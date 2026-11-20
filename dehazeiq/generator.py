"""Filmgenerator: väljer och ordnar klipp utifrån analys, stil och musik.

Urvalet är ett optimeringsproblem med slump:
  1. Kandidatfönster per scen poängsätts (kvalitet + stilens syn på rörelse).
  2. Klipp väljs ett i taget med en sannolikhet som belönar kvalitet och
     straffar likhet med redan valda klipp (variation).
  3. Ordningen följer en enkel dramaturgi: intro → uppbyggnad → höjdpunkt → avslut.
  4. Klipplängder anpassas till filmens längd och, ibland, till musikens takt.
Ett nytt frö (seed) ger ett nytt förslag av samma material.
"""

import time
import uuid

import numpy as np

from . import analysis
from .config import STYLES

DT = 1.0 / analysis.SAMPLE_FPS


class GenerateError(RuntimeError):
    pass


def _clip_data(project, clip):
    d = analysis.load(project.npz_path(clip["id"]))
    emb_kind = "hist"
    if "emb" in d and len(d.get("emb", [])):
        emb_kind = "clip"
    return d, emb_kind


def _norm(v):
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


def _segment_embedding(d, emb_kind, s, e):
    """Inbäddning för ett tidsintervall (CLIP om det finns, annars färghistogram)."""
    if emb_kind == "clip":
        et = d["emb_t"]
        m = (et >= s - 1.0) & (et <= e + 1.0)
        if not m.any():
            m = np.argmin(np.abs(et - (s + e) / 2)) == np.arange(len(et))
        return _norm(d["emb"][m].astype(np.float32).mean(axis=0))
    t = d["t"]
    m = (t >= s) & (t <= e)
    if not m.any():
        m = np.ones(len(t), bool)
    return _norm(np.sqrt(d["hist"][m].mean(axis=0)))


def _similarity(a, b, kind):
    sim = float(np.dot(a, b))
    if kind == "clip":
        return float(np.clip((sim - 0.6) / 0.35, 0.0, 1.0))
    return float(np.clip((sim - 0.75) / 0.25, 0.0, 1.0))


def _scenes(cut):
    idx = [0] + [i for i in range(1, len(cut)) if cut[i]] + [len(cut)]
    return [(idx[k], idx[k + 1]) for k in range(len(idx) - 1) if idx[k + 1] > idx[k]]


def build_candidates(project, style):
    clips = project.usable_clips()
    if not clips:
        raise GenerateError("Inget analyserat material ännu. Kör analysen först.")
    loaded = []
    for c in clips:
        try:
            d, kind = _clip_data(project, c)
        except (OSError, KeyError, ValueError):
            continue
        loaded.append((c, d, kind))
    if not loaded:
        raise GenerateError("Hittar ingen analysdata. Kör analysen igen.")
    # Blandad absolut och relativ kvalitet, så att mjukare undervattensmaterial inte straffas för hårt
    allq = np.concatenate([d["quality"] for _, d, _ in loaded])
    ranks = np.sort(allq)
    emb_kind = "clip" if all(k == "clip" for _, _, k in loaded) else "hist"

    wlen = float(np.clip(style["avg_shot"] * 1.6, style["min_shot"], style["max_shot"]))
    stride = max(1, int(round(0.5 / DT)))
    cands = []
    for c, d, _ in loaded:
        q_abs = d["quality"]
        q_rel = np.searchsorted(ranks, q_abs) / max(1, len(ranks))
        score = 0.5 * q_abs + 0.5 * q_rel
        motion = d["motion"]
        t = d["t"]
        for i0, i1 in _scenes(d["cut"]):
            scene_len = (i1 - i0) * DT
            if scene_len < style["min_shot"]:
                continue
            n = max(1, min(i1 - i0, int(round(wlen / DT))))
            cs = np.concatenate([[0.0], np.cumsum(score[i0:i1])])
            ca = np.concatenate([[0.0], np.cumsum(q_abs[i0:i1])])
            cm = np.concatenate([[0.0], np.cumsum(motion[i0:i1])])
            local = []
            for j in range(0, (i1 - i0) - n + 1, stride):
                ms = (cs[j + n] - cs[j]) / n
                ma = (ca[j + n] - ca[j]) / n
                mm = (cm[j + n] - cm[j]) / n
                # Suddiga/mörka partier straffas hårt oavsett stil
                util = ms + style["motion_pref"] * (mm - 0.3) * 0.5 - 0.8 * max(0.0, 0.55 - ma)
                local.append((util, i0 + j, i0 + j + n, ms, mm, ma))
            local.sort(key=lambda x: -x[0])
            taken = []
            for util, a, b, ms, mm, ma in local:
                if any(not (b <= ta or a >= tb) for ta, tb in taken):
                    continue
                if ms < 0.2 or ma < 0.3:
                    continue
                taken.append((a, b))
                s, e = float(t[a]), float(t[b - 1]) + DT
                cands.append({
                    "clip": c, "data": d, "i0": a, "i1": b, "start": s, "end": e,
                    "util": float(util), "quality": float(ms), "motion": float(mm),
                    "emb": _segment_embedding(d, emb_kind, s, e),
                    "time": float(c.get("created") or 0) + s,
                })
                if len(taken) >= 3:
                    break
    if not cands:
        raise GenerateError("Hittade inga tillräckligt bra sekvenser i materialet.")
    u = np.array([x["util"] for x in cands])
    lo, hi = float(u.min()), float(u.max())
    for x in cands:
        x["util_n"] = (x["util"] - lo) / (hi - lo) if hi > lo else 1.0
    return cands, emb_kind


def _select(cands, n, style, rng, emb_kind, favorites):
    chosen = []

    def overlaps(x, y):
        return x["clip"]["id"] == y["clip"]["id"] and not (x["end"] <= y["start"] or x["start"] >= y["end"])

    # Favoriter kommer alltid med (bästa sekvensen i varje favoritklipp)
    for fid in favorites:
        best = max((c for c in cands if c["clip"]["id"] == fid), key=lambda c: c["util"], default=None)
        if best is not None and len(chosen) < n:
            best["favorite"] = True
            chosen.append(best)

    while len(chosen) < n:
        pool, utils = [], []
        for c in cands:
            if any(c is x or overlaps(c, x) for x in chosen):
                continue
            sim = max((_similarity(c["emb"], x["emb"], emb_kind) for x in chosen), default=0.0)
            same = sum(1 for x in chosen if x["clip"]["id"] == c["clip"]["id"])
            if sim > 0.97 and same:
                continue
            u = c["util_n"] + style["variety"] * (1.0 - sim) - 0.35 * same
            pool.append(c)
            utils.append(u)
        if not pool:
            break
        u = np.array(utils)
        p = np.exp((u - u.max()) / max(style["temperature"], 1e-3))
        p /= p.sum()
        chosen.append(pool[int(rng.choice(len(pool), p=p))])
    return chosen


def _order(chosen, style_key, emb_kind):
    if len(chosen) <= 2:
        return sorted(chosen, key=lambda c: c["time"])
    rest = list(chosen)

    def intro_score(c):
        above = 0.0 if c["clip"].get("analysis", {}).get("underwater") else 0.2
        return c["util_n"] - 0.5 * c["motion"] + above

    intro = max(rest, key=intro_score)
    rest.remove(intro)
    if style_key == "action":
        outro = max(rest, key=lambda c: c["util_n"] + c["motion"] + (0.3 if c.get("favorite") else 0))
    else:
        outro = max(rest, key=lambda c: c["util_n"] - 0.3 * c["motion"] + (0.3 if c.get("favorite") else 0))
    rest.remove(outro)
    middle = sorted(rest, key=lambda c: c["time"])
    # Höjdpunkten (mest energi) placeras runt 70 % in i filmen
    if len(middle) >= 3:
        peak = max(middle, key=lambda c: c["motion"] + 0.5 * c["util_n"])
        middle.remove(peak)
        middle.insert(int(round(0.7 * len(middle))), peak)
    seq = [intro] + middle + [outro]
    # Undvik att två mycket lika klipp hamnar direkt efter varandra
    for i in range(1, len(seq) - 1):
        if _similarity(seq[i - 1]["emb"], seq[i]["emb"], emb_kind) > 0.85:
            for j in range(i + 1, len(seq) - 1):
                if _similarity(seq[i - 1]["emb"], seq[j]["emb"], emb_kind) < 0.6:
                    seq[i], seq[j] = seq[j], seq[i]
                    break
    return seq


def _durations(seq, total, style, rng, beats):
    mins = np.array([style["min_shot"]] * len(seq))
    maxs = np.array([min(style["max_shot"], c["end"] - c["start"]) for c in seq])
    mins = np.minimum(mins, maxs)
    d = np.array([style["avg_shot"] * rng.uniform(0.8, 1.25) for _ in seq])
    if len(seq) > 2 and style["avg_shot"] >= 3:
        d[0] *= 1.25
        d[-1] *= 1.25
    d = np.clip(d, mins, maxs)
    for _ in range(8):
        s = d.sum()
        if abs(s - total) < 0.05:
            break
        d = np.clip(d * (total / s), mins, maxs)
    # Lägg klippen på taktslag ibland – inte alltid, berättelsen går också före
    if beats is not None and len(beats) and len(d) > 1:
        beats = np.asarray(beats)
        cuts = np.cumsum(d)[:-1]
        for k in range(len(cuts)):
            if rng.random() >= style["beat_sync"]:
                continue
            b = beats[np.argmin(np.abs(beats - cuts[k]))]
            prev = cuts[k - 1] if k else 0.0
            nxt = cuts[k + 1] if k + 1 < len(cuts) else d.sum()
            if abs(b - cuts[k]) <= 0.35 * min(d[k], d[k + 1]) and b - prev >= 0.6 and nxt - b >= 0.6:
                cuts[k] = b
        edges = np.concatenate([[0.0], cuts, [d.sum()]])
        nd = np.diff(edges)
        if (nd <= maxs + 1e-6).all() and (nd > 0.5).all():
            d = nd
    return d


def _place(c, dur):
    """Välj bästa delen av kandidatfönstret för ett klipp med längden dur."""
    d = c["data"]
    t = d["t"]
    q = d["quality"]
    s0, s1 = c["start"], c["end"]
    if s1 - s0 <= dur + 1e-6:
        start = s0
    else:
        best, start = -1.0, s0
        for s in np.arange(s0, s1 - dur + 1e-6, DT):
            m = (t >= s) & (t < s + dur)
            v = float(q[m].mean()) if m.any() else 0.0
            if v > best:
                best, start = v, float(s)
    m = (t >= start) & (t < start + dur)
    cx = float(d["cx"][m].mean()) if m.any() else 0.5
    cx = 0.5 + 0.7 * (cx - 0.5)
    return start, cx


def generate(project, style_key="cinematic", fmt="9:16", length=30.0, seed=None,
             music=None, favorites=()):
    if style_key not in STYLES:
        raise GenerateError(f"Okänd stil: {style_key}")
    style = STYLES[style_key]
    seed = int(seed if seed is not None else np.random.SeedSequence().entropy % 2**31)
    rng = np.random.default_rng(seed)
    cands, emb_kind = build_candidates(project, style)
    length = float(length)
    n = max(3, int(round(length / style["avg_shot"])))
    chosen = _select(cands, n, style, rng, emb_kind, list(favorites))
    seq = _order(chosen, style_key, emb_kind)
    beats = music.get("beats") if music else None
    durs = _durations(seq, length, style, rng, beats)

    shots, pos = [], 0.0
    for c, dur in zip(seq, durs):
        start, cx = _place(c, float(dur))
        clip = c["clip"]
        a = clip.get("analysis", {})
        shots.append({
            "clip_id": clip["id"], "name": clip["name"],
            "src_start": round(start, 3), "src_end": round(start + float(dur), 3),
            "duration": round(float(dur), 3), "at": round(pos, 3),
            "cx": round(cx, 3), "wb_gains": a.get("wb_gains", [1, 1, 1]),
            "underwater": a.get("underwater", False), "tags": a.get("tags", []),
            "quality": round(c["quality"], 3), "motion": round(c["motion"], 3),
            "favorite": bool(c.get("favorite")),
        })
        pos += float(dur)

    return {
        "id": uuid.uuid4().hex[:10],
        "style": style_key, "style_label": style["label"],
        "format": fmt, "target_length": length, "length": round(pos, 2),
        "seed": seed, "created": time.time(),
        "n_shots": len(shots),
        "avg_shot": round(pos / max(1, len(shots)), 2),
        "music": music.get("path") if music else None,
        "music_name": music.get("name") if music else None,
        "bpm": music.get("bpm") if music else None,
        "favorites": list(favorites),
        "similarity": emb_kind,
        "shots": shots,
        "renders": {},
    }


def generate_set(project, style="auto", fmt="9:16", length=30.0, music=None, favorites=()):
    """Tre förslag: tre stilar (auto) eller tre varianter av samma stil."""
    if style == "auto":
        plan = [("cinematic", None), ("action", None), ("calm", None)]
    else:
        plan = [(style, None)] * 3
    return [generate(project, s, fmt, length, seed, music, favorites) for s, seed in plan]
