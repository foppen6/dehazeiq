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

from . import whisper
from . import divearc, analysis, effects, quality, story
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


def context_clips(project):
    """Klipp som får användas som sammanhang (yta, båt, nedstigning) trots att de saknar
    ett tydligt motiv – men aldrig tekniskt dåliga klipp."""
    ok = {"Inget tydligt motiv", "Svagare än resten"}
    return [c for c in project.clips() if c.get("analysis") and not c.get("is360") and not c.get("excluded")
            and set(c.get("reasons") or []) <= ok]


def build_candidates(project, style, fmt="16:9", favorites=(), use_interest=True, clips=None,
                     highlights=True):
    clips = project.usable_clips() if clips is None else clips
    if fmt not in ("9:16", "4:5"):  # delad 360-bild (två vyer över varandra) bara i stående format
        clips = [c for c in clips if not c.get("portrait_only")]
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
    # Tal (Whisper): vlogg och dokumentär väljer gärna klipp där något sägs, musikfilmer undviker dem
    sp_pref = style.get("speech_pref")
    if sp_pref is None:
        sp_pref = (0.15 if style.get("label") == "Dokumentär" else
                   -0.15 if style.get("no_text") or style.get("music_video") or style.get("promo") else 0.0)
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
        has_speech = bool((c.get("speech") or {}).get("segments"))
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
                talk = whisper.speech_share(c, float(t[a]), float(t[b - 1]) + DT) if has_speech else 0.0
                if passes and mi is not None and use_interest and not (sp_pref > 0 and talk >= 0.4):
                    passes = mi >= quality.WIN_MIN_INTEREST  # någon som pratar är sevärt ändå
                if not passes and not is_fav:
                    continue
                util = ms + style["motion_pref"] * (mm - 0.3) * 0.5 - 0.8 * max(0.0, 0.55 - ma)
                if mi is not None:
                    # AI: sevärdhet och skönhet väger lika tungt som teknisk kvalitet
                    util = 0.4 * util + 0.35 * mi + 0.25 * float(beauty[a:b].mean())
                util += sp_pref * talk
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
                    "speech": round(whisper.speech_share(c, s, e), 3) if has_speech else 0.0,
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
    if highlights and len(cands) > 4:
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


def _durations(seq, total, style, rng, beats, energy=None):
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
    if style.get("ramp") and len(d) > 3:
        # trailer: långa lugna klipp först, allt kortare mot klimax (sista klippet får andas)
        r = np.linspace(1.7, 0.55, len(d))
        r[-1] = 1.4
        d = np.clip(d * r, mins, maxs)
        d = np.clip(d * (total / d.sum()), mins, maxs)
    if energy and len(d) > 2:
        # musikens energi: kortare klipp där musiken är intensiv, längre där den är lugn
        from .music import energy_at
        for _ in range(3):
            mid = np.cumsum(d) - d / 2
            f = np.array([1.35 - 0.7 * energy_at(energy, m) for m in mid])
            d = np.clip(d * f, mins, maxs)
            d = np.clip(d * (total / d.sum()), mins, maxs)
    if beats is not None and len(beats) and style.get("bar_sync"):
        beats = list(beats)[::2]  # lugnare: byten på varannan taktslag (halvtakt)
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


def _hit_drop(seq, durs, music):
    """Musikvideo: ett klipp börjar exakt på musikens starkaste lyft inom filmen (refräng/drop),
    och det klippet är filmens bästa (mest rörelse och sevärdhet)."""
    from .music import drops
    total = float(np.sum(durs))
    ds = music.get("drops") or drops(music.get("energy") or [])
    ds = [x for x in ds if 0.25 * total <= x["t"] <= total - 1.5]
    if not ds:
        return seq, durs
    td = max(ds, key=lambda x: x["strength"])["t"]
    beats = np.asarray(music.get("beats") or [])
    if len(beats):
        td = float(beats[np.argmin(np.abs(beats - td))])  # exakt på taktslaget
    edges = np.concatenate([[0.0], np.cumsum(durs)])
    k = int(np.argmin(np.abs(edges[1:-1] - td))) + 1  # närmaste klippgräns
    move = td - edges[k]
    if abs(move) > 0.45 * min(durs[k - 1], durs[k]):
        return seq, durs
    durs = np.array(durs, float)
    durs[k - 1] += move
    durs[k] -= move
    # bästa klippet hamnar på dropen (byter plats med det som låg där)
    best = max(range(1, len(seq)), key=lambda i: seq[i]["motion"] + seq[i]["util_n"] + seq[i].get("fun", 0))
    seq = list(seq)
    if best != k and (seq[best]["end"] - seq[best]["start"]) >= durs[k] - 1e-3 \
            and (seq[k]["end"] - seq[k]["start"]) >= durs[best] - 1e-3:
        seq[best], seq[k] = seq[k], seq[best]
    return seq, durs


def auto_fit(c, start, dur, fmt):
    """AI-inpassning: ryms inte motivet i beskärningen (t.ex. en manta, ett stim eller en dykgrupp i en
    stående film) zoomar vi ut precis så mycket som behövs och lägger en suddig bakgrund runt.
    Returnerar {"zoom", "bg", "auto"} eller None (vanlig beskärning räcker)."""
    d, clip = c["data"], c["clip"]
    fw, fh = _crop_fraction(clip, fmt)
    if fw >= 0.999 and fh >= 0.999:
        return None
    key, frac = ("spx", fw) if fw < 0.999 else ("spy", fh)
    if key not in d or "sstr" not in d:
        return None
    t = d["t"]
    m = (t >= start) & (t < start + dur)
    if not m.any() or float(np.median(d["sstr"][m])) < 0.08:
        return None  # inget tydligt motiv: vanlig beskärning
    spread = float(np.percentile(d[key][m], 70))
    need = min(1.0, 4.4 * spread)  # motivet ±2 standardavvikelser och lite luft
    if need <= frac * 1.12:
        return None
    z = float(np.log(need) / np.log(frac))
    z = max(0.45, round(z, 2))  # aldrig mer än ungefär halva vägen mot hela bilden automatiskt
    return None if z >= 0.95 else {"zoom": z, "bg": "blur", "auto": True}


def _place(c, dur, fmt):
    """Välj bästa delen av kandidatfönstret och en beskärningsbana som följer motivet."""
    d = c["data"]
    t = d["t"]
    q = d["quality"]
    s0, s1 = c["start"], c["end"]
    segs = ((c["clip"].get("speech") or {}).get("segments")) or []
    if s1 - s0 <= dur + 1e-6:
        start = s0
    else:
        best, start = -1e9, s0
        for s in np.arange(s0, s1 - dur + 1e-6, DT):
            m = (t >= s) & (t < s + dur)
            v = float(q[m].mean()) if m.any() else 0.0
            if segs:  # klipp inte av en mening mitt i
                e = s + dur
                v -= 0.25 * sum(1 for g in segs if g["start"] < s - 0.1 < g["end"] or g["start"] < e + 0.1 < g["end"])
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
    # AI: var i bilden är djuret? (rutnät av utsnitt, analysversion 2)
    loc = None
    if "loc_t" in d and len(d["loc_t"]):
        lconf = np.clip((d["loc_conf"] - 0.012) / 0.02, 0.0, 1.0)
        loc = (d["loc_t"], d["loc_x"], d["loc_y"], lconf)
    ai_x = None
    if loc is None and fw < 0.999 and "ai_crop" in d and "emb_t" in d:
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
        if loc is not None:
            lt, lx, ly, lc = loc
            near = np.abs(lt - t[k]) <= 2.2
            if near.any():
                # närliggande mätningar viktade efter säkerhet och avstånd i tid
                wgt = (0.1 + lc[near]) * (1.0 - np.abs(lt[near] - t[k]) / 2.5)
                if float(wgt.sum()) > 1e-3:
                    xa = float((lx[near] * wgt).sum() / wgt.sum())
                    ya = float((ly[near] * wgt).sum() / wgt.sum())
                    alpha = 0.5 + 0.45 * float(np.clip(lc[near].max(), 0, 1))
                    x = alpha * xa + (1 - alpha) * x
                    y = alpha * ya + (1 - alpha) * y
        elif ai_x is not None:
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
            lim = 0.3 * dt
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


def _candidates_for(project, style, fmt, favorites):
    # Höjdpunktsurvalet görs inom varje tema (story.build), inte globalt
    try:
        cands, emb_kind = build_candidates(project, style, fmt, set(favorites), highlights=False)
    except GenerateError:
        # Inga sekvenser med tydligt motiv – gör filmen av det tekniskt bästa i stället
        cands, emb_kind = build_candidates(project, style, fmt, set(favorites), use_interest=False,
                                           highlights=False)
    try:
        ctx, _ = build_candidates(project, style, fmt, set(), use_interest=False,
                                  clips=context_clips(project), highlights=False)
    except GenerateError:
        ctx = []
    by_id = {c["id"]: c for c in project.clips()}
    story.annotate(cands, by_id)
    story.annotate(ctx, by_id)
    try:  # dykets början och slut (båt, nedstigning / boj, säkerhetsstopp, uppstigning)
        divearc.annotate(cands + ctx)
    except Exception as exc:  # noqa: BLE001
        print("Dykfaser:", exc)
    ctx = [c for c in ctx if c.get("context")]
    return cands, ctx, emb_kind


def themes(project, fmt="9:16"):
    """Teman som går att göra film av (för gränssnittet och automatiska förslag)."""
    cands, _, _ = _candidates_for(project, STYLES["cinematic"], fmt, ())
    by_id = {c["id"]: c for c in project.clips()}
    return story.find_themes(cands, by_id)


def search_theme(query, title=None, order="story"):
    q = str(query).strip()
    return {"id": f"search:{q}", "kind": "search", "query": q, "order": order,
            "title": title or (q[:1].upper() + q[1:])}


def _resolve_theme(theme, cands, project):
    if isinstance(theme, dict):
        return theme
    if isinstance(theme, str) and theme.startswith("search:"):
        return search_theme(theme.split(":", 1)[1])
    by_id = {c["id"]: c for c in project.clips()}
    found = story.find_themes(cands, by_id)
    if theme:
        for t in found:
            if t["id"] == theme:
                return t
        # samma sorts berättelse även om exakt id saknas (t.ex. art ↔ djurgrupp, andra klipplängder)
        kind, _, rest = str(theme).partition(":")
        for t in found:
            if t["kind"] == kind and (not rest or rest in (t.get("label"), t.get("species"))):
                return t
        if kind == "subject":
            want = rest
            for t in found:
                if t["kind"] == "subject" and want and (t.get("label") == want or want in t.get("title", "")):
                    return t
    return found[-1]  # resan/höjdpunkterna


def generate(project, style_key="cinematic", fmt="9:16", length=30.0, seed=None,
             music=None, favorites=(), theme=None, avoid_clips=()):
    if style_key not in STYLES:
        raise GenerateError(f"Okänd stil: {style_key}")
    style = STYLES[style_key]
    seed = int(seed if seed is not None else np.random.SeedSequence().entropy % 2**31)
    rng = np.random.default_rng(seed)
    cands, ctx, emb_kind = _candidates_for(project, style, fmt, favorites)
    th = _resolve_theme(theme, cands, project)
    length = float(length)
    if music is None and not style.get("no_music"):
        # ingen låt vald i projektet: AI väljer ur musikbiblioteket (tempo, energi, längd, licens)
        try:
            from . import musiclib
            recent = [p.get("music_track") for p in (project.data.get("proposals") or [])[:4] if p.get("music_track")]
            music = musiclib.pick(style_key, length, commercial=bool(style.get("promo")), avoid=recent, seed=seed)
        except Exception:  # noqa: BLE001
            music = None
    n = max(3, int(round(length / style["avg_shot"])))
    # Filmen blir hellre kortare än utfylld: aldrig fler klipp än det finns höjdpunkter (+ sammanhang)
    n = min(n, max(1, len({(c["clip"]["id"], c["i0"]) for c in cands})) + 2)
    favs = list(favorites)
    if avoid_clips:
        # "Generera nya förslag": klipp som nyss användes får lägre prioritet, så att det blir nytt
        av = set(avoid_clips) - set(favs)
        for c in cands:
            if c["clip"]["id"] in av:
                c["util_n"] *= 0.72

    def select(pool, k):
        k = min(k, len(pool))
        return _select(pool, k, style, rng, emb_kind, [f for f in favs if any(c["clip"]["id"] == f for c in pool)])

    seq = story.build(th, cands, ctx, n, select)
    if not seq:
        seq = _order(_select(cands, n, style, rng, emb_kind, favs), style_key, emb_kind)
    seq = divearc.arrange(seq, (th or {}).get("kind"), style_key)
    beats = music.get("beats") if music else None
    is_mv = bool(style.get("music_video")) or style_key == "musicvideo"
    energy = (music.get("energy") or None) if (music and is_mv) else None
    durs = _durations(seq, length, style, rng, beats, energy)
    if is_mv and music and len(seq) >= 4:
        seq, durs = _hit_drop(seq, durs, music)

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
            **({"fit": f} if (f := auto_fit(c, start, float(dur), fmt)) and not clip.get("photo") else {}),
            "underwater": a.get("underwater", False), "tags": a.get("tags", []),
            "label": c.get("label"), "shot": c.get("shot"), "context": c.get("context"),
            "session": c.get("session"), "time": c.get("time"),
            "species_sci": (c.get("species") or [None] * 3)[2] if c.get("species_p", 0) >= 0.35 else None,
            "species_p": round(float(c.get("species_p", 0)), 3),
            "caption": c.get("caption") or "",
            "quality": round(c["quality"], 3), "motion": round(c["motion"], 3),
            "favorite": bool(c.get("favorite")),
            "species": (c.get("species") or [None])[0] if c.get("species_p", 0) >= 0.35 else None,
            "desc": c.get("desc") or "",
            "photo": bool(clip.get("is_photo")),
            "view360": clip.get("view360"), "parent360": clip.get("parent360"),
            "phase": c.get("phase"),
        })
        pos += float(dur)

    # Berättartext från djupanalysen: hur det börjar och vad som är höjdpunkten
    story_text = story.THEME_TEXT.get(th["kind"], "")
    descs = [(c, c.get("desc")) for c in seq if c.get("desc")]
    if len(descs) >= 2:
        first = descs[0][1].rstrip(". ")
        peak = max(descs[1:], key=lambda x: x[0].get("vlm_action", 0) + x[0].get("fun", 0))[1].rstrip(". ")
        story_text = f"{first} … {peak[0].lower() + peak[1:] if peak else peak}."

    prop = {
        "id": uuid.uuid4().hex[:10],
        "style": style_key, "style_label": style["label"],
        "theme": th["id"], "theme_kind": th["kind"], "title": th["title"],
        "story": story_text,
        "format": fmt, "target_length": length, "length": round(pos, 2),
        "seed": seed, "created": time.time(),
        "n_shots": len(shots),
        "avg_shot": round(pos / max(1, len(shots)), 2),
        "music": music.get("path") if music else None,
        "music_name": music.get("name") if music else None,
        "bpm": music.get("bpm") if music else None,
        "music_track": music.get("track_id") if music else None,
        "music_auto": bool(music and music.get("auto")),
        "music_license": (music.get("license") if music else None),
        "music_credit": (music.get("credit") if music else "") or "",
        "favorites": list(favorites),
        "similarity": emb_kind,
        "short": bool(pos < length * 0.85),
        "shots": shots,
        "renders": {},
    }
    return effects.plan(prop, {c["id"]: c for c in project.clips()}, style_key)


def generate_set(project, style="auto", fmt="9:16", length=30.0, music=None, favorites=(), theme=None,
                 avoid=(), avoid_clips=()):
    """Tre förslag. Utan valt tema: tre olika berättelser (t.ex. djurporträtt, ett dyk, resan).
    Med valt tema: tre versioner av samma berättelse (tre stilar, eller tre varianter av en stil)."""
    if theme:
        if style == "auto":
            kind = (theme.get("kind") if isinstance(theme, dict) else str(theme).split(":")[0])
            styles = ["documentary", "playful", "cinematic"] if kind in ("fun", "subject") else ["documentary", "cinematic", "action"]
            if kind == "fun":
                styles = ["playful", "action", "cinematic"]
        else:
            styles = [style] * 3
        return [generate(project, s, fmt, length, None, music, favorites, theme, avoid_clips) for s in styles]
    plan = story.auto_plan(themes(project, fmt), avoid)
    return [generate(project, s if style == "auto" else style, fmt, length, None, music, favorites, t, avoid_clips)
            for t, s in plan]
