"""Dykets berättelse: början och slut hamnar på rätt plats.

Vissa klipp hör till en bestämd del av dyket:
  - början: på båten, i vattnet vid ytan, nedstigning längs linan
  - slutet: dykaren skjuter upp en boj (SMB/DSMB), säkerhetsstopp, uppstigning, huvudet ovanför ytan
Sådana klipp får bara ligga först respektive sist i en film om dyket (aldrig mitt i), och de
tas inte med i filmer om ett djur, detaljer, rörelse eller roliga ögonblick.

Fasen avgörs av bildinnehållet (CLIP-textdelen jämför med beskrivningar av varje fas) och
av tiden: var i dyket klippet är taget, och om det är ovan eller under ytan.
"""

import numpy as np

END = ["a scuba diver inflating an orange surface marker buoy underwater",
       "a diver holding a long orange inflatable buoy above their head",
       "a yellow delayed surface marker buoy rising towards the surface",
       "divers ascending slowly towards the bright water surface",
       "a diver doing a safety stop holding a rope in blue water",
       "a diver's head bobbing at the water surface after a dive"]
START = ["divers descending down a rope into the blue water",
         "a diver jumping into the sea from a boat",
         "divers preparing scuba gear on a boat deck",
         "a diver floating at the surface before descending"]
NEUTRAL = ["a scuba diver swimming close to the sea floor",
           "a close-up photo of a sea creature on the sand",
           "fish swimming over a reef", "an underwater scene with sand and rocks",
           "an octopus or cuttlefish on the seabed", "a crab on the sea floor"]

STORY_KINDS = ("session", "trip", "dive", "search")  # teman där början/slut får vara med
_cache = {}


def _qvs():
    if "q" not in _cache:
        from . import cliptext
        enc = cliptext.get()
        if not enc:
            _cache["q"] = None
        else:
            _cache["q"] = tuple(np.array([enc.embed(t) for t in g]) for g in (END, START, NEUTRAL))
    return _cache["q"]


def _window_emb(c):
    d = c["data"]
    if "emb" not in d:
        return None
    t = np.asarray(d["emb_t"], float)
    m = (t >= c["start"] - 0.2) & (t <= c["end"] + 0.2)
    e = np.asarray(d["emb"], np.float32)[m] if m.any() else np.asarray(d["emb"], np.float32)
    return e


def annotate(cands):
    """Sätter c["phase"] = "start" | "end" | None på kandidatsekvenserna."""
    q = _qvs()
    sess = {}
    for c in cands:
        sess.setdefault(c.get("session"), []).append(c)
    for group in sess.values():
        times = [c["time"] for c in group]
        t0, t1 = min(times), max(times)
        span = max(1.0, t1 - t0)
        # var i sessionen tar undervattensdelen slut/börjar?
        uw = [c["time"] for c in group if (c["clip"].get("analysis") or {}).get("underwater")]
        uw0, uw1 = (min(uw), max(uw)) if uw else (t0, t1)
        for c in group:
            pos = (c["time"] - t0) / span
            above = not (c["clip"].get("analysis") or {}).get("underwater")
            score_end = score_start = 0.0
            e = _window_emb(c) if q else None
            if e is not None and len(e):
                se = (e @ q[0].T).max(axis=1)
                ss = (e @ q[1].T).max(axis=1)
                sn = (e @ q[2].T).max(axis=1)
                score_end = float(np.max(se - sn))
                score_start = float(np.max(ss - sn))
            c["phase_scores"] = (round(score_end, 4), round(score_start, 4))
            phase = None
            manual = c["clip"].get("phase_manual")
            if manual in ("start", "end", "mid"):
                c["phase"] = None if manual == "mid" else manual  # användaren har bestämt
                continue
            if above and uw and c["time"] > uw1:
                phase = "end"            # ovan ytan efter dyket
            elif above and uw and c["time"] < uw0:
                phase = "start"          # ovan ytan före dyket
            elif score_end > 0.03 or (score_end > 0.012 and pos >= 0.6):
                phase = "end"            # boj, säkerhetsstopp, uppstigning
            elif score_start > 0.03 or (score_start > 0.012 and pos <= 0.3):
                phase = "start"
            c["phase"] = phase
    return cands


def arrange(seq, theme_kind, style_key, keep_min=3):
    """Ordnar om ett färdigt urval: början först, slutet sist (i tidsordning).
    I filmer som inte berättar om dyket tas sådana klipp bort."""
    if not seq:
        return seq
    phased = [c for c in seq if c.get("phase")]
    if not phased:
        return seq
    story = theme_kind in STORY_KINDS and not str(style_key).startswith(("mv_", "promo_")) \
        and style_key not in ("musicvideo", "trailer")
    if not story:
        rest = [c for c in seq if not c.get("phase")]
        return rest if len(rest) >= min(keep_min, len(seq)) else seq
    starts = sorted([c for c in seq if c.get("phase") == "start"], key=lambda c: c["time"])
    ends = sorted([c for c in seq if c.get("phase") == "end"], key=lambda c: c["time"])
    mid = [c for c in seq if not c.get("phase")]
    return starts + mid + ends
