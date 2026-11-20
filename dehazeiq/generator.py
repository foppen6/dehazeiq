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

from . import analysis, quality
from .config import FORMATS, STYLES

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


def _smooth(a, k):
    if len(a) < 2 or k <= 1:
        return a.astype(np.float32)
    pad = k // 2
    ap = np.pad(a.astype(np.float32), (pad, pad), mode="edge")
    return np.convolve(ap, np.ones(k, np.float32) / k, mode="valid")[: len(a)]


def _crop_fraction(clip, fmt):
    """Hur stor del av källbildens bredd/höjd som syns efter beskärning till målformatet."""
    tw, th = FORMATS.get(fmt, FORMATS["16:9"])
    sw, sh = clip.get("width") or 16, clip.get("height") or 9
    target, src = tw / th, sw / sh
    if src > target:
        return target / src, 1.0  # beskärs i sidled
    return 1.0, src / target      # beskärs i höjdled


def build_candidates(project, style, fmt="16:9", favorites=(), use_interest=True):
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
    # Skärpa i förhållande till resten av materialet (brusokänsligt mått)
    has_focus = all("focus" in d for _, d, _ in loaded)
    focus_sorted = np.sort(np.concatenate([d["focus"] for _, d, _ in loaded])) if has_focus else None
    use_ai = all("interest" in d for _, d, _ in loaded)
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
        is_fav = c["id"] in favorites
        # Skärpa, exponering och stabilitet per prov (äldre analyser saknar dem: räkna fram)
        if "sharp_n" in d:
            sharp_n, expo, stab = d["sharp_n"], d["expo"], d["stab"]
        else:
            _, sharp_n, expo, stab = analysis.sample_quality(d["sharp"], d["luma"], d["clo"], d["chi"],
                                                             d.get("jitter", np.zeros_like(d["sharp"])))
        sharp_s = _smooth(sharp_n, 3)
        if focus_sorted is not None:
            # Skärpa i förhållande till klippets egen bästa skärpa: fångar fokusletande och
            # suddiga ögonblick (jämförelsen mellan klipp görs redan på klippnivå)
            ref = max(1e-6, float(np.percentile(d["focus"], 90)))
            frank = d["focus"] / ref
            frank_s = _smooth(frank, 3)
        else:
            frank = frank_s = None
        interest = d["interest"] if use_ai else None
        beauty = d["beauty"] if use_ai else None
        fw, fh = _crop_fraction(c, fmt)
        spread = d["spx"] if fw < 0.999 and "spx" in d else (d["spy"] if fh < 0.999 and "spy" in d else None)
        frac = fw if fw < 0.999 else fh
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
                a, b = i0 + j, i0 + j + n
                ms = (cs[j + n] - cs[j]) / n
                ma = (ca[j + n] - ca[j]) / n
                mm = (cm[j + n] - cm[j]) / n
                # Kvalitetsspärr: bara skarpa, välexponerade och stabila sekvenser
                passes = (float(sharp_n[a:b].mean()) >= quality.WIN_MIN_SHARP
                          and float(sharp_s[a:b].min()) >= quality.WIN_MIN_SHARP_LOW
                          and float(expo[a:b].mean()) >= quality.WIN_MIN_EXPO
                          and float(stab[a:b].mean()) >= quality.WIN_MIN_STAB)
                if passes and frank is not None:
                    passes = (float(frank[a:b].mean()) >= quality.WIN_MIN_FOCUS_RANK
                              and float(frank_s[a:b].min()) >= quality.WIN_MIN_FOCUS_RANK_LOW)
                mi = float(interest[a:b].mean()) if interest is not None else None
                if passes and mi is not None and use_interest:
                    passes = mi >= quality.WIN_MIN_INTEREST
                if not passes and not is_fav:
                    continue
                util = ms + style["motion_pref"] * (mm - 0.3) * 0.5 - 0.8 * max(0.0, 0.55 - ma)
                if mi is not None:
                    # AI: sevärdhet och skönhet väger lika tungt som teknisk kvalitet
                    util = 0.4 * util + 0.35 * mi + 0.25 * float(beauty[a:b].mean())
                if not passes:
                    util -= 1.0  # favorit utan godkänd sekvens: ta den minst dåliga
                # Motivet måste rymmas i beskärningen (t.ex. 9:16 ur liggande video)
                if spread is not None:
                    need = 3.0 * float(spread[a:b].mean())
                    if need > frac:
                        util -= 0.6 * min(1.0, (need - frac) / frac)
                local.append((util, a, b, ms, mm, ma))
            local.sort(key=lambda x: -x[0])
            taken = []
            for util, a, b, ms, mm, ma in local:
                if any(not (b <= ta or a >= tb) for ta, tb in taken):
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
        raise GenerateError("Hittade inga tillräckligt skarpa sekvenser i materialet. "
                            "Markera klipp som \"Måste med\" om du ändå vill använda dem.")
    # Bara höjdpunkterna: den bättre delen av alla godkända sekvenser (favoriter alltid med)
    u = np.array([x["util"] for x in cands])
    if len(cands) > 4:
        thr = float(np.quantile(u, quality.HIGHLIGHT_QUANTILE))
        keep = [x for x in cands if x["util"] >= thr or x["clip"]["id"] in favorites]
        if len(keep) >= 3:
            cands = keep
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


def _place(c, dur, fmt):
    """Välj bästa delen av kandidatfönstret och en beskärningsbana som följer motivet."""
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
    fw, fh = _crop_fraction(c["clip"], fmt)
    m = (t >= start) & (t < start + dur)
    if not m.any():
        m = np.argmin(np.abs(t - start)) == np.arange(len(t))
    if "sx" in d:
        # Motivets position, utjämnad (~1,75 s) så att beskärningen glider i stället för att rycka
        sx = _smooth(d["sx"], 7)
        sy = _smooth(d["sy"], 7)
        strength = float(np.median(d["sstr"][m]))
        weak = strength < 0.08  # inget tydligt motiv – håll bilden centrerad
    else:
        sx = d["cx"]
        sy = np.full_like(sx, 0.5)
        weak = False
    # AI: i vilket av fem utsnitt syns motivet tydligast? (bara när bilden beskärs i sidled)
    ai_x = None
    if fw < 0.999 and "ai_crop" in d and "emb_t" in d:
        from .ai import CROP_CENTERS
        centers = np.asarray(CROP_CENTERS, np.float32)
        crop = d["ai_crop"]
        valid = ~np.isnan(crop).any(axis=1)
        if valid.any():
            et = d["emb_t"][valid]
            cs = crop[valid]
            spread = cs.max(axis=1) - cs.min(axis=1)
            w = np.exp((cs - cs.max(axis=1, keepdims=True)) * 250.0)
            w /= w.sum(axis=1, keepdims=True)
            xs = (w * centers).sum(axis=1)
            conf = np.clip(spread / 0.015, 0.0, 1.0)
            ai_x = (et, xs, conf)
    idx = np.where(m)[0]
    keys = []
    prev = None
    step = max(1, int(round(0.5 / DT)))
    for k in list(idx[::step]) + [idx[-1]]:
        rel = float(t[k] - start)
        x = 0.5 if weak else float(sx[k])
        y = 0.5 if weak else float(sy[k])
        if ai_x is not None:
            et, xs, conf = ai_x
            j = int(np.argmin(np.abs(et - t[k])))
            if abs(float(et[j]) - float(t[k])) <= 2.5 and conf[j] > 0:
                # närliggande AI-mätningar viktas ihop med motivkartan
                near = np.abs(et - t[k]) <= 2.5
                wsum = float((conf[near]).sum())
                xa = float((xs[near] * conf[near]).sum() / wsum) if wsum > 0 else float(xs[j])
                # AI-utsnitten är grova: de styr mest när motivkartan är osäker
                alpha = (0.8 if weak else 0.3) * float(np.clip(conf[near].mean(), 0, 1))
                x = alpha * xa + (1 - alpha) * x
        # Håll beskärningen innanför bilden
        x = float(np.clip(x, fw / 2, 1 - fw / 2))
        y = float(np.clip(y, fh / 2, 1 - fh / 2))
        if prev is not None:  # begränsa panoreringens hastighet
            dt = max(1e-3, rel - prev[0])
            lim = 0.22 * dt
            x = prev[1] + float(np.clip(x - prev[1], -lim, lim))
            y = prev[2] + float(np.clip(y - prev[2], -lim, lim))
        if prev is None or rel - prev[0] > 1e-3:
            keys.append([round(max(0.0, min(rel, dur)), 3), round(x, 4), round(y, 4)])
            prev = (rel, x, y)
    if keys and keys[-1][0] < dur:
        keys.append([round(dur, 3), keys[-1][1], keys[-1][2]])
    cx = float(np.mean([k[1] for k in keys])) if keys else 0.5
    cy = float(np.mean([k[2] for k in keys])) if keys else 0.5
    return start, cx, cy, keys


def generate(project, style_key="cinematic", fmt="9:16", length=30.0, seed=None,
             music=None, favorites=()):
    if style_key not in STYLES:
        raise GenerateError(f"Okänd stil: {style_key}")
    style = STYLES[style_key]
    seed = int(seed if seed is not None else np.random.SeedSequence().entropy % 2**31)
    rng = np.random.default_rng(seed)
    try:
        cands, emb_kind = build_candidates(project, style, fmt, set(favorites))
    except GenerateError:
        # Inga sekvenser med tydligt motiv – gör filmen av det tekniskt bästa i stället
        cands, emb_kind = build_candidates(project, style, fmt, set(favorites), use_interest=False)
    length = float(length)
    n = max(3, int(round(length / style["avg_shot"])))
    # Filmen blir hellre kortare än utfylld: aldrig fler klipp än det finns höjdpunkter
    n = min(n, max(1, len({(c["clip"]["id"], c["i0"]) for c in cands})))
    chosen = _select(cands, n, style, rng, emb_kind, list(favorites))
    seq = _order(chosen, style_key, emb_kind)
    beats = music.get("beats") if music else None
    durs = _durations(seq, length, style, rng, beats)

    shots, pos = [], 0.0
    for c, dur in zip(seq, durs):
        start, cx, cy, path = _place(c, float(dur), fmt)
        clip = c["clip"]
        a = clip.get("analysis", {})
        shots.append({
            "clip_id": clip["id"], "name": clip["name"],
            "src_start": round(start, 3), "src_end": round(start + float(dur), 3),
            "duration": round(float(dur), 3), "at": round(pos, 3),
            "cx": round(cx, 3), "cy": round(cy, 3), "path": path, "wb_gains": a.get("wb_gains", [1, 1, 1]),
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
        "short": bool(pos < length * 0.85),
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
