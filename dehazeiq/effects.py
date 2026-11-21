"""Effekter som AI:n lägger till automatiskt: övergångar, slowmotion, långsam zoom,
titel och vinjett. Planen sparas i förslaget; vilka som används styrs av
projektets inställningar (settings["effects"]) så att de kan slås av och på
utan att filmen behöver genereras om."""

import os
import sys
from pathlib import Path

EFFECTS = {
    "transitions": "Mjuka övergångar",
    "slowmo": "Slowmotion",
    "zoom": "Långsam zoom",
    "title": "Titel",
    "vignette": "Vinjett",
    "fast": "Snabbspolning",
    "freeze": "Frysbild",
    "punch": "Zoomryck",
    "labels": "Textskyltar",
    "sfx": "Ljudeffekter",
}
DEFAULT_EFFECTS = {k: True for k in EFFECTS}

TRANSITION = {"cinematic": ("fade", 0.45), "calm": ("fade", 0.7), "action": ("cut", 0.0),
              "playful": ("cut", 0.0), "documentary": ("cut", 0.0)}

# Övergångar (FFmpeg xfade) som går att välja i redigeringen, i grupper
TRANSITIONS = {
    "cut": "Rakt klipp",
    "fade": "Toning", "fadeblack": "Toning via svart", "fadewhite": "Toning via vitt", "dissolve": "Upplösning",
    "hblur": "Svisch (oskärpa)", "smoothleft": "Mjukt svep vänster", "smoothright": "Mjukt svep höger",
    "slideleft": "Skjut vänster", "slideright": "Skjut höger", "wipeleft": "Torka vänster", "wipeup": "Torka upp",
    "circleopen": "Cirkel öppnas", "circleclose": "Cirkel stängs", "zoomin": "Zooma in", "radial": "Radial",
    "pixelize": "Pixlar", "squeezeh": "Kläm", "diagtl": "Diagonal",
}
TR_DUR = {"fade": 0.5, "fadeblack": 0.8, "fadewhite": 0.6, "dissolve": 0.7, "hblur": 0.25, "smoothleft": 0.4,
          "smoothright": 0.4, "slideleft": 0.35, "slideright": 0.35, "wipeleft": 0.4, "wipeup": 0.4,
          "circleopen": 0.45, "circleclose": 0.45, "zoomin": 0.35, "radial": 0.4, "pixelize": 0.4,
          "squeezeh": 0.35, "diagtl": 0.4}
FUN_CAPTIONS = ["Vem där?", "Hallå där!", "Kolla in mig!", "Ojdå!", "Smygläge", "Här bor jag", "Hej då!",
                "Inte nu …", "Titta här!", "Wow!"]


def _dx(shot):
    """Åt vilket håll rör sig motivet/utsnittet i klippet? (−1 vänster, 1 höger, 0 stilla)"""
    path = shot.get("path") or []
    if len(path) >= 2:
        d = path[-1][1] - path[0][1]
        if abs(d) > 0.03:
            return 1 if d > 0 else -1
    return 0


def plan_transitions(shots, style_key):
    """Övergång från varje klipp till nästa. AI:n väljer efter stil, rörelse och sammanhang:
    raka klipp när motivet står på samma plats (matchklipp), svep i rörelsens riktning,
    toning via svart vid nytt dyk, och aldrig för många effektövergångar i rad."""
    n = len(shots)
    out = []
    since = 9
    fun_cycle = ["zoomin", "circleopen", "pixelize", "radial", "squeezeh", "slideleft", "diagtl"]
    for i in range(n - 1):
        a, b = shots[i], shots[i + 1]
        new_dive = a.get("session") is not None and b.get("session") is not None and a["session"] != b["session"]
        end_x = (a.get("path") or [[0, a.get("cx", .5)]])[-1][1]
        start_x = (b.get("path") or [[0, b.get("cx", .5)]])[0][1]
        match = abs(end_x - start_x) < 0.08 and a.get("label") == b.get("label")
        dx = _dx(a) or _dx(b)
        t = "cut"
        if style_key == "documentary":
            t = "fadeblack" if new_dive else ("dissolve" if (a.get("shot") == "wide" and since >= 4) else "cut")
        elif style_key == "cinematic":
            t = "fadeblack" if new_dive else ("cut" if match else "fade")
        elif style_key == "calm":
            t = "fadeblack" if new_dive else ("dissolve" if i % 2 else "fade")
        elif style_key == "action":
            if not match and since >= 3:
                t = "hblur" if dx == 0 else ("smoothright" if dx > 0 else "smoothleft")
        elif style_key == "playful":
            if not match and since >= 2:
                t = fun_cycle[i % len(fun_cycle)] if dx == 0 else ("slideright" if dx > 0 else "slideleft")
        since = 0 if t not in ("cut", "fade", "dissolve") else since + 1
        out.append(t)
    return out


def plan_texts(shots, style_key, proposal):
    """Textskyltar: artnamn första gången ett djur syns och kapitel vid nytt dyk (dokumentär),
    korta skojiga pratbubblor på frysbilder (lekfull)."""
    seen = set()
    for i, s in enumerate(shots):
        s.pop("text", None)
        if style_key == "documentary":
            if i > 0 and s.get("session") is not None and shots[i - 1].get("session") not in (None, s["session"]):
                s["text"] = {"kind": "chapter", "text": f"Dyk {int(s['session']) + 1}"}
                continue
            # artnamnet bara när artmodellen är säker, annars djurgruppen (t.ex. "Bläckfisk")
            sure = s.get("species") and s.get("species_p", 0) >= 0.6
            group = s.get("label") if s.get("label") not in (None, "Undervatten") else None
            name = s.get("species") if sure else group
            key = group or name
            if name and key not in seen and s["duration"] >= 2.5 and not s.get("context"):
                seen.add(key)
                s["text"] = {"kind": "label", "text": name, "sub": (s.get("species_sci") or "") if sure else ""}
        elif style_key == "playful":
            if (s.get("fx") or {}).get("freeze"):
                s["text"] = {"kind": "pop", "text": s.get("caption") or FUN_CAPTIONS[i % len(FUN_CAPTIONS)]}
    if style_key == "documentary":
        ts = [s.get("time") for s in shots if s.get("time")]
        if ts:
            import datetime
            months = ["januari", "februari", "mars", "april", "maj", "juni", "juli", "augusti", "september",
                      "oktober", "november", "december"]
            d = datetime.datetime.fromtimestamp(min(ts))
            proposal.setdefault("effects", {})["subtitle"] = f"{d.day} {months[d.month - 1]} {d.year}"


def plan_sfx(shots, trans, style_key):
    """Ljudeffekter: svisch vid effektövergångar, pling vid frysbild (bara lekfullt och action)."""
    if style_key not in ("playful", "action"):
        return []
    ev, pos = [], 0.0
    for i, s in enumerate(shots):
        fx = s.get("fx") or {}
        if fx.get("freeze"):
            ev.append({"t": round(pos + s["duration"] - fx["freeze"], 3), "kind": "pling"})
        pos += s["duration"]
        if i < len(trans) and trans[i] not in ("cut", "fade", "dissolve", "fadeblack"):
            ev.append({"t": round(max(0.0, pos - 0.15), 3), "kind": "whoosh"})
    return ev


def enabled(settings):
    eff = dict(DEFAULT_EFFECTS)
    eff.update({k: bool(v) for k, v in ((settings or {}).get("effects") or {}).items() if k in EFFECTS})
    return eff


def plan(proposal, clips_by_id, style_key):
    """Bestämmer effekter för ett nyss genererat förslag (ändrar shots på plats)."""
    shots = proposal["shots"]
    kind, d = TRANSITION.get(style_key, ("fade", 0.45))
    calm = style_key in ("calm", "cinematic")

    # Slowmotion: bara där källan har hög bildfrekvens (≥ 48 bps) och klippet är långt nog
    hfr = [i for i, s in enumerate(shots)
           if (clips_by_id.get(s["clip_id"]) or {}).get("fps", 30) >= 48 and s["duration"] >= 1.6]
    if style_key == "action":
        slow = sorted(hfr, key=lambda i: -(shots[i]["motion"] + shots[i]["quality"]))[:1]
    else:
        slow = sorted(hfr, key=lambda i: -shots[i]["quality"])[:max(1, len(shots) // 4)]
    # Långsam zoom: lugna översikter och halvbilder i lugna stilar
    motions = sorted(s["motion"] for s in shots)
    med = motions[len(motions) // 2] if motions else 0
    zoom = []
    if calm:
        zoom = [i for i, s in enumerate(shots)
                if i not in slow and s["duration"] >= 2.2 and s["motion"] <= med
                and s.get("shot") in ("wide", "medium", None)][:max(1, int(len(shots) * 0.4))]
    # Lekfullt och action: snabbspola en lugn, lång tagning (t.ex. en krabba som går),
    # frys det roligaste ögonblicket och ge klippen ett zoomryck på takten
    fast, freeze, punch = [], [], []
    if style_key in ("playful", "action"):
        for i, s in enumerate(shots):
            clip = clips_by_id.get(s["clip_id"]) or {}
            room = float(clip.get("duration") or 0) - s["src_start"]
            if i not in slow and s["motion"] < med and s["duration"] >= 1.5 and room >= s["duration"] * 2 + 0.2:
                fast.append(i)
        fast = fast[:1] if style_key == "action" else fast[:2]
        punch = [i for i in range(1, len(shots), 2) if i not in fast]
    if style_key == "playful" and len(shots) >= 3:
        cand = [i for i, s in enumerate(shots) if s["duration"] >= 2.0 and i not in fast and i not in slow]
        if cand:
            freeze = [max(cand, key=lambda i: shots[i]["quality"] + shots[i]["motion"])]
    for i, s in enumerate(shots):
        fx = {}
        if i in fast:
            fx["speed"] = 2.0
            s["src_end"] = round(s["src_start"] + s["duration"] * 2.0, 3)
        if i in freeze:
            fx["freeze"] = round(min(0.9, s["duration"] * 0.4), 2)
            s["src_end"] = round(s["src_start"] + s["duration"] - fx["freeze"], 3)
        if i in punch:
            fx["punch"] = 0.1 if style_key == "action" else 0.07
        if i in slow:
            fps = (clips_by_id.get(s["clip_id"]) or {}).get("fps", 60)
            fx["speed"] = 0.4 if fps >= 100 else 0.5
            # källan som används blir kortare: dur * speed
            s["src_end"] = round(s["src_start"] + s["duration"] * fx["speed"], 3)
        if i in zoom:
            fx["zoom"] = 0.07 if style_key == "calm" else 0.05
        s["fx"] = fx
    trans = plan_transitions(shots, style_key)
    for i, s in enumerate(shots):
        s["tr"] = trans[i] if i < len(trans) else None
    plan_texts(shots, style_key, proposal)
    proposal["effects"] = {
        "transition": kind, "transition_d": d,
        "title": proposal.get("title") or "",
        "vignette": style_key == "cinematic",
        "subtitle": (proposal.get("effects") or {}).get("subtitle", ""),
        "sfx": plan_sfx(shots, trans, style_key),
    }
    return proposal


def describe(proposal, settings):
    """Kort text till förslagskortet: vilka effekter som faktiskt används."""
    on = enabled(settings)
    fx = proposal.get("effects") or {}
    out = []
    if on["transitions"] and fx.get("transition") == "fade":
        out.append("mjuka övergångar")
    n_slow = sum(1 for s in proposal["shots"] if 0 < (s.get("fx") or {}).get("speed", 1) < 1)
    n_zoom = sum(1 for s in proposal["shots"] if (s.get("fx") or {}).get("zoom"))
    if on["slowmo"] and n_slow:
        out.append(f"slowmotion ×{n_slow}")
    if on["zoom"] and n_zoom:
        out.append(f"zoom ×{n_zoom}")
    if on["title"] and fx.get("title"):
        out.append("titel")
    if on["vignette"] and fx.get("vignette"):
        out.append("vinjett")
    for key, name in (("fast", "snabbspolning"), ("freeze", "frysbild"), ("punch", "zoomryck")):
        n = sum(1 for s in proposal["shots"] if (s.get("fx") or {}).get("speed" if key == "fast" else key)
                and (key != "fast" or (s.get("fx") or {}).get("speed", 1) > 1))
        if on[key] and n:
            out.append(name)
    return out


_FONT_CANDIDATES = {
    "win": ["segoeuib.ttf", "seguisb.ttf", "arialbd.ttf", "arial.ttf"],
    "mac": ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf",
            "/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/SFNS.ttf"],
    "other": ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"],
}


def title_font():
    if sys.platform.startswith("win"):
        root = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        paths = [root / n for n in _FONT_CANDIDATES["win"]]
    elif sys.platform == "darwin":
        paths = [Path(p) for p in _FONT_CANDIDATES["mac"]]
    else:
        paths = [Path(p) for p in _FONT_CANDIDATES["other"]]
    return next((p for p in paths if p.exists()), None)
