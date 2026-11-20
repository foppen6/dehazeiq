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

    def add_proposals(self, props, keep=12):
        with _LOCK:
            self.reload()
            self.data["proposals"] = (props + self.data.get("proposals", []))[:keep]
            self.save()

    def update_proposal(self, prop_id, **fields):
        with _LOCK:
            self.reload()
            for p in self.data.get("proposals", []):
                if p["id"] == prop_id:
                    p.update(fields)
            self.save()


_SETTINGS_FILE = PROJECTS_DIR.parent / "settings.json"
_DEFAULTS = {"format": "9:16", "length": 30, "style": "auto"}


def default_settings():
    """Senast använda format/längd/stil – nya projekt får samma."""
    try:
        data = json.loads(_SETTINGS_FILE.read_text("utf-8"))
        return {k: data.get(k, v) for k, v in _DEFAULTS.items()}
    except (OSError, ValueError):
        return dict(_DEFAULTS)


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


def collect_video_files(paths):
    """Expandera mappar till videofiler. Hoppar över dolda filer och Insta360-LRV."""
    files = []
    for raw in paths:
        p = Path(raw).expanduser()
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and not f.name.startswith(".") and f.suffix.lower() in VIDEO_EXT:
                    files.append(f)
        elif p.is_file() and p.suffix.lower() in VIDEO_EXT:
            files.append(p)
    return files


class Jobs:
    """Ett bakgrundsjobb åt gången per projekt, med framsteg för gränssnittet."""

    def __init__(self):
        self._status = {}
        self._lock = threading.Lock()

    def status(self, pid):
        with self._lock:
            return dict(self._status.get(pid) or {"state": "idle"})

    def busy(self, pid):
        return self.status(pid).get("state") == "running"

    def start(self, pid, kind, fn, *args):
        with self._lock:
            if (self._status.get(pid) or {}).get("state") == "running":
                raise RuntimeError("Ett jobb körs redan i projektet")
            job = {"id": uuid.uuid4().hex[:8], "kind": kind, "state": "running",
                   "progress": 0.0, "message": "Startar …", "started": time.time()}
            self._status[pid] = job

        def progress(frac=None, message=None):
            with self._lock:
                if frac is not None:
                    job["progress"] = round(max(0.0, min(1.0, float(frac))), 4)
                if message is not None:
                    job["message"] = message

        def runner():
            try:
                result = fn(progress, *args)
                with self._lock:
                    job.update(state="done", progress=1.0, result=result,
                               message="Klart", finished=time.time())
            except Exception as exc:  # noqa: BLE001
                traceback.print_exc()
                with self._lock:
                    job.update(state="error", message=str(exc), finished=time.time())

        threading.Thread(target=runner, daemon=True).start()
        return job["id"]


JOBS = Jobs()
