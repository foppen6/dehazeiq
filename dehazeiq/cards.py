"""Hittar minneskort och kameror (SD-kort, Insta360, GoPro, telefon i USB-läge) som kopplas in,
och räknar hur många klipp på dem som inte redan finns i något projekt."""
import json
import os
import string
import sys
import threading
import time
from pathlib import Path

from .config import PROJECTS_DIR, VIDEO_EXT

_CACHE = {"t": 0.0, "cards": []}
_LOCK = threading.Lock()
_IGNORED = set()
SKIP_DIRS = {"LRV", "MISC", "THM", ".Trashes", ".Spotlight-V100", ".fseventsd", "System Volume Information"}


def _roots():
    if sys.platform == "darwin":
        base = Path("/Volumes")
        return [p for p in base.iterdir() if p.is_dir() and not p.is_symlink()] if base.exists() else []
    if os.name == "nt":
        out = []
        try:
            import ctypes
            mask = ctypes.windll.kernel32.GetLogicalDrives()
            for i, letter in enumerate(string.ascii_uppercase):
                if mask & (1 << i) and letter not in "AC":
                    root = Path(f"{letter}:\\")
                    if ctypes.windll.kernel32.GetDriveTypeW(f"{letter}:\\") == 2:  # flyttbar enhet
                        out.append(root)
        except (OSError, AttributeError):
            pass
        return out
    roots, seen = [], set()
    user = os.environ.get("USER") or ""
    for base in {Path("/media") / user, Path("/run/media") / user, Path("/media")}:
        if base.exists():
            for p in base.iterdir():
                if p.is_dir() and str(p) not in seen:
                    seen.add(str(p))
                    roots.append(p)
    return roots


def _media_dir(root):
    """Kortets mapp med film: DCIM (de flesta kameror) eller PRIVATE/M4ROOT (Sony)."""
    for name in ("DCIM", "PRIVATE/M4ROOT/CLIP", "PRIVATE/AVCHD"):
        d = root / name
        if d.is_dir():
            return d
    return None


def _known():
    """(filnamn, storlek) för alla klipp i alla projekt."""
    known = set()
    for f in PROJECTS_DIR.glob("*/project.json"):
        try:
            clips = json.loads(f.read_text("utf-8")).get("clips") or {}
        except (OSError, ValueError):
            continue
        for c in clips.values():
            if c.get("name"):
                known.add((c["name"].lower(), int(c.get("size") or 0)))
                known.add((c["name"].lower(), 0))
    return known


def _scan_card(root, known):
    media = _media_dir(root)
    if not media:
        return None
    files, new, size_new = 0, [], 0
    deadline = time.time() + 4.0
    for dirpath, dirnames, filenames in os.walk(media):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            if fn.startswith(".") or Path(fn).suffix.lower() not in VIDEO_EXT:
                continue
            p = Path(dirpath) / fn
            try:
                sz = p.stat().st_size
            except OSError:
                continue
            files += 1
            if (fn.lower(), sz) not in known and (fn.lower(), 0) not in known:
                new.append(str(p))
                size_new += sz
        if time.time() > deadline:
            break
    if not files:
        return None
    return {"path": str(root), "name": root.name or str(root), "media": str(media), "files": files,
            "new": len(new), "new_paths": new[:2000], "new_gb": round(size_new / 1e9, 1)}


def cards(max_age=6.0):
    with _LOCK:
        if time.time() - _CACHE["t"] < max_age:
            return _CACHE["cards"]
        known = None
        out = []
        for root in _roots():
            if str(root) in _IGNORED:
                continue
            try:
                if not _media_dir(root):
                    continue
                known = known if known is not None else _known()
                c = _scan_card(root, known)
            except OSError:
                continue
            if c:
                out.append(c)
        _CACHE.update(t=time.time(), cards=out)
        return out


def ignore(path):
    with _LOCK:
        _IGNORED.add(str(path))
        _CACHE["t"] = 0.0


def forget_cache():
    with _LOCK:
        _CACHE["t"] = 0.0
