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
}
DEFAULT_EFFECTS = {k: True for k in EFFECTS}

TRANSITION = {"cinematic": ("fade", 0.45), "calm": ("fade", 0.7), "action": ("cut", 0.0)}


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
    for i, s in enumerate(shots):
        fx = {}
        if i in slow:
            fps = (clips_by_id.get(s["clip_id"]) or {}).get("fps", 60)
            fx["speed"] = 0.4 if fps >= 100 else 0.5
            # källan som används blir kortare: dur * speed
            s["src_end"] = round(s["src_start"] + s["duration"] * fx["speed"], 3)
        if i in zoom:
            fx["zoom"] = 0.07 if style_key == "calm" else 0.05
        s["fx"] = fx
    proposal["effects"] = {
        "transition": kind, "transition_d": d,
        "title": proposal.get("title") or "",
        "vignette": style_key == "cinematic",
    }
    return proposal


def describe(proposal, settings):
    """Kort text till förslagskortet: vilka effekter som faktiskt används."""
    on = enabled(settings)
    fx = proposal.get("effects") or {}
    out = []
    if on["transitions"] and fx.get("transition") == "fade":
        out.append("mjuka övergångar")
    n_slow = sum(1 for s in proposal["shots"] if (s.get("fx") or {}).get("speed"))
    n_zoom = sum(1 for s in proposal["shots"] if (s.get("fx") or {}).get("zoom"))
    if on["slowmo"] and n_slow:
        out.append(f"slowmotion ×{n_slow}")
    if on["zoom"] and n_zoom:
        out.append(f"zoom ×{n_zoom}")
    if on["title"] and fx.get("title"):
        out.append("titel")
    if on["vignette"] and fx.get("vignette"):
        out.append("vinjett")
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
