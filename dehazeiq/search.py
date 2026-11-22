"""Sök i materialet med egna ord ("båtdäck", "dykare med lampa", "solnedgång") och gör film av träffarna.

Använder bildinbäddningarna som analysen redan sparat (helbild och utsnittet runt motivet),
så sökningen går på någon sekund även i stora projekt. Kräver CLIP:s textdel (cliptext).
"""

import numpy as np

from . import cliptext


class SearchError(RuntimeError):
    pass


def query_vec(text):
    enc = cliptext.get()
    if not enc:
        raise SearchError("Sökningen kräver AI-modellpaketet (textdelen saknas)")
    parts = [p.strip() for p in str(text).replace("+", ",").split(",") if p.strip()]
    if not parts:
        raise SearchError("Skriv vad du letar efter")
    return [enc.query(p) for p in parts]


def _sample_scores(d, qvs):
    """Likhet per prov i klippet (max över sökorden, max av helbild och motivutsnitt)."""
    if "emb" not in d:
        return None, None
    t = np.asarray(d["emb_t"], float)
    emb = np.asarray(d["emb"], np.float32)
    s = np.max([emb @ q for q in qvs], axis=0)
    if "loc_emb" in d and len(d["loc_t"]):
        lt = np.asarray(d["loc_t"], float)
        ls = np.max([np.asarray(d["loc_emb"], np.float32) @ q for q in qvs], axis=0)
        # närmaste motivutsnitt för varje prov
        idx = np.clip(np.searchsorted(lt, t), 0, len(lt) - 1)
        s = np.maximum(s, ls[idx] - 0.005)
    return t, s


def search(project, text, limit=24):
    """Bästa ögonblicken för sökordet: [{clip_id, name, t, score, strong}]."""
    qvs = query_vec(text)
    hits, every = [], []
    for c in project.clips():
        if not c.get("analysis") or c.get("is360") or c.get("excluded"):
            continue
        try:
            with np.load(project.npz_path(c["id"])) as d:
                t, s = _sample_scores(d, qvs)
        except (OSError, KeyError, ValueError):
            continue
        if t is None or not len(t):
            continue
        every.append(s)
        i = int(np.argmax(s))
        hits.append({"clip_id": c["id"], "name": c["name"], "t": round(float(t[i]), 2),
                     "score": float(s[i]), "photo": bool(c.get("is_photo")),
                     "weak": bool(c.get("auto_excluded"))})
    if not hits:
        return {"query": text, "hits": [], "available": True}
    allv = np.concatenate(every)
    mu, sd = float(allv.mean()), float(allv.std() + 1e-6)
    top = max(h["score"] for h in hits)
    for h in hits:
        z = (h["score"] - mu) / sd
        h["strong"] = bool(z >= 1.6 and h["score"] >= top - 0.03)
        h["match"] = round(float(np.clip((z - 0.5) / 2.5, 0, 1)), 2)  # 0–1 för gränssnittet
        h["score"] = round(h["score"], 4)
    hits.sort(key=lambda h: -h["score"])
    return {"query": text, "hits": hits[:limit], "available": True}


def score_candidates(cands, qvs):
    """Sätter c["q"] (likhet med sökorden) på generatorns sekvenser."""
    for c in cands:
        d = c["data"]
        t, s = _sample_scores(d, qvs)
        if t is None:
            c["q"] = 0.0
            continue
        m = (t >= c["start"] - 0.25) & (t <= c["end"] + 0.25)
        c["q"] = float(s[m].max()) if m.any() else float(s.max()) - 0.02
    return cands


def pick(cands, n):
    """Sekvenserna som matchar sökorden: tydligt över mängden, minst några stycken."""
    if not cands:
        return []
    q = np.array([c["q"] for c in cands])
    top, mu, sd = float(q.max()), float(q.mean()), float(q.std() + 1e-6)
    thr = max(mu + 0.9 * sd, top - 0.045)
    pool = [c for c in cands if c["q"] >= thr]
    if len(pool) < min(n, 3):
        pool = sorted(cands, key=lambda c: -c["q"])[:min(len(cands), max(3, n))]
    return pool
