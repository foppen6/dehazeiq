"""Berättelser: teman och dramaturgi.

I stället för att bara plocka de bästa sekvenserna bygger DeHazeIQ filmer kring ett tema:

  Djurporträtt  – en film om ett motiv (t.ex. sköldpaddan): öppningsbild → översikt/halvbild
                  → närbilder → höjdpunkt → avsked (motivet simmar bort eller översikt)
  Dyket         – ett dyk i tidsordning: yta/nedstigning → dykets höjdpunkter → yta
  Resan         – kapitel per dyk/dag, med samma motiv samlade, i tidsordning

Teman hittas automatiskt ur AI-analysen (motiv per sekvens) och klippens tidsstämplar
(sessioner = klipp tagna nära varandra i tid).
"""

from datetime import datetime

import numpy as np

from . import ai

SESSION_GAP = 40 * 60  # sekunder mellan klipp som räknas som ett nytt dyk/tillfälle
MONTHS = ["jan", "feb", "mars", "april", "maj", "juni", "juli", "aug", "sep", "okt", "nov", "dec"]

# Etiketter som kan bära en egen film (motiv). Övriga är miljö/sammanhang.
SUBJECT_LABELS = {
    "Sköldpadda", "Dykare", "Fiskstim", "Fisk", "Haj", "Rocka", "Bläckfisk", "Manet", "Muräna",
    "Nakensnäcka", "Krabba och hummer", "Sjöhäst", "Säl och delfin", "Vrak", "Grotta",
    "Rev och koraller", "Kelp och tång",
}
PORTRAIT_TITLE = {
    "Sköldpadda": "Sköldpaddan", "Dykare": "Dykarna", "Fiskstim": "Fiskstimmen", "Fisk": "Fiskarna",
    "Haj": "Hajen", "Rocka": "Rockan", "Bläckfisk": "Bläckfisken", "Manet": "Maneterna",
    "Muräna": "Muränan", "Nakensnäcka": "Nakensnäckorna", "Krabba och hummer": "Kräftdjuren",
    "Sjöhäst": "Sjöhästen", "Säl och delfin": "Sälarna och delfinerna", "Vrak": "Vraket",
    "Grotta": "Grottan", "Rev och koraller": "Revet", "Kelp och tång": "Kelpskogen",
}


# ---------- sessioner ----------

def sessions(clips):
    """Grupperar klipp efter tid. Returnerar {clip_id: session_nr} och en lista med sessionsinfo."""
    ordered = sorted(clips, key=lambda c: c.get("created") or 0)
    sid, last, out, info = 0, None, {}, []
    for c in ordered:
        t = c.get("created") or 0
        end = t + (c.get("duration") or 0)
        if last is None or t - last > SESSION_GAP:
            sid += 1
            info.append({"id": sid, "start": t, "clips": [], "underwater": 0})
        out[c["id"]] = sid
        info[-1]["clips"].append(c["id"])
        info[-1]["underwater"] += 1 if (c.get("analysis") or {}).get("underwater") else 0
        last = max(last or 0, end)
    days = {datetime.fromtimestamp(s["start"]).date() for s in info if s["start"]}
    for s in info:
        dt = datetime.fromtimestamp(s["start"]) if s["start"] else None
        kind = "Dyk" if s["underwater"] * 2 >= len(s["clips"]) else "Ovan ytan"
        when = ""
        if dt:
            when = f"{dt.day} {MONTHS[dt.month - 1]} {dt:%H:%M}" if len(days) > 1 else f"{dt:%H:%M}"
        s["kind"] = kind
        s["title"] = f"{kind} {s['id']}" + (f" · {when}" if when else "")
    return out, info


# ---------- semantik per sekvens ----------

def annotate(cands, clips_by_id):
    """Lägger till motiv, bildutsnitt, sammanhang och session på varje kandidatsekvens."""
    sess_of, _ = sessions(list(clips_by_id.values()))
    model = ai.get()
    for c in cands:
        c["session"] = sess_of.get(c["clip"]["id"], 1)
        c["label"], c["label_p"], c["shot"], c["context"] = None, 0.0, "medium", None
        d = c["data"]
        if model is None or "emb" not in d or "tag_probs" not in d:
            # Utan AI: bara undervatten/ovan ytan som sammanhang
            if not (c["clip"].get("analysis") or {}).get("underwater"):
                c["context"] = "surface"
            continue
        et = d["emb_t"]
        m = (et >= c["start"] - 0.5) & (et <= c["end"] + 0.5)
        if not m.any():
            m = np.zeros(len(et), bool)
            m[int(np.argmin(np.abs(et - (c["start"] + c["end"]) / 2)))] = True
        emb = d["emb"][m].astype(np.float32)
        probs = d["tag_probs"][m].astype(np.float32).mean(axis=0)
        best = int(np.argmax(probs))
        c["label"], c["label_p"] = model.labels[best], float(probs[best])
        t = model.text
        if all(k in t for k in ("closeup", "medium", "wide")):
            sims = np.stack([(emb @ t[g].T).max(axis=1).mean() for g in ("closeup", "medium", "wide")])
            p = np.exp((sims - sims.max()) * 100.0)
            p /= p.sum()
            c["shot"] = ("close", "medium", "wide")[int(np.argmax(p))]
        groups = [g for g in ("subject", "surface", "descent", "leaving") if g in t]
        if len(groups) > 1:
            sims = np.array([(emb @ t[g].T).max(axis=1).mean() for g in groups])
            p = np.exp((sims - sims.max()) * 100.0)
            p /= p.sum()
            g = groups[int(np.argmax(p))]
            if g != "subject" and p.max() > 0.45:
                c["context"] = g
    return cands


# ---------- teman ----------

def find_themes(cands, clips_by_id):
    """Vilka filmer går att berätta med det här materialet? Sorterat efter hur bra de blir."""
    _, sinfo = sessions(list(clips_by_id.values()))
    themes = []
    by_label = {}
    for c in cands:
        if c.get("label") in SUBJECT_LABELS and c.get("label_p", 0) >= 0.25 and not c.get("context"):
            by_label.setdefault(c["label"], []).append(c)
    for label, cs in by_label.items():
        n_clips = len({c["clip"]["id"] for c in cs})
        if len(cs) >= 3 and n_clips >= 2:
            score = sum(c["util_n"] for c in cs)
            themes.append({"id": f"subject:{label}", "kind": "subject", "label": label,
                           "title": PORTRAIT_TITLE.get(label, label), "count": len(cs),
                           "clips": n_clips, "score": score})
    if len(sinfo) > 1:
        for s in sinfo:
            cs = [c for c in cands if c.get("session") == s["id"]]
            if len(cs) >= 3:
                themes.append({"id": f"session:{s['id']}", "kind": "session", "title": s["title"],
                               "count": len(cs), "clips": len(s["clips"]),
                               "score": sum(c["util_n"] for c in cs) * 0.9})
    themes.sort(key=lambda t: -t["score"])
    themes.append({"id": "trip", "kind": "trip",
                   "title": "Resans höjdpunkter" if len(sinfo) > 1 else "Dykets höjdpunkter",
                   "count": len(cands), "clips": len({c["clip"]["id"] for c in cands}), "score": 0})
    return themes


def auto_plan(themes):
    """Tre olika berättelser när användaren låter AI välja."""
    subj = [t for t in themes if t["kind"] == "subject"]
    sess = [t for t in themes if t["kind"] == "session"]
    trip = [t for t in themes if t["kind"] == "trip"]
    picks = []
    if subj:
        picks.append((subj[0], "cinematic"))
    if sess:
        picks.append((sess[0], "cinematic" if not picks else "calm"))
    elif len(subj) > 1:
        picks.append((subj[1], "calm"))
    picks.append((trip[0], "action"))
    for st in ("cinematic", "calm", "action"):  # för lite material för tre teman: fler stilar av resan
        if len(picks) >= 3:
            break
        if all(not (t is trip[0] and s == st) for t, s in picks):
            picks.append((trip[0], st))
    return picks[:3]


# ---------- dramaturgi ----------

def _has(items, c):
    """Identitetsjämförelse (sekvenserna innehåller numpy-data som inte kan jämföras med ==)."""
    return any(x is c for x in items)


def _context_pick(ctx_pool, kinds, session=None, before=None, after=None, exclude=()):
    best = None
    for c in ctx_pool:
        if c.get("context") not in kinds or _has(exclude, c):
            continue
        if session is not None and c.get("session") != session:
            continue
        if before is not None and c["time"] > before:
            continue
        if after is not None and c["time"] < after:
            continue
        if best is None or c["util_n"] > best["util_n"]:
            best = c
    return best


def _top(pool, n):
    """Höjdpunkter inom temat: den bättre halvan, men minst n sekvenser om det finns."""
    if len(pool) <= n:
        return list(pool)
    ranked = sorted(pool, key=lambda c: -c["util_n"])
    med = float(np.median([c["util_n"] for c in pool]))
    keep = [c for c in ranked if c["util_n"] >= med]
    return keep if len(keep) >= n else ranked[:n]


def build(theme, cands, ctx_pool, n, select):
    """Väljer och ordnar sekvenser för ett tema. select(pool, k) väljer k sekvenser med variation."""
    kind = theme["kind"]
    _sel = select
    select = lambda pool, k: _sel(_top(pool, k), k)  # noqa: E731
    if kind == "subject":
        pool = [c for c in cands if c.get("label") == theme["label"] and c.get("label_p", 0) >= 0.2]
        if len(pool) < 2:
            pool = cands
        # Håll ihop berättelsen: helst ett och samma dyk
        sess_count = {}
        for c in pool:
            sess_count[c["session"]] = sess_count.get(c["session"], 0) + 1
        main_sess = max(sess_count, key=sess_count.get)
        same = [c for c in pool if c["session"] == main_sess]
        if len(same) >= max(3, n - 2):
            pool = same
        body = select(pool, max(1, n - 2))
        order = {"wide": 0, "medium": 1, "close": 2}
        leaving = [c for c in body if c.get("context") == "leaving"]
        rest = [c for c in body if not _has(leaving, c)]
        # översikt/halvbild först, närbilder i mitten, höjdpunkt (mest rörelse + skönhet) mot slutet
        rest.sort(key=lambda c: (order.get(c.get("shot"), 1), c["time"]))
        if len(rest) >= 3:
            peak = max(rest, key=lambda c: c["motion"] + c["util_n"])
            rest = [c for c in rest if c is not peak]
            rest.insert(max(1, int(round(0.7 * len(rest)))), peak)
        first_t = min(c["time"] for c in body)
        last_t = max(c["time"] for c in body)
        opener = _context_pick(ctx_pool, ("descent", "surface"), main_sess, before=first_t, exclude=body) \
            or _context_pick(ctx_pool, ("descent", "surface"), main_sess, exclude=body)
        closer = leaving[:1] or [x for x in [_context_pick(ctx_pool, ("leaving",), main_sess, exclude=body)] if x]
        seq = ([opener] if opener else []) + rest + leaving[1:] + closer
        if not closer and not (seq and seq[-1].get("shot") == "wide"):
            wide_end = _context_pick(ctx_pool, ("surface",), main_sess, after=last_t, exclude=seq)
            if wide_end:
                seq.append(wide_end)
        return _dedupe(seq)

    if kind == "session":
        sid = int(theme["id"].split(":")[1])
        pool = [c for c in cands if c["session"] == sid] or cands
        body = sorted(select(pool, max(1, n - 2)), key=lambda c: c["time"])
        opener = _context_pick(ctx_pool, ("surface", "descent"), sid, before=body[0]["time"], exclude=body)
        closer = _context_pick(ctx_pool, ("surface",), sid, after=body[-1]["time"], exclude=body)
        return _dedupe(([opener] if opener else []) + body + ([closer] if closer else []))

    # Resan: kapitel per session, samma motiv samlat, tidsordning
    sess_ids = sorted({c["session"] for c in cands})
    weight = {s: sum(c["util_n"] for c in cands if c["session"] == s) for s in sess_ids}
    total_w = sum(weight.values()) or 1.0
    seq = []
    for s in sess_ids:
        k = max(1, int(round((n - 1) * weight[s] / total_w)))
        part = select([c for c in cands if c["session"] == s and not _has(seq, c)], k)
        first_seen = {}
        for c in part:  # samma motiv samlas där det först dyker upp
            first_seen[c.get("label")] = min(first_seen.get(c.get("label"), c["time"]), c["time"])
        part = sorted(part, key=lambda c: (first_seen[c.get("label")], c["time"]))
        seq += part
    first = seq[0]["time"] if seq else None
    opener = _context_pick(ctx_pool, ("surface", "descent"), sess_ids[0], before=first, exclude=seq) if seq else None
    if opener:
        seq.insert(0, opener)
    return _dedupe(seq)


def _dedupe(seq):
    out = []
    for c in seq:
        if c is None or _has(out, c):
            continue
        if any(c["clip"]["id"] == o["clip"]["id"] and not (c["end"] <= o["start"] or c["start"] >= o["end"])
               for o in out):
            continue
        out.append(c)
    return out


THEME_TEXT = {
    "subject": "Porträtt av ett motiv: från översikt till närbilder och ett avsked.",
    "session": "Ett dyk i tidsordning, från ytan till uppstigningen.",
    "trip": "De bästa ögonblicken, kapitel för kapitel i tidsordning.",
}
