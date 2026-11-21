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
    bio = ai.get_bio() if model else None
    for c in cands:
        c["session"] = sess_of.get(c["clip"]["id"], 1)
        c["label"], c["label_p"], c["shot"], c["context"] = None, 0.0, "medium", None
        c["closeness"] = 0.0
        c["fun"], c["calm_p"], c["subj_emb"], c["subj_conf"] = 0.0, 0.5, None, 0.0
        c["species"], c["species_p"], c["bio_emb"], c["desc"], c["role"] = None, 0.0, None, "", None
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
        # Etiketter räknas om från inbäddningarna med de aktuella beskrivningarna
        probs = model.label_probs(emb).mean(axis=0)
        c["subj_emb"] = None
        if "loc_emb" in d and len(d["loc_t"]):
            lt = d["loc_t"]
            lm = (lt >= c["start"] - 1.0) & (lt <= c["end"] + 1.0)
            if not lm.any():
                lm = np.zeros(len(lt), bool)
                lm[int(np.argmin(np.abs(lt - (c["start"] + c["end"]) / 2)))] = True
            le = d["loc_emb"][lm].astype(np.float32)
            # utsnittet med djuret säger mer än hela bilden
            probs = 0.35 * probs + 0.65 * model.label_probs(le).mean(axis=0)
            v = le.mean(axis=0)
            c["subj_emb"] = v / max(float(np.linalg.norm(v)), 1e-6)
            c["subj_conf"] = float(d["loc_conf"][lm].mean())
            fun = model.group_prob(le, "funny", "plain")
            c["fun"] = float(fun.mean()) if fun is not None else 0.0
        else:
            fun = model.group_prob(emb, "funny", "plain")
            c["fun"] = float(fun.mean()) if fun is not None else 0.0
        calm = model.group_prob(emb, "calm", "action")
        c["calm_p"] = float(calm.mean()) if calm is not None else 0.5
        best = int(np.argmax(probs))
        c["label"], c["label_p"] = model.labels[best], float(probs[best])
        t = model.text
        if all(k in t for k in ("closeup", "medium", "wide")):
            sims = np.stack([(emb @ t[g].T).max(axis=1).mean() for g in ("closeup", "medium", "wide")])
            p = np.exp((sims - sims.max()) * 100.0)
            p /= p.sum()
            c["shot"] = ("close", "medium", "wide")[int(np.argmax(p))]
            c["closeness"] = float(sims[0] - sims[2])  # relativt mått: >0 närmare, <0 vidare
        groups = [g for g in ("subject", "surface", "descent", "leaving") if g in t]
        if len(groups) > 1:
            sims = np.array([(emb @ t[g].T).max(axis=1).mean() for g in groups])
            p = np.exp((sims - sims.max()) * 100.0)
            p /= p.sum()
            g = groups[int(np.argmax(p))]
            if g != "subject" and p.max() > 0.45:
                c["context"] = g
        _annotate_species(c, d, bio, model)
    for c in cands:
        _annotate_vlm(c, bio)
    return cands


def _annotate_species(c, d, bio, model):
    """Art med BioCLIP på utsnittet med djuret (analysversion 3)."""
    if not bio or "bio_emb" not in d or "loc_t" not in d or not len(d["loc_t"]):
        return
    lt = d["loc_t"]
    m = (lt >= c["start"] - 1.0) & (lt <= c["end"] + 1.0)
    if not m.any():
        m = np.zeros(len(lt), bool)
        m[int(np.argmin(np.abs(lt - (c["start"] + c["end"]) / 2)))] = True
    e = d["bio_emb"][m].astype(np.float32)
    if e.shape[1] != bio.text.shape[1]:
        return
    v = e.mean(axis=0)
    c["bio_emb"] = v / max(float(np.linalg.norm(v)), 1e-6)
    p = bio.probs(e).mean(axis=0)
    i = int(np.argmax(p))
    c["species"], c["species_p"] = bio.species[i], float(p[i])
    # Gruppnivå (summan över arterna i gruppen) är stabilare än enskild art
    gp = {}
    for row, pi in zip(bio.species, p):
        gp[row[4]] = gp.get(row[4], 0.0) + float(pi)
    group = max(gp, key=gp.get)
    c["bio_group"], c["bio_group_p"] = group, gp[group]
    if gp[group] >= 0.5 and not c.get("context") and model and group in model.labels:
        c["label"], c["label_p"] = group, max(c["label_p"], gp[group])


def _annotate_vlm(c, bio):
    """Djupanalysens beskrivningar (Qwen3-VL): vad händer, hur roligt, hur vackert, skärpa."""
    frames = ((c["clip"].get("vlm") or {}).get("frames")) or []
    if not frames:
        return
    near = [f for f in frames if c["start"] - 1.0 <= f["t"] <= c["end"] + 1.0]
    if not near:
        f = min(frames, key=lambda f: abs(f["t"] - (c["start"] + c["end"]) / 2))
        if abs(f["t"] - (c["start"] + c["end"]) / 2) > 3.0:
            return
        near = [f]
    act = float(np.mean([f["action"] for f in near])) / 10
    fun = float(np.mean([f["fun"] for f in near])) / 10
    beauty = float(np.mean([f["beauty"] for f in near])) / 10
    sharp = float(np.mean([1.0 if f.get("sharp", True) else 0.0 for f in near]))
    best = max(near, key=lambda f: f["action"] + f["fun"] + f["beauty"])
    c["desc"] = best.get("what", "")
    c["vlm_action"], c["vlm_beauty"], c["vlm_sharp"] = act, beauty, sharp
    c["fun"] = 0.4 * c.get("fun", 0.0) + 0.6 * fun
    roles = [f.get("role") for f in near]
    c["role"] = max(set(roles), key=roles.count)
    # Bättre urval: vackrare och skarpare sekvenser väger tyngre
    if "util_n" in c:
        c["util_n"] *= (0.75 + 0.5 * beauty) * (0.6 if sharp == 0 else 1.0)
    # Arten från beskrivningen, om artmodellen var osäker
    sp = (best.get("species") or "").strip().lower()
    if bio and sp and c.get("species_p", 0) < 0.5:
        for row in bio.species:
            if row[2].lower() == sp:
                c["species"], c["species_p"] = row, 0.5
                break


# ---------- teman ----------

def same_animal(cs, margin=0.035, extra=()):
    """Behåll bara sekvenser där det är samma sorts djur. AI-etiketten kan blanda ihop t.ex.
    en dvärgbläckfisk med en knot eller ett kammanet, men utsnitten av djuret ser olika ut:
    jämför varje sekvens med medelbilden av de säkraste och släng de som avviker."""
    key = "bio_emb" if cs and all(c.get("bio_emb") is not None for c in cs) else "subj_emb"
    with_emb = [c for c in cs if c.get(key) is not None]
    if len(with_emb) < 4:
        return cs
    E = np.stack([c[key] for c in with_emb])
    p = np.array([c.get("label_p", 0) for c in with_emb])
    # kärnan: de som liknar flest andra (det vanligaste djuret), med etikettens säkerhet som tillägg
    dens = (E @ E.T).mean(axis=1)
    score = dens + 0.1 * p
    seed = score >= np.median(score)
    keep = np.ones(len(with_emb), bool)
    for _ in range(3):
        ref = E[seed & keep] if (seed & keep).any() else E[keep]
        cen = ref.mean(axis=0)
        cen /= max(float(np.linalg.norm(cen)), 1e-6)
        sim = E @ cen
        thr = float(np.median(sim[seed & keep] if (seed & keep).any() else sim)) - margin
        new = sim >= thr
        if new.sum() < 3 or (new == keep).all():
            break
        keep = new
    for c, k, sv in zip(with_emb, keep, sim):
        c["animal_sim"] = float(sv)
    kept = [c for c, k in zip(with_emb, keep) if k]
    # sekvenser där AI:n var osäker på arten men djuret ser likadant ut tas också med
    for c in extra:
        if c.get(key) is None or c.get("context") or any(c is k for k in kept) \
                or any(c is k for k in with_emb):
            continue
        if float(c[key] @ cen) >= thr + 0.01:
            c["animal_sim"] = float(c[key] @ cen)
            kept.append(c)
    return kept + [c for c in cs if c.get(key) is None]


def _share(cands, k=None):
    return k or max(2, int(np.ceil(len(cands) * 0.5)))


def closest(cands, k=None):
    """Närbilderna – relativt resten av materialet, så att temat finns även om allt är halvbild."""
    picked = [c for c in cands if c.get("shot") == "close"]
    rest = sorted((c for c in cands if not _has(picked, c)), key=lambda c: -c.get("closeness", 0))
    return (picked + rest)[:max(len(picked), _share(cands, k))]


def widest(cands, k=None):
    picked = [c for c in cands if c.get("shot") == "wide" or c.get("context") in ("surface", "descent")]
    rest = sorted((c for c in cands if not _has(picked, c)), key=lambda c: c.get("closeness", 0))
    return (picked + rest)[:max(len(picked), _share(cands, k))]


def funniest(cands, k=None):
    """Nyfikna djur som tittar in i kameran, oväntade ögonblick (AI) – plus lite rörelse."""
    if not any(c.get("fun") for c in cands):
        return []
    ranked = sorted(cands, key=lambda c: -(c.get("fun", 0) + 0.25 * c["motion"]))
    return [c for c in ranked if c.get("fun", 0) >= 0.7][:_share(cands, k)]


def calmest(cands, k=None):
    ranked = sorted(cands, key=lambda c: -(c.get("calm_p", 0.5) - 0.6 * c["motion"]))
    return [c for c in ranked if c["motion"] < 0.5][:_share(cands, k)]


def most_moving(cands, k=None):
    return sorted(cands, key=lambda c: -c["motion"])[:_share(cands, k)]


def find_themes(cands, clips_by_id):
    """Vilka filmer går att berätta med det här materialet? Sorterat efter hur bra de blir."""
    _, sinfo = sessions(list(clips_by_id.values()))
    themes = []
    by_label = {}
    for c in cands:
        if c.get("label") in SUBJECT_LABELS and c.get("label_p", 0) >= 0.22 and not c.get("context"):
            by_label.setdefault(c["label"], []).append(c)
    # Arter (BioCLIP/djupanalys): en film per art när artmodellen är säker
    by_species = {}
    for c in cands:
        sp = c.get("species")
        if sp and c.get("species_p", 0) >= 0.5 and not c.get("context"):
            by_species.setdefault(sp[2], []).append(c)
    covered = set()
    for sci, cs in by_species.items():
        cs = same_animal(cs)
        sp = cs[0]["species"]
        group_n = sum(1 for c in cands if c.get("label") == sp[4] and not c.get("context"))
        # bara när arten dominerar sin grupp – annars är artnamnet troligen en gissning
        if len(cs) >= 3 and len(cs) >= 0.6 * max(1, group_n):
            themes.append({"id": f"subject:{sci}", "kind": "subject", "label": sp[4], "species": sci,
                           "title": sp[1], "count": len(cs), "clips": len({c["clip"]["id"] for c in cs}),
                           "score": sum(c["util_n"] for c in cs) * 1.05})
            covered.add(sp[4])
    for label in list(by_label):
        by_label[label] = same_animal(by_label[label], extra=cands)
    for label, cs in by_label.items():
        n_clips = len({c["clip"]["id"] for c in cs})
        if len(cs) >= 3 and label not in covered:
            score = sum(c["util_n"] for c in cs)
            themes.append({"id": f"subject:{label}", "kind": "subject", "label": label,
                           "title": PORTRAIT_TITLE.get(label, label), "count": len(cs),
                           "clips": n_clips, "score": score})
    for s in sinfo:
        cs = [c for c in cands if c.get("session") == s["id"]]
        if len(cs) >= 3:
            title = s["title"] if len(sinfo) > 1 else ("Dyket i tidsordning" if s["kind"] == "Dyk" else "I tidsordning")
            themes.append({"id": f"session:{s['id']}", "kind": "session", "title": title,
                           "count": len(cs), "clips": len(s["clips"]),
                           "score": sum(c["util_n"] for c in cs) * 0.9})
    underwater = sum(1 for c in clips_by_id.values() if (c.get("analysis") or {}).get("underwater"))
    mostly_under = underwater * 2 >= max(1, len(clips_by_id))
    enough = len(cands) >= 4
    extra = [
        ("detail", "Detaljer och färger", closest(cands) if enough else [], 0.8),
        ("blue", "Det stora blå" if mostly_under else "Miljöerna", widest(cands) if enough else [], 0.7),
        ("motion", "I rörelse", most_moving(cands) if enough else [], 0.6),
        ("fun", "Roliga ögonblick", funniest(cands) if enough else [], 0.75),
        ("calm", "Lugna stunder", calmest(cands) if enough else [], 0.55),
    ]
    for kind, title, cs, w in extra:
        if len(cs) >= 2:
            themes.append({"id": kind, "kind": kind, "title": title, "count": len(cs),
                           "clips": len({c["clip"]["id"] for c in cs}),
                           "score": sum(c["util_n"] for c in cs) * w})
    themes.sort(key=lambda t: -t["score"])
    themes.append({"id": "trip", "kind": "trip",
                   "title": "Resans höjdpunkter" if len(sinfo) > 1 else "Dykets höjdpunkter",
                   "count": len(cands), "clips": len({c["clip"]["id"] for c in cands}), "score": 0})
    return themes


STYLE_FOR = {"subject": "cinematic", "session": "cinematic", "trip": "action",
             "detail": "calm", "blue": "calm", "motion": "action", "fun": "playful", "calm": "calm"}
KIND_PRIORITY = ["subject", "fun", "session", "detail", "motion", "calm", "blue", "trip"]
ALL_STYLES = ("cinematic", "calm", "action", "playful")


def auto_plan(themes, avoid=(), rng=None):
    """Tre OLIKA berättelser när användaren låter AI välja. Teman som användes senast (avoid)
    hamnar sist, så att varje ny generering ger något nytt."""
    rng = rng or np.random.default_rng()
    avoid = set(avoid)
    # Högst en av varje sort först, i prioritetsordning med lite slump, sedan resten
    by_kind = {}
    for t in themes:
        by_kind.setdefault(t["kind"], []).append(t)
    order = sorted(by_kind, key=lambda k: KIND_PRIORITY.index(k) + rng.uniform(0, 1.6))
    candidates = []
    for k in order:
        ts = sorted(by_kind[k], key=lambda t: (t["id"] in avoid, -t["score"]))
        candidates.append(ts[0])
    for k in order:
        candidates += [t for t in by_kind[k][1:]]
    candidates.sort(key=lambda t: t["id"] in avoid)  # stabil sortering: nya teman först
    picks, used_styles = [], set()
    for t in candidates:
        if len(picks) == 3:
            break
        st = STYLE_FOR.get(t["kind"], "cinematic")
        if st in used_styles:  # variera även stilen
            st = next((x for x in ALL_STYLES if x not in used_styles), st)
        picks.append((t, st))
        used_styles.add(st)
    trip = by_kind.get("trip", [themes[-1]])[0]
    for st in ("cinematic", "calm", "action"):  # för lite material: fler stilar av samma berättelse
        if len(picks) >= 3:
            break
        if all(s != st for _, s in picks):
            picks.append((trip, st))
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
        if c.get("subj_conf", 0) > 0.026:  # tydligt (annat) djur i bild – inte en miljöbild
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
        if theme.get("species"):
            pool = same_animal([c for c in cands if (c.get("species") or [None] * 3)[2] == theme["species"]
                                and c.get("species_p", 0) >= 0.3])
        else:
            pool = same_animal([c for c in cands if c.get("label") == theme["label"]
                                and c.get("label_p", 0) >= 0.2], extra=cands)
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
        roles = {"intro": 0, "calm": 1, "detail": 1, "action": 2, "climax": 3}
        if any(c.get("role") for c in rest):
            # djupanalysen vet vad som händer: lugn inledning → handling → klimax
            rest.sort(key=lambda c: (roles.get(c.get("role"), 2), order.get(c.get("shot"), 1), c["time"]))
        else:
            rest.sort(key=lambda c: (order.get(c.get("shot"), 1), c["time"]))
        if len(rest) >= 3:
            peak = max(rest, key=lambda c: c["motion"] + c["util_n"] + c.get("vlm_action", 0) + c.get("fun", 0)
                       + (0.5 if c.get("role") == "climax" else 0))
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

    if kind == "detail":
        pool = closest(cands, max(n, 2)) or cands
        body = select(pool, max(1, n - 1))
        first_seen = {}
        for c in body:
            first_seen[c.get("label")] = min(first_seen.get(c.get("label"), c["time"]), c["time"])
        body = sorted(body, key=lambda c: (first_seen[c.get("label")], c["time"]))
        sess = body[0]["session"] if body else None
        opener = next((c for c in sorted(cands, key=lambda c: -c["util_n"])
                       if c.get("shot") in ("wide", "medium") and c.get("session") == sess and not _has(body, c)), None)
        return _dedupe(([opener] if opener else []) + body)

    if kind == "blue":
        pool = _dedupe(widest(cands, max(n, 2)) + [c for c in ctx_pool if c.get("context") in ("surface", "descent")])
        body = sorted(select(pool or cands, n), key=lambda c: c["time"])
        desc = [c for c in body if c.get("context") == "descent"]
        surf = [c for c in body if c.get("context") == "surface"]
        mid = [c for c in body if not _has(desc, c) and not _has(surf, c)]
        return _dedupe(surf[:1] + desc + mid + surf[1:])

    if kind == "fun":
        pool = funniest(cands, max(n, 2)) or cands
        body = select(pool, n)
        # uppbyggnad: lugnare först, det roligaste mot slutet – men samma djur hålls ihop
        key = lambda c: c.get("fun", 0) + 0.25 * c["motion"]  # noqa: E731
        peak = {}
        for c in body:
            peak[c.get("label")] = max(peak.get(c.get("label"), 0), key(c))
        return _dedupe(sorted(body, key=lambda c: (peak[c.get("label")], key(c))))

    if kind == "calm":
        pool = calmest(cands, max(n, 2)) or cands
        body = sorted(select(pool, n), key=lambda c: c["time"])
        return _dedupe(body)

    if kind == "motion":
        pool = most_moving(cands, max(n, 2))
        body = select(pool, n)
        return _dedupe(sorted(body, key=lambda c: c["motion"]))  # stegras mot det mest intensiva

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
    "detail": "Närbilder: färger, mönster och små detaljer, samlade per motiv.",
    "blue": "Stämning och miljö: vida vyer, ljus och vatten.",
    "motion": "Fart och rörelse som trappas upp mot det mest intensiva.",
    "fun": "Nyfikna djur och oväntade ögonblick, lekfullt klippt med fartfyllda effekter.",
    "calm": "Stilla stunder: djur som vilar, långsamma tagningar och lugn rytm.",
}
