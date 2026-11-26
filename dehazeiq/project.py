"""Projektlagring och bakgrundsjobb.

Ett projekt är en mapp under ~/DeHazeIQ/projects/<id>/:
    project.json   – klipp, analysresultat, musik och förslag
    proxies/       – lätta H.264-kopior för analys och förhandsvisning
    analysis/      – rådata från analysen (.npz per klipp)
    renders/       – förhandsvisningar och exporter
"""

import hashlib
import json
import os
import re
import threading
import time
import traceback
import uuid
from pathlib import Path

from .config import HOME, PROJECTS_DIR, VIDEO_EXT
from .effects import DEFAULT_EFFECTS

_LOCK = threading.RLock()


def slugify(name: str) -> str:
    s = name.lower().strip()
    for a, b in (("å", "a"), ("ä", "a"), ("ö", "o"), ("é", "e"), ("ü", "u")):
        s = s.replace(a, b)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "projekt"


def clip_id_for(path: Path) -> str:
    st = path.stat()
    key = f"{path.resolve()}|{st.st_size}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def project_lock():
    """Lås för att läsa, ändra och spara projektfilen i ett svep (så att två samtidiga ändringar,
    t.ex. ett jobb i kön och en redigering, inte skriver över varandra)."""
    return _LOCK


class Project:
    def __init__(self, pid: str):
        self.id = pid
        self.dir = PROJECTS_DIR / pid
        self.file = self.dir / "project.json"
        if not self.file.exists():
            raise FileNotFoundError(pid)
        with _LOCK:
            self.data = json.loads(self.file.read_text("utf-8"))
            self.data["id"] = pid  # mappens namn gäller (en kopierad mapp)

    # ---------- skapa / lista ----------
    @staticmethod
    def create(name: str) -> "Project":
        PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
        base = slugify(name)
        pid, n = base, 2
        while (PROJECTS_DIR / pid).exists():
            pid = f"{base}-{n}"
            n += 1
        d = PROJECTS_DIR / pid
        for sub in ("proxies", "analysis", "renders", "cache"):
            (d / sub).mkdir(parents=True, exist_ok=True)
        data = {
            "id": pid, "name": name.strip() or pid, "created": time.time(),
            "clips": {}, "order": [], "music": None, "proposals": [],
            "settings": default_settings(),
        }
        (d / "project.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
        return Project(pid)

    @staticmethod
    def list_all():
        out = []
        if not PROJECTS_DIR.exists():
            return out
        for d in PROJECTS_DIR.iterdir():
            f = d / "project.json"
            if f.exists():
                try:
                    data = json.loads(f.read_text("utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                clips = data.get("clips", {}).values()
                pid = d.name  # mappens namn: en kopierad projektmapp får inte samma id som originalet
                out.append({
                    "id": pid, "name": data.get("name", pid),
                    "busy": JOBS.busy(pid),
                    "created": data.get("created", 0),
                    "clips": len(data.get("clips", {})),
                    "duration": round(sum(c.get("duration", 0) for c in clips), 1),
                    "modified": f.stat().st_mtime,
                })
        out.sort(key=lambda p: -p["modified"])
        return out

    # ---------- lagring ----------
    def rename(self, name: str):
        with _LOCK:
            self.reload()
            self.data["name"] = name.strip()[:80] or self.data["name"]
            self.save()

    def delete(self):
        """Tar bort projektmappen (proxyfiler, analys, förhandsvisningar och exporter).
        Originalfilmerna rörs inte."""
        import shutil
        with _LOCK:
            shutil.rmtree(self.dir)

    def save(self):
        with _LOCK:
            tmp = self.file.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), "utf-8")
            os.replace(tmp, self.file)

    def reload(self):
        with _LOCK:
            self.data = json.loads(self.file.read_text("utf-8"))
            self.data["id"] = self.id

    def update_clip(self, cid: str, **fields):
        with _LOCK:
            self.reload()
            self.data["clips"].setdefault(cid, {}).update(fields)
            self.save()

    # ---------- sökvägar ----------
    def photo_clip_path(self, cid) -> Path:
        return self.dir / "photos" / f"{cid}.mp4"

    def proxy_path(self, cid) -> Path:
        return self.dir / "proxies" / f"{cid}.mp4"

    def npz_path(self, cid) -> Path:
        return self.dir / "analysis" / f"{cid}.npz"

    @property
    def renders(self) -> Path:
        p = self.dir / "renders"
        p.mkdir(exist_ok=True)
        return p

    @property
    def cache(self) -> Path:
        p = self.dir / "cache"
        p.mkdir(exist_ok=True)
        return p

    # ---------- klipp ----------
    def clips(self):
        return [self.data["clips"][c] for c in self.data.get("order", []) if c in self.data["clips"]]

    def usable_clips(self):
        from .quality import is_usable
        return [c for c in self.clips() if is_usable(c)]

    def proposal(self, prop_id):
        for p in self.data.get("proposals", []):
            if p["id"] == prop_id:
                return p
        return None

    def add_proposals(self, props, keep=None):
        """Nya förslag först. Inget gallras automatiskt (Rensa gamla förslag gör det på begäran).
        Varje anrop är en omgång: förslagen får samma batch-tid så att de kan visas tillsammans."""
        now = time.time()
        for p in props:
            p.setdefault("batch", now)
        with _LOCK:
            self.reload()
            allp = props + self.data.get("proposals", [])
            if keep:
                out, n = [], 0
                for p in allp:
                    if p.get("edited") or p.get("favorite") or n < keep:
                        out.append(p)
                        n += 0 if p.get("edited") else 1
                allp = out
            self.data["proposals"] = allp
            self.save()

    def prune_proposals(self, keep_latest=6):
        """Rensa gamla förslag: behåller favoriter, redigerade och de senaste keep_latest.
        Tar också bort deras förhandsvisningar. Returnerar antal borttagna."""
        with _LOCK:
            self.reload()
            ps = self.data.get("proposals", [])
            keep, gone, n = [], [], 0
            for p in ps:
                if p.get("favorite") or p.get("edited") or n < keep_latest:
                    keep.append(p)
                    n += 0 if (p.get("favorite") or p.get("edited")) else 1
                else:
                    gone.append(p)
            self.data["proposals"] = keep
            self.save()
        for p in gone:
            prev = (p.get("renders") or {}).get("preview")
            if prev:
                (self.dir / "renders" / prev).unlink(missing_ok=True)
        return len(gone)

    def replace_proposal(self, prop):
        with _LOCK:
            self.reload()
            ps = self.data.get("proposals", [])
            for i, p in enumerate(ps):
                if p["id"] == prop["id"]:
                    ps[i] = prop
                    break
            else:
                ps.insert(0, prop)
            self.save()

    def delete_proposal(self, prop_id):
        """Tar bort ett förslag och dess förhandsvisning (exporterade filmer lämnas kvar)."""
        with _LOCK:
            self.reload()
            ps = self.data.get("proposals", [])
            gone = [p for p in ps if p["id"] == prop_id]
            self.data["proposals"] = [p for p in ps if p["id"] != prop_id]
            self.save()
        for p in gone:
            prev = (p.get("renders") or {}).get("preview")
            if prev:
                (self.dir / "renders" / prev).unlink(missing_ok=True)
        return bool(gone)

    def update_proposal(self, prop_id, **fields):
        with _LOCK:
            self.reload()
            for p in self.data.get("proposals", []):
                if p["id"] == prop_id:
                    p.update(fields)
            self.save()


_SETTINGS_FILE = PROJECTS_DIR.parent / "settings.json"
_DEFAULTS = {"format": "9:16", "length": 30, "style": "auto", "effects": dict(DEFAULT_EFFECTS)}


def default_settings():
    """Senast använda format/längd/stil – nya projekt får samma."""
    try:
        data = json.loads(_SETTINGS_FILE.read_text("utf-8"))
        out = {k: data.get(k, v) for k, v in _DEFAULTS.items()}
        out["effects"] = {**DEFAULT_EFFECTS, **(out.get("effects") or {})}
        return out
    except (OSError, ValueError, TypeError):
        return {**_DEFAULTS, "effects": dict(DEFAULT_EFFECTS)}


def save_default_settings(settings):
    try:
        _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        merged = default_settings()
        merged.update({k: settings[k] for k in _DEFAULTS if k in settings})
        _SETTINGS_FILE.write_text(json.dumps(merged), "utf-8")
    except OSError:
        pass


def auto_name(paths) -> str:
    """Projektnamn från mappen som importeras (eller filernas mapp)."""
    from datetime import date
    months = ["jan", "feb", "mars", "april", "maj", "juni", "juli", "aug", "sep", "okt", "nov", "dec"]
    for raw in paths:
        p = Path(raw).expanduser()
        folder = p if p.is_dir() else p.parent
        name = folder.name.strip()
        if name and name.lower() not in ("dcim", "100media", "movies", "filmer", "videos", "downloads",
                                         "hämtade filer", "desktop", "skrivbord", "camera"):
            return name[:80]
    d = date.today()
    return f"Import {d.day} {months[d.month - 1]} {d.year}"


def collect_video_files(paths, photos=True):
    """Expandera mappar till video- och bildfiler. Hoppar över dolda filer och Insta360-LRV.
    Ett foto med samma namn som en RAW-fil (DSC_0001.JPG + DSC_0001.NEF) tas bara med en gång."""
    from .photo import PHOTO_EXT, RAW_EXT
    ok = VIDEO_EXT | (PHOTO_EXT if photos else set())
    files = []
    for raw in paths:
        p = Path(raw).expanduser()
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and not f.name.startswith(".") and f.suffix.lower() in ok:
                    files.append(f)
        elif p.is_file() and p.suffix.lower() in ok:
            files.append(p)
    # JPEG + RAW av samma bild: behåll JPEG:en (kamerans färger, snabbare)
    stems = {(f.parent, f.stem.lower()) for f in files if f.suffix.lower() in PHOTO_EXT - RAW_EXT}
    return [f for f in files if not (f.suffix.lower() in RAW_EXT and (f.parent, f.stem.lower()) in stems)]


class JobCancelled(BaseException):  # BaseException: fångas inte av "except Exception" i jobben
    pass


class Jobs:
    """Jobbkö: ett jobb i taget i bakgrunden, för alla projekt. Jobb kan läggas på kö,
    flyttas, avbrytas och kön kan pausas. Varje projekt ser sitt eget pågående eller
    väntande jobb som status (det är vad gränssnittet visar i projektet)."""

    KEEP_DONE = 30

    def __init__(self):
        self._tasks = []
        self._lock = threading.Lock()
        self._wake = threading.Condition(self._lock)
        self.paused = False
        self._workers = {}
        self._qfile = None
        self._load_saved()

    # ---------- sparad kö (överlever omstart) ----------
    @staticmethod
    def _fn_ref(fn):
        """Bara funktioner på modulnivå med JSON-argument kan sparas och köras igen."""
        mod, name = getattr(fn, "__module__", None), getattr(fn, "__qualname__", "")
        if not mod or not mod.startswith("dehazeiq.") or "<" in name or "." in name:
            return None
        return f"{mod}:{name}"

    def _qpath(self):
        return self._qfile or (HOME / "queue.json")

    def _save(self):
        """Anropas med låset taget. Sparar väntande/pågående jobb som går att köra om."""
        out = []
        for t in self._tasks:
            if t["state"] not in ("running", "queued", "interrupted"):
                continue
            ref = t.get("ref") or (self._fn_ref(t["fn"]) if t.get("fn") else None)
            if not ref:
                continue
            try:
                json.dumps(list(t.get("args") or ()))
            except (TypeError, ValueError):
                continue
            out.append({k: t.get(k) for k in ("id", "pid", "kind", "label", "lane", "project", "queued_at")}
                       | {"ref": ref, "args": list(t.get("args") or ())})
        try:
            f = self._qpath()
            f.parent.mkdir(parents=True, exist_ok=True)
            tmp = f.with_suffix(".tmp")
            tmp.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, f)
        except OSError:
            pass

    def _load_saved(self):
        try:
            saved = json.loads(self._qpath().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for t in saved if isinstance(saved, list) else []:
            if not isinstance(t, dict) or not t.get("ref"):
                continue
            self._tasks.append(dict(t, state="interrupted", progress=0.0, fn=None, cancel=False,
                                    args=tuple(t.get("args") or ()),
                                    message="Avbröts när programmet stängdes", finished=time.time()))

    def retry(self, tid):
        """Kör ett avbrutet jobb igen (efter omstart)."""
        import importlib
        with self._lock:
            t = next((x for x in self._tasks if x["id"] == tid and x["state"] == "interrupted"), None)
            if t is None:
                return None
            self._tasks.remove(t)
            self._save()
        mod, name = t["ref"].split(":", 1)
        fn = getattr(importlib.import_module(mod), name)
        return self.start(t["pid"], t["kind"], fn, *t["args"], label=t.get("label"), project_name=t.get("project"))

    def dismiss(self, tid):
        with self._lock:
            n = len(self._tasks)
            self._tasks = [x for x in self._tasks if not (x["id"] == tid and x["state"] == "interrupted")]
            self._save()
            return len(self._tasks) != n

    # ---------- status ----------
    def _public(self, t, pos=None):
        out = {k: v for k, v in t.items() if k not in ("fn", "args", "cancel", "ref")}
        if pos is not None:
            out["position"] = pos
        return out

    def status(self, pid):
        st = self._status(pid)
        with self._lock:
            st["active"] = [t["id"] for t in self._tasks if t["pid"] == pid and t["state"] in ("running", "queued")]
        return st

    def _status(self, pid):
        with self._lock:
            running = [t for t in self._tasks if t["pid"] == pid and t["state"] == "running"]
            if running:  # förhandsvisning/export först: det är den användaren väntar på
                running.sort(key=lambda t: t.get("lane") != "media")
                return self._public(running[0])
            queued = [t for t in self._tasks if t["state"] == "queued"]
            for i, t in enumerate(queued):
                if t["pid"] == pid:
                    lane_q = [x for x in queued if x.get("lane") == t.get("lane")]
                    ahead = sum(1 for x in self._tasks if x["state"] == "running" and x.get("lane") == t.get("lane")) \
                        + lane_q.index(t)
                    pub = self._public(t, i + 1)
                    pub["state"] = "running"  # för projektet: arbete pågår (väntar i kön)
                    pub["queued"] = True
                    pub["message"] = ("Kön är pausad" if self.paused else
                                      f"Väntar i kön ({ahead} jobb före)" if ahead else "Startar …")
                    return pub
            done = [t for t in self._tasks if t["pid"] == pid and t["state"] in ("done", "error", "cancelled")]
            if done:
                return self._public(max(done, key=lambda t: t.get("finished") or 0))
            return {"state": "idle"}

    def busy(self, pid):
        return self.status(pid).get("state") == "running"

    def running_now(self, pid):
        with self._lock:
            return any(t["pid"] == pid and t["state"] == "running" for t in self._tasks)

    def queue(self):
        with self._lock:
            active = [t for t in self._tasks if t["state"] in ("running", "queued")]
            stopped = [t for t in self._tasks if t["state"] == "interrupted"]
            done = [t for t in self._tasks if t["state"] not in ("running", "queued", "interrupted")]
            done.sort(key=lambda t: -(t.get("finished") or 0))
            return {"paused": self.paused, "tasks": [self._public(t) for t in active],
                    "interrupted": [self._public(t) for t in stopped],
                    "done": [self._public(t) for t in done[:12]]}

    # ---------- ändra kön ----------
    def start(self, pid, kind, fn, *args, label=None, project_name=None, front=False):
        lane = "media" if kind.startswith("render:") else "main"  # förhandsvisning/export i egen fil
        task = {"id": uuid.uuid4().hex[:8], "pid": pid, "kind": kind, "label": label or kind, "lane": lane,
                "project": project_name or pid, "state": "queued", "progress": 0.0,
                "message": "Väntar i kön", "queued_at": time.time(), "fn": fn, "args": args,
                "cancel": False}
        with self._lock:
            if front:
                i = next((k for k, t in enumerate(self._tasks) if t["state"] == "queued"), len(self._tasks))
                self._tasks.insert(i, task)
            else:
                self._tasks.append(task)
            self._prune()
            self._save()
            w = self._workers.get(lane)
            if w is None or not w.is_alive():
                w = self._workers[lane] = threading.Thread(target=self._run, args=(lane,), daemon=True)
                w.start()
            self._wake.notify_all()
        return task["id"]

    def cancel(self, tid):
        with self._lock:
            for t in self._tasks:
                if t["id"] == tid:
                    if t["state"] == "queued":
                        t.update(state="cancelled", message="Avbrutet", finished=time.time())
                        self._save()
                    elif t["state"] == "running":
                        t["cancel"] = True
                        t["message"] = "Avbryter …"
                    return True
        return False

    def move(self, tid, delta):
        with self._lock:
            queued = [t for t in self._tasks if t["state"] == "queued"]
            idx = next((i for i, t in enumerate(queued) if t["id"] == tid), None)
            if idx is None:
                return False
            j = max(0, min(len(queued) - 1, idx + delta))
            if j == idx:
                return True
            a, b = queued[idx], queued[j]
            ia, ib = self._tasks.index(a), self._tasks.index(b)
            self._tasks[ia], self._tasks[ib] = b, a
            self._save()
            return True

    def pause(self, paused):
        with self._lock:
            self.paused = bool(paused)
            self._wake.notify_all()

    def clear_done(self):
        with self._lock:
            self._tasks = [t for t in self._tasks if t["state"] in ("running", "queued")]
            self._save()

    def _prune(self):
        done = [t for t in self._tasks if t["state"] not in ("running", "queued", "interrupted")]
        if len(done) > self.KEEP_DONE:
            old = sorted(done, key=lambda t: t.get("finished") or 0)[: len(done) - self.KEEP_DONE]
            self._tasks = [t for t in self._tasks if t not in old]

    # ---------- arbetaren ----------
    def _run(self, lane="main"):
        while True:
            with self._lock:
                task = None
                while task is None:
                    if not self.paused:
                        task = next((t for t in self._tasks if t["state"] == "queued"
                                     and t.get("lane", "main") == lane), None)
                    if task is None:
                        self._wake.wait(timeout=5)
                task.update(state="running", started=time.time(), message="Startar …")

            def progress(frac=None, message=None, task=task):
                with self._lock:
                    if task["cancel"]:
                        raise JobCancelled()
                    if frac is not None:
                        task["progress"] = round(max(0.0, min(1.0, float(frac))), 4)
                    if message is not None:
                        task["message"] = message

            try:
                result = task["fn"](progress, *task["args"])
                with self._lock:
                    task.update(state="done", progress=1.0, result=result, message="Klart", finished=time.time())
            except JobCancelled:
                with self._lock:
                    task.update(state="cancelled", message="Avbrutet", finished=time.time())
            except Exception as exc:  # noqa: BLE001
                traceback.print_exc()
                with self._lock:
                    task.update(state="error", message=str(exc), finished=time.time())
            finally:
                with self._lock:
                    task["fn"] = None
                    task["args"] = ()
                    self._save()


JOBS = Jobs()
