"""Kvalitetsspärrar: vad som är tillräckligt bra för att komma med i en film.

Två nivåer:
  1. Klipp – ett klipp vars bästa sekvens är suddig, skakig eller felexponerad väljs bort
     automatiskt (med en förklaring). Användaren kan ändå tvinga in det med "Måste med".
  2. Sekvens – generatorn använder bara de delar av ett klipp där skärpan håller hela vägen.
"""

import numpy as np

# Klippnivå (gäller klippets bästa 3-sekundersdel)
CLIP_MIN_SHARP = 0.32
CLIP_MIN_EXPO = 0.35
CLIP_MIN_STAB = 0.40
CLIP_REL_QUALITY = 0.72  # andel av projektets median – svagare än så väljs bort

# Sekvensnivå (generatorn)
WIN_MIN_SHARP = 0.36      # snittskärpa i sekvensen
WIN_MIN_SHARP_LOW = 0.26  # skärpan får inte dippa under detta (fokusletande, rörelseoskärpa)
WIN_MIN_EXPO = 0.35
WIN_MIN_STAB = 0.40


def assess(clips):
    """Sätt auto_excluded och reasons på analyserade klipp. Returnerar antal bortvalda."""
    analyzed = [c for c in clips if c.get("analysis") and not c.get("is360")]
    if not analyzed:
        return 0
    qs = [c["analysis"].get("best_q", c["analysis"].get("score", 0)) for c in analyzed]
    median_q = float(np.median(qs))
    n_out = 0
    for c in analyzed:
        a = c["analysis"]
        reasons = []
        if a.get("best_sharp", 1) < CLIP_MIN_SHARP:
            reasons.append("Suddigt")
        if a.get("best_expo", 1) < CLIP_MIN_EXPO:
            reasons.append("Fel exponering")
        if a.get("best_stab", 1) < CLIP_MIN_STAB:
            reasons.append("Skakigt")
        if not reasons and len(analyzed) >= 4 and a.get("best_q", 1) < CLIP_REL_QUALITY * median_q:
            reasons.append("Svagare än resten")
        c["auto_excluded"] = bool(reasons)
        c["reasons"] = reasons
        n_out += bool(reasons)
    return n_out


def is_usable(clip) -> bool:
    if not clip.get("analysis") or clip.get("is360") or clip.get("excluded"):
        return False
    if clip.get("favorite"):
        return True
    return not clip.get("auto_excluded")
