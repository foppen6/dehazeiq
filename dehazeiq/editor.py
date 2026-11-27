"""Redigering av ett filmförslag i programmet: korta/förläng, hastighet, effekter, flytta,
ta bort, byta klipp mot ett liknande, flytta motivet i bilden, färg och titel – med ångra.
Dessutom: byta plattform (format och längd) och göra filmer efter vald filmtyp."""

import copy
import re
import time
import uuid

import numpy as np

from . import generator, story
from .config import FILM_TYPES, GRADE_KEYS, LOOKS, MV_STYLES, PLATFORMS, PROMO_STYLES, SOCIAL_STYLES, STYLES


class EditError(Exception):
    pass


HISTORY = 25


MUSIC_KEYS = ("music", "music_name", "bpm", "music_track", "music_auto", "music_license", "music_credit",
              "music_genre")


def _snapshot(prop):
    return {"shots": copy.deepcopy(prop["shots"]), "grade": copy.deepcopy(prop.get("grade")),
            "effects": copy.deepcopy(prop.get("effects")), "title": prop.get("title"),
            "overlays": copy.deepcopy(prop.get("overlays")), "match": copy.deepcopy(prop.get("match")),
            "musicinfo": {k: copy.deepcopy(prop.get(k)) for k in MUSIC_KEYS}}


def set_music(project, prop, m):
    """Byter låt i ett förslag men behåller klippen. Klippgränserna flyttas till närmaste taktslag
    i den nya låten (högst knappt en halv sekund), så att filmen fortfarande klipps i takt."""
    for k in MUSIC_KEYS:
        prop.pop(k, None)
    prop["music"] = m.get("path") if m else None
    if not m:
        return prop
    prop.update(music_name=m.get("name"), bpm=m.get("bpm"), music_track=m.get("track_id"),
                music_auto=bool(m.get("auto")), music_license=m.get("license"),
                music_credit=m.get("credit") or "", music_genre=m.get("genre") or "")
    beats = sorted(float(b) for b in (m.get("beats") or []))
    if len(beats) > 4:
        arr = np.asarray(beats)
        pos = 0.0
        for s in prop["shots"]:
            end = pos + float(s["duration"])
            j = int(abs(arr - end).argmin())
            b = float(arr[j])
            if abs(b - end) <= 0.45 and b - pos >= 0.6:
                s["duration"] = round(b - pos, 3)
                fx = s.get("fx") or {}
                if fx.get("freeze"):
                    fx["freeze"] = round(min(0.9, s["duration"] * 0.4), 2)
                _fit_source(project, s)
            pos += float(s["duration"])
    return prop


def _finish(prop):
    """Räkna om positioner och längd efter en ändring; gamla renderingar gäller inte längre."""
    from .texts import ensure_uids
    ensure_uids(prop)
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
        if "overlays" in snap:
            prop["overlays"] = snap["overlays"] or []
        if "match" in snap:
            if snap["match"] is None:
                prop.pop("match", None)
            else:
                prop["match"] = snap["match"]
        if "musicinfo" in snap:
            for k, v in snap["musicinfo"].items():
                if v is None:
                    prop.pop(k, None)
                else:
                    prop[k] = v
            if "music" not in prop:
                prop["music"] = None
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
    elif op == "music":
        from . import musiclib
        tid = str(args.get("track") or "auto")
        if tid == "none":
            m = None
        elif tid == "auto":
            st = STYLES.get(prop.get("style")) or {}
            m = musiclib.pick(prop.get("style"), prop.get("length") or 30, commercial=bool(st.get("promo")),
                              avoid=[prop.get("music_track")] if prop.get("music_track") else ())
            if not m:
                raise EditError("Musikbiblioteket har ingen annan låt som passar. Lägg till fler under Musik.")
        else:
            m = musiclib.track_music(tid)
            if not m:
                raise EditError("Låten finns inte längre i biblioteket")
            m["auto"] = False
        set_music(project, prop, m)
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
        fx.pop("kenburns", None)
        eff = args.get("effect", "none")
        if eff == "kb_in":
            fx["kenburns"] = 0.10
        elif eff == "kb_out":
            fx["kenburns"] = -0.10
        elif eff == "zoom":
            fx["zoom"] = 0.06
        elif eff == "punch":
            fx["punch"] = 0.09
    elif op in ("split", "trim_in", "trim_out"):
        # vid tidslinjemarkören: dela klippet (S), kapa början (Q) eller slutet (W)
        i, s = shot_at()
        from .texts import ensure_uids
        ensure_uids(prop)
        dur = float(s["duration"])
        at = round(float(args.get("at", dur / 2)), 3)
        if not 0.25 <= at <= dur - 0.25:
            raise EditError("Ställ markören minst en kvarts sekund in i klippet")
        fx = s.setdefault("fx", {})
        speed = float(fx.get("speed", 1.0))
        path = [list(k) for k in (s.get("path") or []) if isinstance(k, (list, tuple)) and len(k) >= 3]
        ovs = [o for o in (prop.get("overlays") or []) if o.get("shot_uid") == s["uid"]]
        if op == "trim_out":
            s["duration"] = at
            fx.pop("freeze", None)
            s["path"] = [k for k in path if k[0] <= at] or path[:1]
            _fit_source(project, s)
        elif op == "trim_in":
            s["src_start"] = round(float(s["src_start"]) + at * speed, 3)
            s["duration"] = round(dur - at, 3)
            s["path"] = [[round(k[0] - at, 3)] + k[1:] for k in path if k[0] >= at] or ([[0.0] + path[-1][1:]] if path else [])
            for o in ovs:
                o["offset"] = round(max(0.0, float(o.get("offset", 0)) - at), 3)
            _fit_source(project, s)
        else:
            b = copy.deepcopy(s)
            b["uid"] = uuid.uuid4().hex[:8]
            s["duration"] = at
            s["fx"].pop("freeze", None)
            s["tr"] = "cut"
            s["path"] = [k for k in path if k[0] <= at] or path[:1]
            _fit_source(project, s)
            b["src_start"] = round(float(b["src_start"]) + at * speed, 3)
            b["duration"] = round(dur - at, 3)
            b["path"] = [[round(k[0] - at, 3)] + k[1:] for k in path if k[0] >= at] or ([[0.0] + path[-1][1:]] if path else [])
            b.pop("edited", None)
            _fit_source(project, b)
            for o in ovs:  # texter efter delningen följer med andra halvan
                if float(o.get("offset", 0)) >= at:
                    o["shot_uid"] = b["uid"]
                    o["offset"] = round(float(o["offset"]) - at, 3)
            shots.insert(i + 1, b)
    elif op == "delete":
        i, s = shot_at()
        if len(shots) <= 1:
            raise EditError("Filmen måste ha minst ett klipp")
        shots.pop(i)
    elif op == "move":
        i, s = shot_at()
        if args.get("to") is not None:  # dra och släpp: flytta klippet till en ny plats
            j = max(0, min(len(shots) - 1, int(args["to"])))
            shots.insert(j, shots.pop(i))
        else:
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
    elif op == "fit":
        # inpassning: zoom 1 = fyller bilden (beskärning), lägre = zooma ut med bakgrund, högre = tajtare
        from .render import FIT_BG
        targets = shots if args.get("all") else [shot_at()[1]]
        for s in targets:
            if args.get("auto"):
                s.pop("fit", None)
                c = next((x for x in _cands(project, prop) if x["clip"]["id"] == s["clip_id"]
                          and x["start"] - 0.5 <= s["src_start"] <= x["end"]), None)
                f = generator.auto_fit(c, s["src_start"], s["duration"], prop["format"]) if c else None
                if f:
                    s["fit"] = f
                continue
            f = dict(s.get("fit") or {"zoom": 1.0, "bg": "blur"})
            if args.get("zoom") is not None:
                f["zoom"] = round(max(0.0, min(1.8, float(args["zoom"]))), 3)
            if args.get("bg") is not None:
                bg = str(args["bg"])
                if bg not in FIT_BG and not re.fullmatch(r"#?[0-9A-Fa-f]{6}", bg):
                    raise EditError("Okänd bakgrund")
                f["bg"] = bg if bg in FIT_BG else "0x" + bg.lstrip("#")
            f.pop("auto", None)
            if abs(f["zoom"] - 1.0) < 0.01:
                s.pop("fit", None)
            else:
                s["fit"] = f
            s["edited"] = True
    elif op == "match":
        # färgmatchning: på/av, referensklipp (index eller "auto"), styrka, hoppa över ett klipp
        from . import texts
        texts.ensure_uids(prop)
        m = dict(prop.get("match") or {"on": True, "ref": None, "strength": 0.7})
        if "on" in args:
            m["on"] = bool(args["on"])
        if "strength" in args:
            m["strength"] = round(max(0.0, min(1.0, float(args["strength"]))), 2)
        if args.get("ref") == "auto":
            m["ref"] = None
        elif args.get("ref") is not None:
            r = int(args["ref"])
            if not 0 <= r < len(shots):
                raise EditError("Klippet finns inte")
            m["ref"] = shots[r]["uid"]
            m["on"] = True
            shots[r].pop("nomatch", None)
        if "skip" in args:
            i, s = shot_at()
            if args["skip"]:
                s["nomatch"] = True
            else:
                s.pop("nomatch", None)
        prop["match"] = m
    elif op == "materialize":
        from . import texts
        if not texts.materialize(prop):
            hist.pop()  # inget att göra: ingen ångra-punkt
    elif op == "speech_text":
        # rätta eller ta bort en talundertext (gäller klippet i hela projektet)
        clip = project.data["clips"].get(args.get("clip_id"))
        segs = ((clip or {}).get("speech") or {}).get("segments") or []
        k = int(args.get("k", -1))
        if not 0 <= k < len(segs):
            raise EditError("Repliken finns inte")
        segs = [dict(x) for x in segs]
        if args.get("delete") or not str(args.get("text", "")).strip():
            segs.pop(k)
        else:
            segs[k]["text"] = str(args["text"]).strip()[:200]
        project.update_clip(clip["id"], speech=dict(clip["speech"], segments=segs))
        project.reload()
        hist.pop()  # gäller klippet, inte filmen: ingen ångra-punkt
    elif op == "cover":
        i, s = shot_at()
        prop["cover"] = {"i": i, "at": round(max(0.0, min(0.99, float(args.get("at", 0.45)))), 3)}
    elif op == "auto_center":
        i, s = shot_at()
        if not s.get("auto_path") and not s.get("manual_center"):
            raise EditError("Klippet följer redan motivet")
        s["path"] = s.get("auto_path") or s.get("path") or []
        s.pop("manual_center", None)
    elif op == "swap":
        i, s = shot_at()
        shots[i] = _shot_from_alternative(project, prop, s, args.get("alt") or {})
    elif op == "insert":  # sekvens från klippbanken in på en plats i filmen
        j = max(0, min(len(shots), int(args.get("at", len(shots)))))
        alt = args.get("alt") or {}
        beat = _beat(prop)
        avail = float(alt.get("end", 0)) - float(alt.get("start", 0))
        d = float(args.get("duration") or (beat * 4 if beat else 2.0))
        if beat:
            while d > max(avail, 1.0) and d > beat * 2:
                d -= beat * 2
        d = round(min(max(0.8, d), max(avail, 0.8), 8.0), 3)
        new = _shot_from_alternative(project, prop, {"duration": d, "at": 0.0}, alt)
        shots.insert(j, new)
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
    elif op in ("overlay_add", "overlay_update", "overlay_delete", "overlay_suggest", "overlay_clear"):
        from . import texts
        texts.ensure_uids(prop)
        ov = prop.setdefault("overlays", [])
        if op == "overlay_add":
            i, s = shot_at()
            ov.append(texts.new_item(s["uid"], args.get("text") or "Ny text", args.get("style", "caption"),
                                     args.get("sub", ""), args.get("offset", 0.3),
                                     args.get("dur", min(2.6, max(1.0, float(s["duration"]) - 0.3))),
                                     **{k: args[k] for k in ("anim", "x", "y", "size", "color", "font", "box")
                                        if k in args}))
        elif op == "overlay_update":
            it = next((x for x in ov if x["id"] == args.get("id")), None)
            if not it:
                raise EditError("Texten finns inte")
            if "text" in args:
                it["text"] = str(args["text"]).strip()[:160]
            if "sub" in args:
                it["sub"] = str(args["sub"]).strip()[:120]
            texts.clean_look(it, args)
            if args.get("style") in texts.TEXT_STYLES:
                it["style"] = args["style"]
            if args.get("offset") is not None:
                it["offset"] = max(0.0, float(args["offset"]))
            if args.get("dur") is not None:
                it["dur"] = max(0.6, min(15.0, float(args["dur"])))
            if args.get("i") is not None:  # flytta texten till ett annat klipp
                it["shot_uid"] = shots[max(0, min(len(shots) - 1, int(args["i"])))]["uid"]
        elif op == "overlay_delete":
            prop["overlays"] = [x for x in ov if x["id"] != args.get("id")]
        elif op == "overlay_clear":
            if args.get("auto_only"):
                prop["overlays"] = [x for x in ov if not x.get("auto")]
            else:
                prop["overlays"] = []
        else:  # AI föreslår texter i vald ton
            got, how = texts.suggest(prop, args.get("tone", "doc"))
            if args.get("replace", True):
                prop["overlays"] = got
                for s_ in shots:  # de automatiska klipptexterna ersätts av förslaget
                    s_.pop("text", None)
            else:
                prop["overlays"] = ov + got
            prop["overlay_tone"] = args.get("tone", "doc")
            prop["overlay_how"] = how
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
    elif op == "promo":
        # reklamens egna texter: läggs in i efterhand, kan återanvändas i alla reklamförslag
        pts = args.get("points") or []
        if isinstance(pts, str):
            pts = pts.splitlines()
        promo = {
            "hook": str(args.get("hook") or "").strip()[:120],
            "points": [str(x).strip()[:80] for x in pts if str(x).strip()][:6],
            "cta": str(args.get("cta") or "").strip()[:80],
            "url": str(args.get("url") or "").strip()[:80],
            "logo": str(args.get("logo") or "").strip(),
            "endcard": bool(args.get("endcard", True)),
        }
        prop["promo"] = promo  # "alla förslag" och "senast använda" sköts av pipeline.edit_proposal
    elif op == "cam360":
        # 360-klipp: vy ur källan (AI-vy, liten planet, kristallkula, 360-svep), riktning, bildvinkel, roll
        i, s = shot_at()
        if not s.get("parent360"):
            raise EditError("Klippet kommer inte från en 360-kamera")
        mode = args.get("mode", (s.get("cam360") or {}).get("mode", "ai"))
        if mode not in ("ai", "view", "planet", "ball", "whip"):
            raise EditError("Okänd vy")
        cam = {"mode": mode, "manual": True}
        if args.get("yaw") is not None:
            cam["yaw"] = max(-180.0, min(180.0, float(args["yaw"])))
        elif (s.get("cam360") or {}).get("yaw"):
            cam["yaw"] = s["cam360"]["yaw"]
        if args.get("fov") is not None:
            f = float(args["fov"])
            if abs(f - 104) > 1:
                cam["fov"] = max(60.0, min(150.0, f))
        elif (s.get("cam360") or {}).get("fov"):
            cam["fov"] = s["cam360"]["fov"]
        if mode == "ai" and (cam.get("yaw") or cam.get("fov")):
            cam["mode"] = "view"
        s["cam360"] = cam
        fx = s.setdefault("fx", {})
        if args.get("roll") is not None:
            if args["roll"]:
                fx["roll"] = 1
            else:
                fx.pop("roll", None)
    elif op == "lyrics":
        lines = args.get("lines") or []
        if isinstance(lines, str):
            lines = lines.splitlines()
        prop["lyrics"] = {"lines": [str(x).rstrip()[:90] for x in lines][:80],
                          "start": max(0.0, float(args.get("start") or 0.0)),
                          "beats_per_line": max(1, min(32, int(args.get("beats_per_line") or 8)))}
    elif op == "title":
        text = str(args.get("text", "")).strip()[:80]
        prop.setdefault("effects", {})["title"] = text
        if text:
            prop["title"] = text
    else:
        hist.pop()
        raise EditError(f"Okänd redigering: {op}")
    # markera ändrade klipp i tidslinjen
    if op in SHOT_OPS and args.get("i") is not None and 0 <= int(args["i"]) < len(shots):
        if not (op == "grade" and args.get("scope") != "shot"):
            shots[int(args["i"])]["edited"] = True
    return _finish(prop)


SHOT_OPS = {"trim", "split", "trim_in", "trim_out", "speed", "fx", "center", "auto_center", "swap", "grade", "grade_reset_shot", "transition",
            "text", "cam360", "fit", "overlay_add"}


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


def bank(project, prop, n=60):
    """Klippbanken: alla bra sekvenser som inte redan finns i filmen, bäst först."""
    cands = _cands(project, prop)
    used = [(s["clip_id"], s["src_start"], s["src_end"]) for s in prop["shots"]]
    out = []
    for c in sorted(cands, key=lambda c: -(c.get("quality", 0) + 0.25 * c.get("util_n", 0))):
        if any(cid == c["clip"]["id"] and c["start"] < e and c["end"] > s0 for cid, s0, e in used):
            continue
        out.append({"clip_id": c["clip"]["id"], "name": c["clip"]["name"], "start": round(c["start"], 2),
                    "end": round(c["end"], 2), "label": c.get("label"), "desc": c.get("desc") or "",
                    "quality": round(c["quality"], 2), "thumb_t": round((c["start"] + c["end"]) / 2, 1)})
        if len(out) >= n:
            break
    return out


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
    f = generator.auto_fit(c, start, dur, prop["format"])
    if old.get("fit") and not old["fit"].get("auto"):
        new["fit"] = dict(old["fit"])  # användarens egen inpassning följer med
    elif f:
        new["fit"] = f
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
    if music is None and prop.get("music_track"):
        from . import musiclib
        music = musiclib.track_music(prop["music_track"])  # samma låt som förslaget hade
    new = generator.generate(project, prop["style"], pf["format"], length, prop.get("seed"), music,
                             prop.get("favorites") or (), prop.get("theme"))
    if "promo" in prop or prop.get("prompt"):
        new["title"] = prop.get("title") or new.get("title")
    for k in ("grade", "plan", "plan_label", "promo", "lyrics", "prompt", "i18n"):
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


VARIETY_DEFAULT = {"auto": "focus", "reels": "focus", "social": "variants", "animal": "focus", "prompt": "variants",
                   "dive": "variants", "trip": "variants", "promo": "variants", "trailer": "variants",
                   "musicvideo": "variants"}
KIND_STYLES = {
    "auto": ["cinematic", "documentary", "playful", "action", "calm"],
    "reels": ["playful", "action", "cinematic", "vlog"],
    "animal": ["documentary", "playful", "cinematic", "action"],
    "dive": ["documentary", "cinematic", "calm", "action"],
    "trip": ["cinematic", "documentary", "vlog", "action"],
    "prompt": ["cinematic", "documentary", "playful"],
    "promo": PROMO_STYLES, "musicvideo": MV_STYLES, "trailer": ["trailer"],
    "social": SOCIAL_STYLES,
}


def focus_themes(project, fmt, kind, avoid=()):
    """Olika fokus: teman med olika innehåll, varierade mellan sorter (djur, detaljer, dyk, rörelse …)."""
    th, by = _themes_by_kind(project, fmt)
    big = lambda ts: sorted([t for t in ts if t.get("count", 3) >= 2], key=lambda t: -t.get("score", 0))  # noqa: E731
    if kind == "animal":
        order = big(by.get("subject", [])) + big(by.get("species", [])) + big(by.get("fun", [])) + big(by.get("detail", []))
    elif kind == "dive":
        sess = sorted([t for t in by.get("session", []) if t.get("count", 3) >= 3], key=lambda t: -t.get("count", 0))
        order = sess + [t for k in ("subject", "detail", "calm", "motion", "fun") for t in big(by.get(k, []))]
    else:
        # en av varje sort först (bästa), sedan resten – olika filmer, inte samma film i olika färger
        kinds = sorted(by, key=lambda k: -max(t.get("score", 0) for t in by[k]))
        order = [sorted(by[k], key=lambda t: -t.get("score", 0))[0] for k in kinds]
        order += [t for k in kinds for t in sorted(by[k], key=lambda t: -t.get("score", 0))[1:]]
    order = [t for t in order if t["id"] not in avoid] + [t for t in order if t["id"] in avoid]
    seen, out = set(), []
    for t in order:
        if t["id"] not in seen:
            seen.add(t["id"])
            out.append(t)
    return out


def variants_of(project, prop, count=3, music=None):
    """Fler varianter av samma film: samma tema och i stort sett samma klipp, andra stilar."""
    pf = PLATFORMS.get(prop.get("platform") or "", None)
    fmt = prop.get("format") or (pf or PLATFORMS["reels"])["format"]
    length = float(prop.get("target_length") or prop.get("length") or 30)
    pool = KIND_STYLES.get(prop.get("plan") or "", None) or ["cinematic", "documentary", "playful", "calm", "action",
                                                              "vintage", "widescreen", "vlog"]
    styles = [x for x in pool if x != prop.get("style")] or pool
    favs = list(dict.fromkeys(s["clip_id"] for s in prop.get("shots", [])))
    out = []
    for k in range(count):
        p = generator.generate(project, styles[k % len(styles)], fmt, length, None, music, favs, prop.get("theme"))
        for key in ("plan", "plan_label", "platform", "promo", "lyrics", "prompt"):
            if prop.get(key) is not None:
                p[key] = prop[key]
        if prop.get("title") and ("promo" in prop or prop.get("prompt")):
            p["title"] = prop["title"]
        p["variant_of"] = prop["id"]
        out.append(p)
    return out


def plan_proposals(project, plan, music=None, favorites=(), avoid=()):
    """Gör förslag för en filmtyp (dykfilm, resefilm, reels, djurporträtt eller AI:ns val).
    plan["variety"]: "focus" = olika filmer med olika fokus, "variants" = varianter av samma film."""
    kind = plan.get("type", "auto")
    variety = plan.get("variety") or VARIETY_DEFAULT.get(kind, "focus")
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

    query = (plan.get("query") or "").strip()
    q_theme = generator.search_theme(query, plan.get("title")) if query else None
    styles = [x for x in (plan.get("styles") or []) if x in STYLES]
    sty = styles or KIND_STYLES.get(kind, KIND_STYLES["auto"])
    if variety == "variants" and kind in ("auto", "reels", "animal", "dive", "trip", "social"):
        # samma film i flera varianter: ett tema, samma klipp, olika stilar (tempo, färg, musik)
        th, by = _themes_by_kind(project, fmt)
        if q_theme:
            theme = q_theme
        elif kind == "dive" and by.get("session"):
            theme = sorted(by["session"], key=lambda t: -t.get("count", 0))[0]["id"]
        elif kind == "animal" and by.get("subject"):
            theme = sorted(by["subject"], key=lambda t: -t.get("score", 0))[0]["id"]
        elif kind == "trip" or not th:
            theme = "trip"
        else:
            theme = focus_themes(project, fmt, kind, avoid)[0]["id"]
        add(theme, sty[0])
        favs = list(dict.fromkeys(list(favorites) + [s_["clip_id"] for s_ in out[0]["shots"]]))
        for k in range(1, count):
            p = generator.generate(project, sty[k % len(sty)], fmt, length, None, music, favs, theme)
            out.append(p)
        kind_done = True
    elif variety == "focus" and kind not in ("auto", "reels", "animal") and not q_theme:
        # olika filmer: varje variant får eget fokus (promo, musikvideo, trailer, dyk, resa)
        fts = focus_themes(project, fmt, kind, avoid)
        for k in range(count):
            theme = fts[k % len(fts)]["id"] if fts else None
            add(theme, sty[k % len(sty)])
            if kind in ("promo", "trailer"):
                out[-1]["promo"] = {}
        kind_done = True
    else:
        kind_done = False
    if kind_done:
        pass
    elif kind == "promo":
        for k in range(count):
            st = (styles or PROMO_STYLES)[k % len(styles or PROMO_STYLES)]
            add(q_theme, st)
            out[-1]["promo"] = {}
            if not q_theme:
                out[-1]["title"] = "Reklamfilm"
    elif kind == "trailer":
        for k in range(count):
            add(q_theme, (styles or ["trailer"])[k % len(styles or ["trailer"])])
            out[-1]["promo"] = {}
    elif kind == "musicvideo":
        for k in range(count):
            add(q_theme, (styles or MV_STYLES)[k % len(styles or MV_STYLES)])
    elif kind == "prompt" or (q_theme and kind not in ("trailer",)):
        sts = styles or {"reels": ["playful", "action", "cinematic"], "animal": ["documentary", "playful", "cinematic"],
                         "dive": ["documentary", "cinematic", "calm"]}.get(kind, ["cinematic", "documentary", "playful"])
        for k in range(count):
            add(q_theme, sts[k % len(sts)])
    elif kind == "auto":
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
        if plan.get("prompt"):
            p["prompt"] = plan["prompt"]
        if q_theme and plan.get("title"):
            p["title"] = plan["title"]
            if (p.get("effects") or {}).get("title"):
                p["effects"]["title"] = plan["title"]
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
