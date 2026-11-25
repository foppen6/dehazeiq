"""Färgmatchning mellan klipp: varje klipp får samma ljushet, kontrast och färgton som ett
referensklipp, så att filmen ser ut att vara filmad vid ett och samma tillfälle.

Mätningen görs på några bilder ur klippets utsnitt (efter AI:ns vitbalans). Korrigeringen är en
linjär kurva per färgkanal som flyttar klippets 5:e och 95:e percentil till referensens, med
gränser så att mörka eller färglösa klipp inte förstärks till brus. Klipp under vattnet matchas mot
ett undervattensklipp och klipp ovan ytan mot ett klipp ovan ytan.

prop["match"] = {"on": bool, "ref": shot-uid eller None (AI väljer), "strength": 0..1}
shot["nomatch"] = True: klippet lämnas som det är.
"""

import json
import subprocess
import threading
from pathlib import Path

import numpy as np

from .media import ffmpeg, subprocess_kwargs

STATS_VERSION = 1
DEFAULT_STRENGTH = 0.7
_lock = threading.Lock()


def settings(prop, effects_on=True):
    m = dict(prop.get("match") or {})
    m.setdefault("on", bool(effects_on))
    m.setdefault("strength", DEFAULT_STRENGTH)
    m.setdefault("ref", None)
    return m


def group(shot, clip):
    uw = shot.get("underwater") or (clip.get("analysis") or {}).get("underwater")
    return "uw" if uw else "air"


def _cache_file(project):
    return project.dir / "cache" / "colorstats.json"


def _load(project):
    try:
        return json.loads(_cache_file(project).read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def _save(project, data):
    f = _cache_file(project)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data), "utf-8")


def shot_stats(project, shot, cache=None):
    """[[p5, p50, p95] för R, G, B] (0–255) i klippets utsnitt, efter vitbalansen."""
    clip = project.data["clips"].get(shot["clip_id"])
    if not clip:
        return None
    speed = float((shot.get("fx") or {}).get("speed") or 1.0)
    t0 = float(shot.get("src_start", 0.0))
    t1 = float(shot.get("src_end") or t0 + float(shot.get("duration", 1.0)) * speed)
    gains = shot.get("wb_gains") or [1, 1, 1]
    key = f"{STATS_VERSION}:{clip['id']}:{t0:.1f}:{t1:.1f}:" + ",".join(f"{g:.2f}" for g in gains)
    own = cache is None
    if own:
        with _lock:
            cache = _load(project)
    if key in cache:
        return cache[key]
    proxy = project.proxy_path(clip["id"])
    src = proxy if proxy.exists() else Path(clip["path"])
    if clip.get("photo") or clip.get("is_photo"):
        times = [0.0]
    else:
        times = [t0 + (t1 - t0) * f for f in (0.2, 0.5, 0.8)]
    pix = []
    for t in times:
        vf = "scale=96:-2,format=rgb24"
        cmd = [ffmpeg(), "-hide_banner", "-loglevel", "error", "-ss", f"{max(0.0, t):.3f}", "-i", str(src),
               "-frames:v", "1", "-vf", vf, "-f", "rawvideo", "pipe:1"]
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=30, **subprocess_kwargs())
        except (OSError, subprocess.TimeoutExpired):
            continue
        if r.returncode == 0 and len(r.stdout) >= 3 * 16:
            a = np.frombuffer(r.stdout, np.uint8).reshape(-1, 3).astype(np.float32)
            pix.append(a * np.array(gains, np.float32))
    if not pix:
        return None
    a = np.clip(np.concatenate(pix), 0, 255)
    st = [[round(float(np.percentile(a[:, c], p)), 2) for p in (5, 50, 95)] for c in range(3)]
    cache[key] = st
    if own:
        with _lock:
            data = _load(project)
            data[key] = st
            _save(project, data)
    return st


def correction(src, ref, k):
    """Per kanal (a, b): ut = in·a + b (0–255). k = styrka 0–1.
    Färgsticket matchas fullt ut, ljushet och kontrast bara delvis: en mörk scen får förbli
    lite mörkare än en ljus, annars ser det onaturligt ut och bruset syns."""
    raw = []
    for (s5, s50, s95), (r5, r50, r95) in zip(src, ref):
        a = (r95 - r5) / max(8.0, s95 - s5)
        a = min(1.25, max(0.8, a))  # förstärk inte brus i platta klipp
        raw.append((a, r50 - a * s50))
    am = sum(a for a, _ in raw) / 3
    bm = sum(b for _, b in raw) / 3
    lum_k = 0.55 * k
    out = []
    for a, b in raw:
        aa = 1 + (am - 1) * lum_k + (a - am) * k
        bb = bm * lum_k + (b - bm) * k
        out.append((round(aa, 4), round(min(32.0, max(-32.0, bb)), 2)))
    return out


def plan(project, prop, effects_on=True):
    """Korrigering per klipp: {index: [(a, b) × 3]} och referensklippens index per grupp."""
    m = settings(prop, effects_on)
    shots = prop.get("shots") or []
    if not m["on"] or len(shots) < 2:
        return {}, {}
    clips = project.data["clips"]
    with _lock:
        cache = _load(project)
    n0 = len(cache)
    groups = {}
    for i, s in enumerate(shots):
        c = clips.get(s["clip_id"])
        if c and not s.get("nomatch") and not (s.get("fx") or {}).get("raw"):
            groups.setdefault(group(s, c), []).append((i, s))
    refs, out = {}, {}
    k = max(0.0, min(1.0, float(m["strength"])))
    for g, members in groups.items():
        ref = next(((i, s) for i, s in members if m["ref"] and s.get("uid") == m["ref"]), None)
        if ref is None:  # AI: bästa klippet i gruppen (tydligast och vackrast)
            ref = max(members, key=lambda x: (float(x[1].get("quality") or 0), float(x[1].get("duration") or 0)))
        refs[g] = ref[0]
        rst = shot_stats(project, ref[1], cache)
        if not rst or len(members) < 2:
            continue
        for i, s in members:
            if i == ref[0]:
                continue
            st = shot_stats(project, s, cache)
            if st:
                out[i] = correction(st, rst, k)
    if len(cache) != n0:
        with _lock:
            data = _load(project)
            data.update(cache)
            _save(project, data)
    return out, refs


def lut(corr):
    if not corr:
        return []
    if all(abs(a - 1) < 0.01 and abs(b) < 1.0 for a, b in corr):
        return []
    e = [f"clip(val*{a:.4f}{b:+.2f},0,255)" for a, b in corr]
    return [f"format=rgb24,lutrgb=r='{e[0]}':g='{e[1]}':b='{e[2]}'"]
