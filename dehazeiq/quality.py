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
CLIP_REL_FOCUS = 0.6     # skärpa (brusokänslig) i förhållande till projektets median
CLIP_MIN_SUBJECT_CONF = 0.015  # AI-rutnätet hittar inget djur någonstans i bilden (bara vatten/partiklar)
CLIP_MIN_INTEREST = 0.35 # AI: sannolikhet att bilden visar något sevärt

# Sekvensnivå (generatorn)
WIN_MIN_FOCUS_RANK = 0.70      # sekvensens skärpa minst 70 % av klippets bästa
WIN_MIN_FOCUS_RANK_LOW = 0.50  # och aldrig under hälften (fokusletande, rörelseoskärpa)
WIN_MIN_INTEREST = 0.45        # AI: något sevärt i bild större delen av tiden
HIGHLIGHT_QUANTILE = 0.5       # bara den bättre hälften av alla godkända sekvenser blir film
WIN_MIN_SHARP = 0.36      # snittskärpa i sekvensen
WIN_MIN_SHARP_LOW = 0.26  # skärpan får inte dippa under detta (fokusletande, rörelseoskärpa)
WIN_MIN_EXPO = 0.35
WIN_MIN_STAB = 0.40


def assess(clips):
    """Sätt auto_excluded och reasons på analyserade klipp. Returnerar antal bortvalda."""
    analyzed = [c for c in clips if c.get("analysis") and not c.get("is360")]
    if not analyzed:
        return 0
    def combined(a):
        q = a.get("best_q", a.get("score", 0))
        if a.get("best_interest") is not None:
            q *= (0.4 + 0.6 * a["best_interest"]) * (0.7 + 0.3 * (a.get("best_beauty") or 0.5))
        return q

    median_q = float(np.median([combined(c["analysis"]) for c in analyzed]))
    foci = [c["analysis"].get("best_focus") for c in analyzed if c["analysis"].get("best_focus")]
    median_focus = float(np.median(foci)) if foci else None
    for c in analyzed:
        a = c["analysis"]
        reasons = []
        if a.get("best_sharp", 1) < CLIP_MIN_SHARP:
            reasons.append("Suddigt")
        elif (median_focus and len(analyzed) >= 3 and a.get("best_focus") is not None and not c.get("is_photo")
              and a["best_focus"] < CLIP_REL_FOCUS * median_focus):
            reasons.append("Suddigt")
        if a.get("best_expo", 1) < CLIP_MIN_EXPO:
            reasons.append("Fel exponering")
        if a.get("best_stab", 1) < CLIP_MIN_STAB:
            reasons.append("Skakigt")
        weak_loc = a.get("subject_conf") is not None and a["subject_conf"] < CLIP_MIN_SUBJECT_CONF
        if weak_loc or (a.get("best_interest") is not None and a["best_interest"] < CLIP_MIN_INTEREST):
            reasons.append("Inget tydligt motiv")
        # foton har användaren valt själv: jämförs inte med videoklippen
        if not reasons and len(analyzed) >= 4 and not c.get("is_photo") and combined(a) < CLIP_REL_QUALITY * median_q:
            reasons.append("Svagare än resten")
        c["auto_excluded"] = bool(reasons)
        c["reasons"] = reasons
    # AI:ns "inget tydligt motiv" är en bedömning, inte ett tekniskt fel: om den skulle lämna
    # för lite material (t.ex. resfilm utan djur) släpps just det kravet
    usable = [c for c in analyzed if not c["auto_excluded"]]
    if len(usable) < min(3, len(analyzed)):
        for c in analyzed:
            if "Inget tydligt motiv" in c["reasons"]:
                c["reasons"] = [r for r in c["reasons"] if r != "Inget tydligt motiv"]
                c["auto_excluded"] = bool(c["reasons"])
    return sum(1 for c in analyzed if c["auto_excluded"])


def is_usable(clip) -> bool:
    if not clip.get("analysis") or clip.get("is360") or clip.get("excluded"):
        return False
    if clip.get("favorite"):
        return True
    return not clip.get("auto_excluded")
