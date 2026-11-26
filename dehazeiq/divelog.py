"""Dykdata från dykdatorn: djup och temperatur i filmen.

Läser dyklogg exporterad från Subsurface (XML), UDDF, Suunto DM5 (SML/XML) eller CSV.
Dyken kopplas till klippen via tidsstämplarna. Kamerans och dykdatorns klockor går sällan
exakt lika (och kan stå i olika tidszoner), så förskjutningen räknas fram automatiskt:
den som lägger flest undervattensklipp inuti dyken. Den kan också justeras för hand."""

import csv
import io
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import numpy as np


class DiveLogError(Exception):
    pass


def _strip(tag):
    return tag.rsplit("}", 1)[-1].lower()


def _num(s, default=None):
    if s is None:
        return default
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(s))
    return float(m.group(0).replace(",", ".")) if m else default


def _mmss(s):
    """'12:30 min' / '750' / '0:12:30' → sekunder."""
    s = str(s).strip().split()[0] if s else "0"
    if ":" in s:
        parts = [float(x) for x in s.split(":")]
        sec = 0.0
        for p in parts:
            sec = sec * 60 + p
        return sec
    return _num(s, 0.0)


def _temp_c(v):
    if v is None:
        return None
    return v - 273.15 if v > 200 else v  # UDDF och DM5 anger kelvin


def _local_ts(dt):
    return time.mktime(dt.timetuple())


def _parse_dt(text):
    text = (text or "").strip().replace("Z", "")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
                "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(text[:26], fmt)
        except ValueError:
            continue
    return None


def _dive(start, samples, source, number=None):
    samples = sorted((float(t), float(d), (None if tc is None else float(tc))) for t, d, tc in samples if d is not None)
    if len(samples) < 2:
        return None
    dur = samples[-1][0]
    depths = [s[1] for s in samples]
    temps = [s[2] for s in samples if s[2] is not None]
    return {"start": float(start), "duration": float(dur), "max_depth": round(max(depths), 1),
            "min_temp": round(min(temps), 1) if temps else None, "samples": [list(s) for s in samples],
            "source": source, "number": number}


def parse_subsurface(root, source):
    dives = []
    for dv in root.iter():
        if _strip(dv.tag) != "dive":
            continue
        date, tm = dv.get("date"), dv.get("time")
        if not date:
            continue
        dt = _parse_dt(f"{date} {tm or '00:00:00'}")
        if not dt:
            continue
        samples, last_temp = [], None
        for sm in dv.iter():
            if _strip(sm.tag) != "sample":
                continue
            t = _mmss(sm.get("time"))
            d = _num(sm.get("depth"))
            if sm.get("temp") is not None:
                last_temp = _num(sm.get("temp"))
            samples.append((t, d, last_temp))
        d = _dive(_local_ts(dt), samples, source, dv.get("number"))
        if d:
            dives.append(d)
    return dives


def parse_uddf(root, source):
    dives = []
    for dv in root.iter():
        if _strip(dv.tag) != "dive":
            continue
        dt = None
        for el in dv.iter():
            if _strip(el.tag) == "datetime":
                dt = _parse_dt(el.text)
                break
        if not dt:
            continue
        samples, last_temp = [], None
        for wp in dv.iter():
            if _strip(wp.tag) != "waypoint":
                continue
            vals = {_strip(c.tag): c.text for c in wp}
            if vals.get("temperature") is not None:
                last_temp = _temp_c(_num(vals["temperature"]))
            samples.append((_num(vals.get("divetime"), 0.0), _num(vals.get("depth")), last_temp))
        d = _dive(_local_ts(dt), samples, source)
        if d:
            dives.append(d)
    return dives


def parse_sml(root, source):
    """Suunto DM5 / Suunto-app (SML eller XML med <Samples><Sample>)."""
    dt = None
    for el in root.iter():
        if _strip(el.tag) in ("datetime", "starttime"):
            dt = _parse_dt(el.text)
            if dt:
                break
    if not dt:
        raise DiveLogError("Hittade ingen starttid i loggen")
    samples, last_temp = [], None
    for sm in root.iter():
        if _strip(sm.tag) != "sample":
            continue
        vals = {_strip(c.tag): c.text for c in sm}
        if vals.get("temperature") is not None:
            last_temp = _temp_c(_num(vals["temperature"]))
        if vals.get("depth") is None:
            continue
        samples.append((_num(vals.get("time"), 0.0), _num(vals.get("depth")), last_temp))
    d = _dive(_local_ts(dt), samples, source)
    return [d] if d else []


def parse_csv(text, source):
    rows = list(csv.reader(io.StringIO(text), delimiter=";" if text.count(";") > text.count(",") else ","))
    if len(rows) < 3:
        raise DiveLogError("CSV-filen är tom")
    head = [h.strip().lower() for h in rows[0]]

    def col(*keys):
        for i, h in enumerate(head):
            if any(k in h for k in keys):
                return i
        return None
    ci_t = col("sample time", "time", "tid")
    ci_d = col("depth", "djup")
    ci_temp = col("temp")
    ci_date = col("date", "datum")
    ci_start = None
    for i, h in enumerate(head):
        if h in ("time", "tid") and i != ci_t:
            ci_start = i
    ci_num = col("dive number", "dyk")
    if ci_t is None or ci_d is None:
        raise DiveLogError("Hittade inga kolumner för tid och djup")
    groups = {}
    for r in rows[1:]:
        if len(r) <= max(ci_t, ci_d):
            continue
        key = r[ci_num] if ci_num is not None and ci_num < len(r) else "1"
        groups.setdefault(key, []).append(r)
    dives = []
    for key, rs in groups.items():
        start = None
        if ci_date is not None:
            st = rs[0][ci_start] if ci_start is not None else "00:00:00"
            dt = _parse_dt(f"{rs[0][ci_date]} {st}")
            start = _local_ts(dt) if dt else None
        if start is None:
            raise DiveLogError("CSV-filen saknar datum och starttid för dyken")
        samples = [(_mmss(r[ci_t]) * (60 if "min" in head[ci_t] and ":" not in r[ci_t] else 1),
                    _num(r[ci_d]), _num(r[ci_temp]) if ci_temp is not None and ci_temp < len(r) else None)
                   for r in rs]
        d = _dive(start, samples, source, key)
        if d:
            dives.append(d)
    return dives


def parse_file(path):
    path = Path(path)
    raw = path.read_bytes()
    text = raw.decode("utf-8", "replace")
    if path.suffix.lower() == ".csv":
        return parse_csv(text, path.name)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        raise DiveLogError(f"Filen kunde inte läsas som dyklogg: {e}")
    tag = _strip(root.tag)
    if tag == "uddf":
        dives = parse_uddf(root, path.name)
    elif tag in ("divelog", "dives"):
        dives = parse_subsurface(root, path.name)
    else:
        dives = parse_sml(root, path.name)
    if not dives:
        raise DiveLogError("Hittade inga dyk med djupprofil i filen")
    return dives


# ---------- koppla klipp och dyk ----------

def _clip_span(c):
    t = c.get("created") or c.get("time")
    dur = float((c.get("analysis") or {}).get("duration") or c.get("duration") or 0)
    return (float(t), dur) if t else (None, dur)


def auto_offset(dives, clips):
    """Förskjutning (sekunder att lägga till klippens tid) som lägger flest undervattensklipp i dyken.
    Provar hela tidszoner (±14 h) och finjusterar sedan ±10 min."""
    spans = []
    for c in clips:
        t, dur = _clip_span(c)
        if t is None or dur <= 0:
            continue
        under = (c.get("analysis") or {}).get("underwater", True)
        spans.append((t, dur, 1.0 if under else -0.5))
    if not spans or not dives:
        return 0.0, 0.0
    iv = np.array([[d["start"], d["start"] + d["duration"]] for d in dives])

    def score(off):
        s = 0.0
        for t, dur, w in spans:
            a, b = t + off, t + off + dur
            inside = np.clip(np.minimum(b, iv[:, 1]) - np.maximum(a, iv[:, 0]), 0, None).max()
            s += w * inside
        return s
    best = (score(0.0), 0.0)
    for h in np.arange(-14, 14.5, 0.5):
        off = h * 3600
        sc = score(off)
        if sc > best[0] + 1e-6 or (abs(sc - best[0]) < 1e-6 and abs(off) < abs(best[1])):
            best = (sc, off)
    base = best[1]
    for m in np.arange(-600, 601, 15):
        off = base + m
        sc = score(off)
        if sc > best[0] + 1e-6 or (abs(sc - best[0]) < 1e-6 and abs(off - base) < abs(best[1] - base)):
            best = (sc, off)
    total = sum(dur for _, dur, w in spans if w > 0) or 1.0
    return float(best[1]), float(max(0.0, best[0]) / total)


def at(project, clip_id, t_in_clip):
    """(djup m, temperatur °C) vid en tid i klippet, eller None."""
    log = project.data.get("divelog") or {}
    dives = log.get("dives") or []
    c = project.data["clips"].get(clip_id) or {}
    t0, _ = _clip_span(c)
    if t0 is None or not dives:
        return None
    ts = t0 + float(log.get("offset", 0.0)) + t_in_clip
    for d in dives:
        if d["start"] - 30 <= ts <= d["start"] + d["duration"] + 30:
            s = np.asarray([[x[0], x[1], np.nan if x[2] is None else x[2]] for x in d["samples"]], float)
            rel = ts - d["start"]
            depth = float(np.interp(rel, s[:, 0], s[:, 1]))
            tv = s[:, 2]
            ok = ~np.isnan(tv)
            temp = float(np.interp(rel, s[ok, 0], tv[ok])) if ok.any() else None
            return max(0.0, depth), temp
    return None


def summary(project):
    log = project.data.get("divelog") or {}
    dives = log.get("dives") or []
    clips = [c for c in project.clips() if c.get("analysis")]
    matched = sum(1 for c in clips if at(project, c["id"], 0.5) is not None)
    return {
        "dives": [{"start": d["start"], "duration": d["duration"], "max_depth": d["max_depth"],
                   "min_temp": d.get("min_temp"), "number": d.get("number"),
                   "profile": [[round(x[0]), round(x[1], 1)] for x in d["samples"][:: max(1, len(d["samples"]) // 120)]]}
                  for d in dives],
        "offset": float(log.get("offset", 0.0)), "fit": float(log.get("fit", 0.0)),
        "matched": matched, "clips": len(clips), "source": log.get("source"),
        "clip_marks": [{"id": c["id"], "name": c["name"], "t": _clip_span(c)[0], "dur": _clip_span(c)[1]}
                       for c in clips if _clip_span(c)[0]],
    }


def import_log(project, path):
    dives = parse_file(path)
    clips = [c for c in project.clips() if c.get("analysis")]
    off, fit = auto_offset(dives, clips)
    from .project import project_lock
    with project_lock():  # läs, ändra och spara i ett svep
        project.reload()
        project.data["divelog"] = {"dives": dives, "offset": off, "fit": fit, "source": Path(path).name,
                                   "imported": time.time()}
        project.save()
    return summary(project)


def set_offset(project, offset=None, auto=False):
    from .project import project_lock
    with project_lock():  # läs, ändra och spara i ett svep
        project.reload()
        log = project.data.get("divelog") or {}
        if not log.get("dives"):
            raise DiveLogError("Ingen dyklogg importerad")
        if auto:
            log["offset"], log["fit"] = auto_offset(log["dives"], [c for c in project.clips() if c.get("analysis")])
        else:
            log["offset"] = float(offset)
        project.data["divelog"] = log
        project.save()
    return summary(project)
