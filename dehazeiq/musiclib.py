"""Musikbibliotek och musikkällor.

Kärnan bryr sig bara om ljudfil, längd, tempo, energi och licens. Var låten kommer ifrån är en
"källa":
  - Mappar på datorn (allt man laddat ner från Epidemic, Artlist, Pixabay, YouTube Audio Library …
    eller egen musik). Bevakas och läses in automatiskt.
  - Openverse: sökbar gratis musik med öppen licens (Jamendo, Freesound, Wikimedia m.fl.), ingen nyckel.
  - Egna tjänster: en liten JSON-fil i mappen music_sources/ beskriver hur man söker och hämtar
    (adress, nyckel, var fälten finns i svaret). Ingen kod behövs för att lägga till en tjänst.

Varje låt har en licens. Programmet namnger upphovspersonen när licensen kräver det och
använder aldrig musik som bara får användas privat i reklamfilmer.
"""

import hashlib
import json
import random
import re
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

from .config import AUDIO_EXT, HOME

LIB_FILE = HOME / "music_library.json"
DOWNLOAD_DIR = HOME / "music"
SOURCES_DIR = HOME / "music_sources"
UA = "DeHazeIQ (+https://github.com/foppen6/dehazeiq)"
_lock = threading.Lock()

# Licenstyper i gränssnittet
LICENSE_KINDS = {
    "own": "Egen eller köpt – du har rätt att använda den",
    "commercial": "Fri för allt, även reklam",
    "cc": "Creative Commons (se villkoren)",
    "private": "Bara privat bruk",
    "unknown": "Okänd licens",
}

# Vilken sorts musik passar stilen: (tempo min, tempo max, energi 0..1)
STYLE_MUSIC = {
    "calm": (55, 95, 0.35), "documentary": (55, 100, 0.35), "ambient": (50, 90, 0.25),
    "mv_ballad": (60, 100, 0.45), "promo_premium": (70, 110, 0.45), "widescreen": (70, 115, 0.5),
    "cinematic": (75, 120, 0.55), "vintage": (80, 125, 0.55), "minimal": (80, 125, 0.5),
    "promo_info": (85, 125, 0.5), "mv_lyrics": (80, 130, 0.6), "trailer": (70, 130, 0.7),
    "vlog": (95, 130, 0.6), "playful": (100, 135, 0.65), "promo_experience": (95, 130, 0.65),
    "action": (115, 150, 0.8), "musicvideo": (110, 150, 0.8), "mv_glitch": (120, 160, 0.85),
    "promo_energy": (115, 150, 0.85),
}


# ---------- licenser ----------

def license_from_code(code, attribution="", url="", source=""):
    """CC-kod (by, by-sa, by-nc, cc0, pdm …) → licensobjekt."""
    code = (code or "").lower().replace("cc-", "")
    if code in ("cc0", "pdm", "pd", "publicdomain"):
        return {"kind": "commercial", "code": code, "attribution": attribution, "url": url,
                "needs_credit": False, "commercial": True, "source": source}
    if code.startswith("by"):
        nc = "nc" in code
        return {"kind": "private" if nc else "cc", "code": code, "attribution": attribution, "url": url,
                "needs_credit": True, "commercial": not nc, "source": source}
    return {"kind": "unknown", "code": code, "attribution": attribution, "url": url,
            "needs_credit": bool(attribution), "commercial": None, "source": source}


def commercial_ok(lic):
    lic = lic or {}
    if lic.get("kind") in ("own", "commercial"):
        return True
    return bool(lic.get("commercial"))


def credit_line(track):
    lic = track.get("license") or {}
    if not lic.get("needs_credit"):
        return ""
    if lic.get("attribution"):
        return f"Musik: {lic['attribution']}"
    who = track.get("artist") or ""
    code = (lic.get("code") or "").upper()
    return f"Musik: {track.get('title') or track.get('name')}" + (f" – {who}" if who else "") + (f" (CC {code})" if code else "")


# ---------- biblioteket ----------

def _load():
    try:
        return json.loads(LIB_FILE.read_text("utf-8"))
    except (OSError, ValueError):
        return {"dirs": [], "tracks": {}, "auto": True}


def _save(lib):
    LIB_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = LIB_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(lib, ensure_ascii=False), "utf-8")
    tmp.replace(LIB_FILE)


def library():
    with _lock:
        lib = _load()
    if str(DOWNLOAD_DIR) not in lib["dirs"] and DOWNLOAD_DIR.exists():
        lib["dirs"].append(str(DOWNLOAD_DIR))
    return lib


def public(lib=None):
    """Biblioteket för gränssnittet (utan taktslagslistor)."""
    lib = lib or library()
    tracks = []
    for tid, t in lib["tracks"].items():
        if not Path(t["path"]).exists():
            continue
        tracks.append({k: v for k, v in t.items() if k not in ("beats", "energy", "drops")}
                      | {"id": tid, "character": character(t)})
    tracks.sort(key=lambda t: (t.get("title") or t["name"]).lower())
    return {"dirs": lib["dirs"], "auto": lib.get("auto", True), "tracks": tracks,
            "starter": lib.get("starter") or {},
            "license_kinds": LICENSE_KINDS, "sources": [s["name"] for s in custom_sources()]}


def track_id(path):
    return hashlib.sha1(str(Path(path).resolve()).encode("utf-8")).hexdigest()[:12]


def set_dirs(dirs):
    with _lock:
        lib = _load()
        lib["dirs"] = [str(Path(d).expanduser()) for d in dirs if str(d).strip()]
        _save(lib)
    return lib


def set_auto(on):
    with _lock:
        lib = _load()
        lib["auto"] = bool(on)
        _save(lib)


def set_license(tid, kind):
    if kind not in LICENSE_KINDS:
        raise ValueError("Okänd licens")
    with _lock:
        lib = _load()
        t = lib["tracks"].get(tid)
        if not t:
            raise ValueError("Okänd låt")
        lic = dict(t.get("license") or {})
        lic["kind"] = kind
        lic["commercial"] = kind in ("own", "commercial") or (kind == "cc" and "nc" not in (lic.get("code") or ""))
        lic["needs_credit"] = kind == "cc" or bool(lic.get("needs_credit") and kind != "own")
        t["license"] = lic
        _save(lib)
        return t


def _tags(path):
    from .media import ffprobe, run
    try:
        out = run([ffprobe(), "-v", "error", "-print_format", "json", "-show_format", str(path)]).stdout
        tags = {k.lower(): v for k, v in ((json.loads(out or b"{}").get("format") or {}).get("tags") or {}).items()}
    except Exception:  # noqa: BLE001
        tags = {}
    return tags


def _sidecar(path):
    side = Path(str(path) + ".json")
    try:
        return json.loads(side.read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def scan(progress=None):
    """Läs in alla låtar i biblioteksmapparna (bara nya och ändrade analyseras)."""
    from . import music
    lib = library()
    files = []
    for d in lib["dirs"]:
        p = Path(d)
        if p.is_dir():
            files += [f for f in sorted(p.rglob("*")) if f.is_file() and f.suffix.lower() in AUDIO_EXT
                      and not f.name.startswith(".")]
    known = lib["tracks"]
    seen, added = set(), 0
    for i, f in enumerate(files):
        tid = track_id(f)
        seen.add(tid)
        st = f.stat()
        old = known.get(tid)
        if old and old.get("mtime") == st.st_mtime and old.get("size") == st.st_size:
            continue
        if progress:
            progress(i / max(1, len(files)), f"Lyssnar på {f.name}")
        try:
            info = music.analyze(f)
        except Exception:  # noqa: BLE001
            continue
        tags = _tags(f)
        side = _sidecar(f)
        lic = side.get("license") or (old or {}).get("license")
        if not lic:
            code = tags.get("license") or tags.get("copyright") or ""
            m = re.search(r"\b(cc0|by-nc-sa|by-nc-nd|by-nc|by-sa|by-nd|by)\b", code.lower())
            lic = license_from_code(m.group(1), source="mapp") if m else {"kind": "own", "commercial": True,
                                                                         "needs_credit": False, "source": "mapp"}
        e = info.get("energy") or []
        known[tid] = {
            "path": str(f), "name": f.stem, "title": side.get("title") or tags.get("title") or f.stem,
            "artist": side.get("artist") or tags.get("artist") or "",
            "duration": info["duration"], "bpm": info["bpm"], "beats": info["beats"], "energy": e,
            "drops": info.get("drops") or [], "mean_energy": round(float(np.mean(e)) if e else 0.5, 3),
            "intensity": intensity(info.get("bpm") or 100, info.get("activity") or 0.0),
            "license": lic, "mtime": st.st_mtime, "size": st.st_size, "added": time.time(),
        }
        added += 1
    for tid in list(known):
        if tid not in seen and not Path(known[tid]["path"]).exists():
            known.pop(tid)
    with _lock:
        cur = _load()
        cur["tracks"] = known
        cur["dirs"] = lib["dirs"]
        _save(cur)
    return {"tracks": len(known), "new": added}


def intensity(bpm, activity):
    """0..1: hur intensiv musiken känns (tempo och hur tätt det händer saker)."""
    a = min(1.0, activity * 5.0)
    b = min(1.0, max(0.0, (bpm - 60.0) / 80.0))
    return round(0.6 * a + 0.4 * b, 3)


def character(t):
    i = t.get("intensity", 0.5)
    return "Lugn" if i < 0.38 else "Energisk" if i > 0.62 else "Mellan"


def pick(style_key, length, commercial=False, avoid=(), seed=None):
    """Bästa låten i biblioteket för stilen (tempo, energi, längd och licens). None om inget passar."""
    lib = library()
    if not lib.get("auto", True):
        return None
    lo, hi, energy = STYLE_MUSIC.get(style_key, (80, 130, 0.55))
    cands = []
    for tid, t in lib["tracks"].items():
        if not Path(t["path"]).exists() or tid in avoid:
            continue
        if commercial and not commercial_ok(t.get("license")):
            continue
        if (t.get("license") or {}).get("kind") == "unknown" and commercial:
            continue
        bpm = t.get("bpm") or 100
        # halv/dubbel takt räknas också (60 BPM-ballad passar 120-stil i halvtakt)
        mid = (lo + hi) / 2
        d = min(abs(bpm - mid), abs(bpm * 2 - mid) + 12, abs(bpm / 2 - mid) + 12)
        tempo = max(0.0, 1 - d / 40.0)
        en = 1 - abs(t.get("intensity", 0.5) - energy) * 1.6
        dur = 1.0 if t["duration"] >= length else max(0.0, t["duration"] / max(1.0, length)) - 0.3
        cands.append((tempo + en + dur, tid, t))
    if not cands:
        return None
    cands.sort(key=lambda x: -x[0])
    rng = random.Random(seed)
    good = [c for c in cands if c[0] >= cands[0][0] - 0.12][:3]  # variation bara mellan låtar som passar
    _, tid, t = rng.choice(good)
    out = {k: t[k] for k in ("path", "duration", "bpm", "beats", "energy", "drops")}
    out.update(name=t.get("title") or t["name"], track_id=tid, artist=t.get("artist", ""),
               license=t.get("license"), credit=credit_line(t), auto=True)
    return out


def track_music(tid):
    """Musikinfo för en bestämd låt i biblioteket (samma format som pick)."""
    t = library()["tracks"].get(tid)
    if not t or not Path(t["path"]).exists():
        return None
    out = {k: t[k] for k in ("path", "duration", "bpm", "beats", "energy", "drops")}
    out.update(name=t.get("title") or t["name"], track_id=tid, artist=t.get("artist", ""),
               license=t.get("license"), credit=credit_line(t), auto=True)
    return out


# ---------- Openverse (gratis, ingen nyckel) ----------

OPENVERSE = "https://api.openverse.org/v1/audio/"


def _get_json(url, headers=None, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (bara https-adresser)
        return json.loads(r.read().decode("utf-8"))


def openverse_search(q, commercial=False, length=None, page=1):
    params = {"q": q, "category": "music", "page_size": 20, "page": page, "filter_dead": "true",
              "license_type": "commercial,modification" if commercial else "modification"}
    if length in ("short", "medium", "long"):
        params["length"] = length
    data = _get_json(OPENVERSE + "?" + urllib.parse.urlencode(params))
    out = []
    for r in data.get("results") or []:
        if not r.get("url"):
            continue
        lic = license_from_code(r.get("license"), r.get("attribution") or "", r.get("license_url") or "",
                                "Openverse · " + str(r.get("source") or r.get("provider") or ""))
        out.append({"id": r.get("id"), "title": r.get("title") or "Utan titel", "artist": r.get("creator") or "",
                    "url": r["url"], "duration": round((r.get("duration") or 0) / 1000.0, 1),
                    "filetype": r.get("filetype") or "", "license": lic,
                    "page": r.get("foreign_landing_url") or "", "source": "openverse"})
    return {"results": out, "count": data.get("result_count", len(out))}


# ---------- egna tjänster (JSON-beskrivning) ----------

EXAMPLE_SOURCE = {
    "name": "Exempeltjänst",
    "about": "Kopiera filen, byt namn och fyll i adresserna enligt tjänstens API-dokumentation.",
    "key": "",
    "search_url": "https://api.example.com/v1/music/search?q={q}&limit=20",
    "headers": {"Authorization": "Bearer {key}"},
    "results": "data",
    "fields": {"id": "id", "title": "title", "artist": "artist.name", "url": "download_url",
               "duration": "duration", "license": "license"},
    "duration_unit": "s",
    "license_default": "commercial",
    "enabled": False,
}


def custom_sources():
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    ex = SOURCES_DIR / "exempel.json.txt"
    if not ex.exists():
        ex.write_text(json.dumps(EXAMPLE_SOURCE, ensure_ascii=False, indent=2), "utf-8")
    out = []
    for f in sorted(SOURCES_DIR.glob("*.json")):
        try:
            d = json.loads(f.read_text("utf-8"))
            if d.get("enabled", True) and d.get("search_url"):
                d["file"] = f.name
                out.append(d)
        except (OSError, ValueError):
            continue
    return out


def _dig(obj, path):
    for part in str(path).split("."):
        if isinstance(obj, list):
            try:
                obj = obj[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return None
    return obj


def custom_search(name, q):
    src = next((s for s in custom_sources() if s["name"] == name), None)
    if not src:
        raise ValueError("Okänd musiktjänst")
    key = src.get("key") or ""
    url = src["search_url"].replace("{q}", urllib.parse.quote(q)).replace("{key}", urllib.parse.quote(key))
    headers = {k: str(v).replace("{key}", key) for k, v in (src.get("headers") or {}).items()}
    data = _get_json(url, headers)
    rows = _dig(data, src.get("results") or "results") or []
    f = src.get("fields") or {}
    out = []
    for r in rows if isinstance(rows, list) else []:
        u = _dig(r, f.get("url", "url"))
        if not u:
            continue
        dur = float(_dig(r, f.get("duration", "duration")) or 0)
        if src.get("duration_unit") == "ms":
            dur /= 1000.0
        code = str(_dig(r, f.get("license", "license")) or "")
        lic = license_from_code(code, source=name) if code else {
            "kind": src.get("license_default", "own"), "commercial": src.get("license_default") in ("own", "commercial"),
            "needs_credit": False, "source": name}
        out.append({"id": str(_dig(r, f.get("id", "id")) or u), "title": str(_dig(r, f.get("title", "title")) or ""),
                    "artist": str(_dig(r, f.get("artist", "artist")) or ""), "url": u, "duration": round(dur, 1),
                    "license": lic, "source": name, "headers": headers if src.get("download_with_key") else None})
    return {"results": out, "count": len(out)}


def download(item):
    """Hämtar en låt till biblioteket (mappen music/) med licensen sparad bredvid."""
    url = item.get("url") or ""
    if not url.startswith("https://"):
        raise ValueError("Bara https-adresser")
    folder = DOWNLOAD_DIR / re.sub(r"[^\w\- ]", "", (item.get("source") or "Hämtat").split("·")[0]).strip()
    folder.mkdir(parents=True, exist_ok=True)
    ext = Path(urllib.parse.urlparse(url).path).suffix.lower()
    if ext not in AUDIO_EXT:
        ext = "." + (item.get("filetype") or "mp3").lower().strip(".")
    safe = re.sub(r"[^\w\- ]", "", f"{item.get('artist', '')} - {item.get('title', '')}").strip(" -")[:90] or "låt"
    dst = folder / f"{safe}{ext}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(item.get("headers") or {})})
    tmp = dst.with_suffix(dst.suffix + ".part")
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as fh:  # noqa: S310
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            fh.write(chunk)
    tmp.replace(dst)
    Path(str(dst) + ".json").write_text(json.dumps({
        "title": item.get("title"), "artist": item.get("artist"), "license": item.get("license"),
        "page": item.get("page"), "downloaded": time.time()}, ensure_ascii=False), "utf-8")
    with _lock:
        lib = _load()
        if str(DOWNLOAD_DIR) not in lib["dirs"]:
            lib["dirs"].append(str(DOWNLOAD_DIR))
        _save(lib)
    return dst


# ---------- startpaket: gratis musik direkt från början ----------

STARTER = [  # (sökord, karaktär) – några låtar av varje sort så att AI:n har något att välja mellan
    ("calm ambient", "lugn"), ("underwater ambient", "lugn"), ("acoustic guitar", "mellan"),
    ("cinematic", "mellan"), ("upbeat", "energisk"), ("electronic dance", "energisk"),
]


def starter_pack(progress=None, per_query=2):
    """Hämtar en liten uppsättning gratis musik (CC0 och CC BY, får användas även i reklam)
    från Openverse till biblioteket och läser in den. Körs automatiskt när biblioteket är tomt."""
    got, errors, seen = [], [], set()
    for k, (q, _) in enumerate(STARTER):
        if progress:
            progress(k / len(STARTER) * 0.6, f"Hämtar gratis musik: {q}")
        try:
            res = openverse_search(q, commercial=True, length="medium")["results"]
        except Exception as e:  # noqa: BLE001
            errors.append(f"{q}: {e.__class__.__name__}")
            continue
        n = 0
        for r in res:
            if n >= per_query or r["id"] in seen or not r["url"].startswith("https://"):
                continue
            if r["duration"] and not (40 <= r["duration"] <= 420):
                continue
            try:
                got.append(download(dict(r, source="Gratis startpaket")))
                seen.add(r["id"])
                n += 1
            except Exception as e:  # noqa: BLE001
                errors.append(f"{r['title']}: {e.__class__.__name__}")
    with _lock:
        lib = _load()
        lib["starter"] = {"done": bool(got), "count": len(got), "errors": errors[:5], "time": time.time()}
        if str(DOWNLOAD_DIR) not in lib["dirs"]:
            lib["dirs"].append(str(DOWNLOAD_DIR))
        _save(lib)
    if got:
        scan(lambda f, m: progress(0.6 + 0.4 * f, m) if progress else None)
    if not got:
        raise RuntimeError("Kunde inte hämta gratis musik. Kontrollera internetanslutningen och försök igen under Musik.")
    return {"downloaded": len(got)}


def needs_starter():
    lib = library()
    real = [t for t in lib["tracks"].values() if Path(t["path"]).exists()]
    st = lib.get("starter") or {}
    return not real and not st.get("done") and time.time() - st.get("time", 0) > 3600
