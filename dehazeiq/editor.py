"""Redigering av ett filmförslag i programmet: korta/förläng, hastighet, effekter, flytta,
ta bort, byta klipp mot ett liknande, flytta motivet i bilden, färg och titel – med ångra.
Dessutom: byta plattform (format och längd) och göra filmer efter vald filmtyp."""

import copy
import time
import uuid

import numpy as np

from . import generator, story
from .config import FILM_TYPES, GRADE_KEYS, LOOKS, PLATFORMS, STYLES


class EditError(Exception):
    pass


HISTORY = 25


def _snapshot(prop):
    return {"shots": copy.deepcopy(prop["shots"]), "grade": copy.deepcopy(prop.get("grade")),
            "effects": copy.deepcopy(prop.get("effects")), "title": prop.get("title")}


def _finish(prop):
    """Räkna om positioner och längd efter en ändring; gamla renderingar gäller inte längre."""
    pos = 0.0
    for s in prop["shots"]:
        s["at"] = round(pos, 3)
        pos += float(s["duration"])
    prop["length"] = round(pos, 2)
    prop["n_shots"] = len(prop["shots"])
    prop["avg_shot"] = round(pos / max(1, len(prop["shots"])), 2)
    prop["renders"] = {}
    prop["edited"] = time.time()
    prop["short"] = False
    return prop


def _clip_len(project, shot):
    c = project.data["clips"].get(shot["clip_id"]) or {}
    return float((c.get("analysis") or {}).get("duration") or c.get("duration") or 0.0)


def _fit_source(project, shot):
    """Se till att källan räcker för längd × hastighet; flytta starten bakåt om det behövs."""
    fx = shot.get("fx") or {}
    speed = float(fx.get("speed", 1.0))
    freeze = float(fx.get("freeze", 0.0))
    need = (shot["duration"] - freeze) * speed
    total = _clip_len(project, shot)
    if total and shot["src_start"] + need > total:
        new_start = max(0.0, total - need - 0.05)
        if abs(new_start - shot["src_start"]) > 1e-3:
            shot["path"] = []  # banan gällde den gamla starten
        shot["src_start"] = round(new_start, 3)
        need = min(need, total - shot["src_start"])
        if speed and need / speed + freeze < shot["duration"]:
            shot["duration"] = round(need / speed + freeze, 3)
    shot["src_end"] = round(shot["src_start"] + need, 3)


def _beat(prop):
    bpm = prop.get("bpm")
    return 60.0 / float(bpm) if bpm else None


def clean_grade(g):
    g = dict(g or {})
    out = {"look": g.get("look") if g.get("look") in LOOKS else "none",
           "strength": float(min(1.0, max(0.0, float(g.get("strength", 1.0)))))}
    for k in GRADE_KEYS:
        lo = 0.0 if k in ("sharpen", "vignette") else -1.0
        out[k] = float(min(1.0, max(lo, float(g.get(k, 0.0) or 0.0))))
    for k in ("dehaze", "particles"):  # None = AI:ns automatik
        if g.get(k) is not None:
            out[k] = float(min(1.0, max(0.0, float(g[k]))))
    if g.get("stabilize") is not None:
        out["stabilize"] = bool(g["stabilize"])
    return out


def apply(project, prop, op, args):
    """Utför en redigering. Returnerar det ändrade förslaget."""
    shots = prop["shots"]

    def shot_at():
        i = int(args.get("i", -1))
        if not 0 <= i < len(shots):
            raise EditError("Klippet finns inte")
        return i, shots[i]

    if op == "undo":
        hist = prop.get("history") or []
        if not hist:
            raise EditError("Inget att ångra")
        snap = hist.pop()
        prop["shots"], prop["grade"], prop["effects"] = snap["shots"], snap["grade"], snap["effects"]
        prop["title"] = snap["title"]
        return _finish(prop)

    hist = prop.setdefault("history", [])
    hist.append(_snapshot(prop))
    del hist[:-HISTORY]

    if op == "trim":
        i, s = shot_at()
        d = float(args.get("duration", s["duration"]))
        beat = _beat(prop)
        if beat and args.get("snap", True):
            d = max(beat, round(d / beat) * beat)
        s["duration"] = round(min(20.0, max(0.5, d)), 3)
        fx = s.setdefault("fx", {})
        if fx.get("freeze"):
            fx["freeze"] = round(min(0.9, s["duration"] * 0.4), 2)
        _fit_source(project, s)
    elif op == "speed":
        i, s = shot_at()
        fx = s.setdefault("fx", {})
        fx.pop("speed", None)
        fx.pop("freeze", None)
        mode = args.get("mode", "normal")
        if mode == "slow":
            fx["speed"] = 0.5
        elif mode == "fast":
            fx["speed"] = 2.0
        elif mode == "freeze":
            fx["freeze"] = round(min(0.9, s["duration"] * 0.4), 2)
        _fit_source(project, s)
    elif op == "fx":
        i, s = shot_at()
        fx = s.setdefault("fx", {})
        fx.pop("zoom", None)
        fx.pop("punch", None)
        eff = args.get("effect", "none")
        if eff == "zoom":
            fx["zoom"] = 0.06
        elif eff == "punch":
            fx["punch"] = 0.09
    elif op == "delete":
        i, s = shot_at()
        if len(shots) <= 1:
            raise EditError("Filmen måste ha minst ett klipp")
        shots.pop(i)
    elif op == "move":
        i, s = shot_at()
        j = max(0, min(len(shots) - 1, i + int(args.get("dir", 1))))
        shots[i], shots[j] = shots[j], shots[i]
    elif op == "center":
        i, s = shot_at()
        s["cx"] = round(float(min(1.0, max(0.0, float(args.get("cx", 0.5))))), 3)
        s["cy"] = round(float(min(1.0, max(0.0, float(args.get("cy", 0.5))))), 3)
        if not s.get("manual_center"):
            s["auto_path"] = s.get("path") or []
        s["path"] = []
        s["manual_center"] = True
    elif op == "auto_center":
        i, s = shot_at()
        if not s.get("auto_path") and not s.get("manual_center"):
            raise EditError("Klippet följer redan motivet")
        s["path"] = s.get("auto_path") or s.get("path") or []
        s.pop("manual_center", None)
    elif op == "swap":
        i, s = shot_at()
        shots[i] = _shot_from_alternative(project, prop, s, args.get("alt") or {})
    elif op == "grade":
        g = clean_grade(args.get("grade"))
        if args.get("scope") == "shot":
            i, s = shot_at()
            s["grade"] = g
        else:
            prop["grade"] = g
            if args.get("all_shots"):
                for s in shots:
                    s.pop("grade", None)
    elif op == "grade_reset_shot":
        i, s = shot_at()
        s.pop("grade", None)
    elif op == "transition":
        i, s = shot_at()
        from .effects import TRANSITIONS
        t = args.get("type", "cut")
        if t not in TRANSITIONS:
            raise EditError("Okänd övergång")
        s["tr"] = t
    elif op == "text":
        i, s = shot_at()
        text = str(args.get("text", "")).strip()[:60]
        if not text:
            s.pop("text", None)
        else:
            kind = args.get("kind") if args.get("kind") in ("label", "chapter", "pop") else "label"
            s["text"] = {"kind": kind, "text": text, "sub": str(args.get("sub", "")).strip()[:60]}
    elif op == "i18n":
        lang = args.get("lang")
        from .i18n import LANGS
        if lang not in LANGS or lang == "sv":
            raise EditError("Välj ett annat språk än svenska")
        over = prop.setdefault("i18n", {}).setdefault(lang, {})
        if "title" in args:
            over["title"] = str(args["title"]).strip()[:80]
        for k, v in (args.get("shots") or {}).items():
            over.setdefault("shots", {})[str(k)] = {"text": str(v.get("text", "")).strip()[:60],
                                                   "sub": str(v.get("sub", "")).strip()[:60]}
    elif op == "title":
        text = str(args.get("text", "")).strip()[:80]
        prop.setdefault("effects", {})["title"] = text
        if text:
            prop["title"] = text
    else:
        hist.pop()
        raise EditError(f"Okänd redigering: {op}")
    return _finish(prop)


# ---------- byt mot liknande ----------

def _cands(project, prop):
    style = STYLES[prop["style"]]
    cands, _, _ = generator._candidates_for(project, style, prop["format"], prop.get("favorites") or ())
    return cands


def _vec(c):
    for k in ("bio_emb", "subj_emb", "emb"):
        v = c.get(k)
        if v is not None:
            v = np.asarray(v, np.float32)
            return v / max(float(np.linalg.norm(v)), 1e-6)
    return None


def alternatives(project, prop, i, n=6):
    """Liknande sekvenser som inte redan används: samma djur/miljö först."""
    shots = prop["shots"]
    if not 0 <= i < len(shots):
        raise EditError("Klippet finns inte")
    cur = shots[i]
    cands = _cands(project, prop)
    used = [(s["clip_id"], s["src_start"], s["src_end"]) for s in shots]

    def overlaps(c):
        return any(cid == c["clip"]["id"] and c["start"] < e and c["end"] > s0 for cid, s0, e in used)

    me = next((c for c in cands if c["clip"]["id"] == cur["clip_id"]
               and c["start"] - 0.5 <= cur["src_start"] <= c["end"]), None)
    mv = _vec(me) if me else None
    out = []
    for c in cands:
        if overlaps(c):
            continue
        sim = 0.0
        v = _vec(c)
        if mv is not None and v is not None and len(v) == len(mv):
            sim = float(v @ mv)
        same_label = 1.0 if cur.get("label") and c.get("label") == cur.get("label") else 0.0
        score = sim + 0.15 * same_label + 0.25 * c.get("util_n", 0)
        out.append((score, c))
    out.sort(key=lambda x: -x[0])
    res = []
    for score, c in out[:n]:
        res.append({"clip_id": c["clip"]["id"], "name": c["clip"]["name"], "start": round(c["start"], 2),
                    "end": round(c["end"], 2), "label": c.get("label"), "desc": c.get("desc") or "",
                    "quality": round(c["quality"], 2), "score": round(score, 3),
                    "thumb_t": round((c["start"] + c["end"]) / 2, 1)})
    return res


def _shot_from_alternative(project, prop, old, alt):
    cands = _cands(project, prop)
    c = next((c for c in cands if c["clip"]["id"] == alt.get("clip_id")
              and abs(c["start"] - float(alt.get("start", -99))) < 0.6), None)
    if not c:
        raise EditError("Sekvensen finns inte längre – analysera om eller välj en annan")
    dur = float(old["duration"])
    start, cx, cy, path = generator._place(c, dur, prop["format"])
    clip = c["clip"]
    a = clip.get("analysis", {})
    new = {
        "clip_id": clip["id"], "name": clip["name"],
        "src_start": round(start, 3), "src_end": round(start + dur, 3), "duration": round(dur, 3), "at": old["at"],
        "cx": round(cx, 3), "cy": round(cy, 3), "path": path, "auto_path": path,
        "wb_gains": a.get("wb_gains", [1, 1, 1]), "underwater": a.get("underwater", False),
        "tags": a.get("tags", []), "label": c.get("label"), "shot": c.get("shot"), "context": c.get("context"),
        "quality": round(c["quality"], 3), "motion": round(c["motion"], 3), "favorite": bool(c.get("favorite")),
        "species": (c.get("species") or [None])[0] if c.get("species_p", 0) >= 0.35 else None,
        "desc": c.get("desc") or "", "fx": {},
    }
    if old.get("grade"):
        new["grade"] = old["grade"]
    _fit_source(project, new)
    return new


# ---------- plattform och filmtyp ----------

def platform_of(prop):
    for k, p in PLATFORMS.items():
        if prop.get("platform") == k:
            return k
    return None


def retarget(project, prop, platform, length=None, keep_id=True):
    """Samma berättelse och stil för en annan plattform (format och längd). Färg och titel följer med."""
    if platform not in PLATFORMS:
        raise EditError("Okänd plattform")
    pf = PLATFORMS[platform]
    length = float(length or pf["length"])
    music = project.data.get("music")
    new = generator.generate(project, prop["style"], pf["format"], length, prop.get("seed"), music,
                             prop.get("favorites") or (), prop.get("theme"))
    for k in ("grade", "plan", "plan_label"):
        if prop.get(k) is not None:
            new[k] = copy.deepcopy(prop[k])
    title = (prop.get("effects") or {}).get("title")
    if title and prop.get("title") == title:
        new.setdefault("effects", {})["title"] = title
        new["title"] = title
    new["platform"] = platform
    if keep_id:
        new["id"] = prop["id"]
    else:
        new["derived_from"] = prop["id"]
    return new


def _themes_by_kind(project, fmt):
    th = generator.themes(project, fmt)
    by = {}
    for t in th:
        by.setdefault(t["kind"], []).append(t)
    return th, by


def plan_proposals(project, plan, music=None, favorites=(), avoid=()):
    """Gör förslag för en filmtyp (dykfilm, resefilm, reels, djurporträtt eller AI:ns val)."""
    kind = plan.get("type", "auto")
    ft = FILM_TYPES.get(kind, FILM_TYPES["auto"])
    platform = plan.get("platform") or ft["platform"]
    pf = PLATFORMS.get(platform, PLATFORMS["reels"])
    fmt = pf["format"]
    length = float(plan.get("length") or pf["length"])
    count = int(plan.get("count") or ft["count"])
    out = []

    def add(theme, style):
        p = generator.generate(project, style, fmt, length, None, music, favorites, theme)
        out.append(p)

    if kind == "auto":
        out += generator.generate_set(project, "auto", fmt, length, music, favorites, None, avoid)
    elif kind in ("dive", "trip"):
        th, by = _themes_by_kind(project, fmt)
        if kind == "dive" and by.get("session"):
            sess = sorted(by["session"], key=lambda t: -t.get("count", 0))
            theme = sess[0]["id"]
        else:
            theme = "trip"
        styles = ["documentary", "cinematic", "calm", "action"]
        for k in range(count):
            add(theme if kind == "trip" or k < 3 or len(by.get("session", [])) < 2
                else by["session"][k % len(by["session"])]["id"], styles[k % len(styles)])
    elif kind == "animal":
        th, by = _themes_by_kind(project, fmt)
        subs = sorted(by.get("subject", []), key=lambda t: -t.get("score", 0))
        if not subs:
            subs = [{"id": "fun"}]
        styles = ["documentary", "playful", "cinematic", "action"]
        for k in range(count):
            add(subs[k % len(subs)]["id"], styles[(k // len(subs)) % len(styles)])
    elif kind == "reels":
        used = list(avoid)
        while len(out) < count:
            batch = generator.generate_set(project, "auto", fmt, length, music, favorites, None, used)
            if not batch:
                break
            for p in batch:
                if len(out) < count:
                    out.append(p)
                used.append(p["theme"])
            if len(used) > 40:
                break
    for p in out:
        p["plan"] = kind
        p["plan_label"] = ft["label"]
        p["platform"] = platform
        p["id"] = p.get("id") or uuid.uuid4().hex[:10]
    return out


def describe_plan(plan):
    ft = FILM_TYPES.get(plan.get("type", "auto"), FILM_TYPES["auto"])
    pf = PLATFORMS.get(plan.get("platform") or ft["platform"], PLATFORMS["reels"])
    n = int(plan.get("count") or ft["count"])
    return f"{ft['label']} · {n} förslag · {pf['label']}"


__all__ = ["EditError", "apply", "alternatives", "retarget", "plan_proposals", "describe_plan", "clean_grade",
           "story"]
