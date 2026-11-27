"""Egna mallar: en sparad kombination av filmtyper, format, längd, effekter och export.

"Kör med mallen" sätter projektets inställningar och kör hela flödet (import → analys →
förslag → förhandsvisningar), och kan exportera det bästa förslaget direkt till mallens
plattformar."""
import json
import os
import threading
import time
import uuid

from .config import HOME

_FILE = HOME / "templates.json"
_LOCK = threading.Lock()
SETTING_KEYS = ("format", "length", "style", "plans", "effects", "previews")
RESOLUTIONS = ("720p", "1080p", "4k")


def _load():
    try:
        data = json.loads(_FILE.read_text("utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _save(items):
    _FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), "utf-8")
    os.replace(tmp, _FILE)


def all_templates():
    with _LOCK:
        return _load()


def get(tid):
    return next((t for t in all_templates() if t.get("id") == tid), None)


def clean_export(exp, platforms, langs):
    exp = exp if isinstance(exp, dict) else {}
    plats = [p for p in exp.get("platforms") or [] if p in platforms]
    return {"platforms": plats,
            "resolution": exp.get("resolution") if exp.get("resolution") in RESOLUTIONS else "1080p",
            "langs": [x for x in exp.get("langs") or ["sv"] if x in langs] or ["sv"],
            "auto": bool(exp.get("auto")) and bool(plats),
            "which": exp.get("which") if exp.get("which") in ("best", "all") else "best"}


def save(name, settings, export, platforms, langs, tid=None):
    name = " ".join(str(name or "").split())[:60]
    if not name:
        raise ValueError("Ge mallen ett namn")
    item = {"id": tid or uuid.uuid4().hex[:10], "name": name, "created": time.time(),
            "settings": {k: settings[k] for k in SETTING_KEYS if k in (settings or {})},
            "export": clean_export(export, platforms, langs)}
    with _LOCK:
        items = _load()
        old = next((i for i, t in enumerate(items) if t.get("id") == item["id"] or t.get("name") == name), None)
        if old is not None:
            item["id"] = items[old]["id"]
            item["created"] = items[old].get("created", item["created"])
            items[old] = item
        else:
            items.append(item)
        _save(items)
    return item


def delete(tid):
    with _LOCK:
        items = _load()
        rest = [t for t in items if t.get("id") != tid]
        if len(rest) == len(items):
            return False
        _save(rest)
        return True


def describe(t):
    """Kort text till listan: 'Reels 15 s, Musikvideo · exporterar till Instagram, TikTok'."""
    s = t.get("settings") or {}
    parts = []
    if s.get("plans"):
        parts.append(f"{len(s['plans'])} filmtyper")
    else:
        parts.append(f"{s.get('format', '9:16')} · {int(float(s.get('length') or 30))} s")
    e = t.get("export") or {}
    if e.get("auto"):
        parts.append(f"exporterar {('alla förslag' if e.get('which') == 'all' else 'bästa förslaget')} "
                     f"({len(e['platforms'])} plattform{'ar' if len(e['platforms']) != 1 else ''}, {e['resolution']})")
    return " · ".join(parts)


def public():
    return [dict(t, text=describe(t)) for t in all_templates()]
