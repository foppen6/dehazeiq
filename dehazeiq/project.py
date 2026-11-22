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

from .config import PROJECTS_DIR, VIDEO_EXT
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


class Project:
    def __init__(self, pid: str):
        self.id = pid
        self.dir = PROJECTS_DIR / pid
        self.file = self.dir / "project.json"
        if not self.file.exists():
            raise FileNotFoundError(pid)
        with _LOCK:
            self.data = json.loads(self.file.read_text("utf-8"))

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
                out.append({
                    "id": data["id"], "name": data.get("name", data["id"]),
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

    def add_proposals(self, props, keep=40):
        """Nya förslag först. Redigerade förslag sparas alltid; övriga gallras till keep st."""
        with _LOCK:
            self.reload()
            allp = props + self.data.get("proposals", [])
            out, n = [], 0
            for p in allp:
                if p.get("edited") or n < keep:
                    out.append(p)
                    n += 0 if p.get("edited") else 1
            self.data["proposals"] = out
            self.save()

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
        self._worker = None

    # ---------- status ----------
    def _public(self, t, pos=None):
        out = {k: v for k, v in t.items() if k not in ("fn", "args", "cancel")}
        if pos is not None:
            out["position"] = pos
        return out

    def status(self, pid):
        with self._lock:
            running = [t for t in self._tasks if t["pid"] == pid and t["state"] == "running"]
            if running:
                return self._public(running[0])
            queued = [t for t in self._tasks if t["state"] == "queued"]
            for i, t in enumerate(queued):
                if t["pid"] == pid:
                    ahead = sum(1 for x in self._tasks if x["state"] == "running") + i
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
            done = [t for t in self._tasks if t["state"] not in ("running", "queued")]
            done.sort(key=lambda t: -(t.get("finished") or 0))
            return {"paused": self.paused, "tasks": [self._public(t) for t in active],
                    "done": [self._public(t) for t in done[:12]]}

    # ---------- ändra kön ----------
    def start(self, pid, kind, fn, *args, label=None, project_name=None, front=False):
        task = {"id": uuid.uuid4().hex[:8], "pid": pid, "kind": kind, "label": label or kind,
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
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._run, daemon=True)
                self._worker.start()
            self._wake.notify_all()
        return task["id"]

    def cancel(self, tid):
        with self._lock:
            for t in self._tasks:
                if t["id"] == tid:
                    if t["state"] == "queued":
                        t.update(state="cancelled", message="Avbrutet", finished=time.time())
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
            return True

    def pause(self, paused):
        with self._lock:
            self.paused = bool(paused)
            self._wake.notify_all()

    def clear_done(self):
        with self._lock:
            self._tasks = [t for t in self._tasks if t["state"] in ("running", "queued")]

    def _prune(self):
        done = [t for t in self._tasks if t["state"] not in ("running", "queued")]
        if len(done) > self.KEEP_DONE:
            old = sorted(done, key=lambda t: t.get("finished") or 0)[: len(done) - self.KEEP_DONE]
            self._tasks = [t for t in self._tasks if t not in old]

    # ---------- arbetaren ----------
    def _run(self):
        while True:
            with self._lock:
                task = None
                while task is None:
                    if not self.paused:
                        task = next((t for t in self._tasks if t["state"] == "queued"), None)
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
                task["fn"] = None
                task["args"] = ()


JOBS = Jobs()
