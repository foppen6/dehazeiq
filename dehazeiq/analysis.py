"""Bildanalys per klipp: skärpa, exponering, stabilitet, rörelse, scenbyten,
färgbalans och (valfritt) motiv med CLIP.

Varje klipp analyseras från sin proxyfil med cirka 4 prov per sekund.
Rådata sparas i en .npz-fil per klipp; en sammanfattning hamnar i projektet.
"""

from pathlib import Path

import cv2
import numpy as np

from . import ai, tagging

SAMPLE_FPS = 4.0
WORK_WIDTH = 320
TAG_EVERY = 2.0  # sekunder mellan bildrutor till CLIP


SAL_W = 64
_NOISE_K = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], np.float32)


def saliency(frame_bgr, grad=None):
    """Var i bilden finns motivet? Spektralresidual (Hou & Zhang) + färgkontrast,
    viktat mot skarpa områden (motivet är oftast det som är i fokus).
    Returnerar (sx, sy, spread_x, spread_y, styrka, motivskärpa)."""
    h, w = frame_bgr.shape[:2]
    sh = max(8, int(round(SAL_W * h / w)))
    small = cv2.resize(frame_bgr, (SAL_W, sh), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    f = np.fft.fft2(gray)
    log_amp = np.log(np.abs(f) + 1e-6)
    phase = np.angle(f)
    residual = log_amp - cv2.blur(log_amp, (3, 3))
    sr = np.abs(np.fft.ifft2(np.exp(residual + 1j * phase))) ** 2
    sr = cv2.GaussianBlur(sr.astype(np.float32), (0, 0), 2.5)
    lab = cv2.cvtColor(small, cv2.COLOR_BGR2LAB).astype(np.float32)
    cc = np.linalg.norm(lab - lab.reshape(-1, 3).mean(axis=0), axis=2)
    cc = cv2.GaussianBlur(cc, (0, 0), 2.0)

    def _n(a):
        lo, hi = float(a.min()), float(a.max())
        return (a - lo) / (hi - lo) if hi > lo else np.zeros_like(a)

    sal = 0.5 * _n(sr) + 0.5 * _n(cc)
    g_small = None
    if grad is not None:
        g_small = cv2.resize(grad, (SAL_W, sh), interpolation=cv2.INTER_AREA)
        g_small = cv2.GaussianBlur(g_small, (0, 0), 1.5)
        sal = sal * (0.35 + 0.65 * _n(g_small))
    # Bara de mest framträdande delarna räknas, så att bakgrunden inte drar mot mitten
    thr = np.percentile(sal, 85)
    wgt = np.clip(sal - thr, 0, None) ** 2
    tot = float(wgt.sum())
    if tot <= 1e-9:
        return 0.5, 0.5, 0.5, 0.5, 0.0, 0.0
    ys, xs = np.mgrid[0:sh, 0:SAL_W]
    xs = (xs + 0.5) / SAL_W
    ys = (ys + 0.5) / sh
    sx = float((wgt * xs).sum() / tot)
    sy = float((wgt * ys).sum() / tot)
    spx = float(np.sqrt((wgt * (xs - sx) ** 2).sum() / tot))
    spy = float(np.sqrt((wgt * (ys - sy) ** 2).sum() / tot))
    strength = float(sal.max() - np.median(sal))
    sfocus = float((wgt * g_small).sum() / tot) if g_small is not None else 0.0
    return sx, sy, spx, spy, strength, sfocus


def _hist(hsv):
    h = cv2.calcHist([hsv], [0, 1, 2], None, [8, 4, 4], [0, 180, 0, 256, 0, 256]).flatten()
    s = h.sum()
    return (h / s).astype(np.float32) if s > 0 else h.astype(np.float32)


def sample_quality(sharp, luma, clip_lo, clip_hi, jitter):
    """Kvalitet 0..1 per prov. Exponeras även för generatorn."""
    sharp_n = np.clip((np.log10(sharp + 1.0) - 1.0) / 1.6, 0.0, 1.0)
    # Undervattensbilder är ofta mörkare än land – hela 45–195 räknas som bra exponering
    under = np.clip((luma - 12.0) / 33.0, 0.0, 1.0)
    over = np.clip((242.0 - luma) / 47.0, 0.0, 1.0)
    # Svarta partier är vanliga (nattdyk, skuggor) – straffa bara stora mängder.
    # Utfrätta högdagrar är värre och straffas tidigare.
    expo = np.minimum(under, over) - 1.5 * np.maximum(0.0, clip_lo - 0.25) - 2.5 * np.maximum(0.0, clip_hi - 0.06)
    expo = np.clip(expo, 0.0, 1.0)
    stab = np.clip(1.0 - jitter * 20.0, 0.0, 1.0)
    return np.clip(0.45 * sharp_n + 0.30 * expo + 0.25 * stab, 0.0, 1.0), sharp_n, expo, stab


def analyze_clip(proxy_path, out_npz, progress=None, with_tags=True) -> dict:
    """Analysera en proxyfil. Returnerar en sammanfattning (JSON-vänlig)."""
    cap = cv2.VideoCapture(str(proxy_path))
    if not cap.isOpened():
        raise RuntimeError(f"Kan inte öppna {proxy_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    step = max(1, int(round(fps / SAMPLE_FPS)))
    tag_step = max(1, int(round(TAG_EVERY * SAMPLE_FPS)))

    rec = {k: [] for k in ("t", "sharp", "luma", "clo", "chi", "r", "g", "b",
                           "cx", "dx", "dy", "diff", "cut", "sx", "sy", "spx", "spy", "sstr",
                           "focus", "sfocus")}
    model = ai.get() if with_tags else None
    ai_step = max(1, int(round(SAMPLE_FPS)))  # en AI-bild per sekund
    ai_buf, ai_buf_t = [], []
    ai_rec = {"t": [], "emb": [], "int": [], "beauty": [], "probs": [], "crop": []}

    def ai_flush():
        if not ai_buf:
            return
        emb = model.embed(ai_buf)
        inter = model.interest(emb)
        ai_rec["t"] += ai_buf_t
        ai_rec["emb"].append(emb)
        ai_rec["int"].append(inter)
        ai_rec["beauty"].append(model.beauty(emb))
        ai_rec["probs"].append(model.label_probs(emb))
        for k, (img, it) in enumerate(zip(ai_buf, inter)):
            h_, w_ = img.shape[:2]
            # Var i bilden är motivet? Bara för liggande bild med något i, varannan sekund
            if w_ > h_ * 1.2 and it > 0.45 and (len(ai_rec["crop"]) % 2 == 0):
                ai_rec["crop"].append(model.crop_scores(img))
            else:
                ai_rec["crop"].append(np.full(len(ai.CROP_CENTERS), np.nan, np.float32))
        ai_buf.clear()
        ai_buf_t.clear()
    hists = []
    tag_frames, tag_times = [], []
    prev_gray = prev_small = prev_hist = None
    window = None
    idx = 0
    n_samples = 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        if idx % step:
            idx += 1
            continue
        ok, frame = cap.retrieve()
        if not ok or frame is None:
            idx += 1
            continue
        t = idx / fps
        h, w = frame.shape[:2]
        if model is not None and n_samples % ai_step == 0:
            aw = 448
            ai_buf.append(cv2.resize(frame, (aw, max(2, int(h * aw / w))), interpolation=cv2.INTER_AREA))
            ai_buf_t.append(t)
            if len(ai_buf) >= 16:
                ai_flush()
        if w != WORK_WIDTH:
            frame = cv2.resize(frame, (WORK_WIDTH, max(2, int(h * WORK_WIDTH / w))),
                               interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        lap = cv2.Laplacian(gray, cv2.CV_32F)
        rec["t"].append(t)
        rec["sharp"].append(float(lap.var()))
        rec["luma"].append(float(gray.mean()))
        rec["clo"].append(float((gray < 10).mean()))
        rec["chi"].append(float((gray > 245).mean()))
        b, g, r = frame.reshape(-1, 3).mean(axis=0)
        rec["r"].append(float(r))
        rec["g"].append(float(g))
        rec["b"].append(float(b))
        col = np.abs(lap).sum(axis=0)
        cs = col.sum()
        rec["cx"].append(float((np.arange(col.size) * col).sum() / cs / col.size) if cs > 0 else 0.5)
        # Brusokänslig skärpa: lätt utjämning tar bort sensorbrus och partiklar,
        # sedan mäts de starkaste kanterna (motivets konturer) i stället för hela bildens snitt
        den = cv2.GaussianBlur(gray, (0, 0), 1.0).astype(np.float32)
        gm = cv2.magnitude(cv2.Sobel(den, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(den, cv2.CV_32F, 0, 1, ksize=3))
        top = np.partition(gm.ravel(), int(gm.size * 0.95))[int(gm.size * 0.95):]
        # Brusnivå (Immerkær) – brusiga bilder får lägre skärpevärde, så att brus inte ser skarpt ut
        gf_ = gray.astype(np.float32)
        noise = float(np.sqrt(np.pi / 2) / (6 * max(1, (gf_.shape[1] - 2) * (gf_.shape[0] - 2)))
                      * np.abs(cv2.filter2D(gf_, -1, _NOISE_K)[1:-1, 1:-1]).sum())
        rec["focus"].append(float(top.mean()) / (1.0 + 0.6 * noise))
        sx, sy, spx, spy, sstr, sfocus = saliency(frame, gm)
        rec["sfocus"].append(sfocus)
        rec["sx"].append(sx)
        rec["sy"].append(sy)
        rec["spx"].append(spx)
        rec["spy"].append(spy)
        rec["sstr"].append(sstr)

        gf = gray.astype(np.float32)
        if window is None or window.shape != gf.shape:
            window = cv2.createHanningWindow(gf.shape[::-1], cv2.CV_32F)
        small = cv2.resize(gray, (64, 36), interpolation=cv2.INTER_AREA).astype(np.float32)
        hist = _hist(cv2.cvtColor(frame, cv2.COLOR_BGR2HSV))
        if prev_gray is not None and prev_gray.shape == gf.shape:
            (dx, dy), resp = cv2.phaseCorrelate(prev_gray, gf, window)
            if resp < 0.05:  # osäker mätning (t.ex. mycket rörelse i bilden) – anta ingen ryckning
                dx, dy = (rec["dx"][-1] * gf.shape[1], rec["dy"][-1] * gf.shape[1]) if rec["dx"] else (0.0, 0.0)
            diff = float(np.abs(small - prev_small).mean() / 255.0)
            bh = float(cv2.compareHist(prev_hist, hist, cv2.HISTCMP_BHATTACHARYYA))
            cut = bh > 0.45 and diff > 0.08
        else:
            dx = dy = 0.0
            diff = 0.0
            cut = False
        rec["dx"].append(float(dx) / gf.shape[1])
        rec["dy"].append(float(dy) / gf.shape[1])
        rec["diff"].append(diff)
        rec["cut"].append(bool(cut))
        hists.append(hist)
        if model is None and with_tags and tagging.AVAILABLE and n_samples % tag_step == 0:
            tag_frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            tag_times.append(t)
        prev_gray, prev_small, prev_hist = gf, small, hist
        n_samples += 1
        idx += 1
        if progress and total and n_samples % 20 == 0:
            progress(min(0.99, idx / total))
    cap.release()
    if model is not None:
        ai_flush()

    if n_samples < 2:
        raise RuntimeError("För kort eller oläsbart klipp")

    arr = {k: np.asarray(v, dtype=np.float32) for k, v in rec.items()}
    arr["cut"] = np.asarray(rec["cut"], dtype=bool)
    arr["hist"] = np.stack(hists).astype(np.float32)

    # Skakighet: andraderivatan av kamerans förflyttning (ryck), inte jämn panorering
    shift = np.stack([arr["dx"], arr["dy"]], axis=1)
    if len(shift) >= 3:  # medianfilter tar bort enstaka felmätningar (upprepade mönster, fiskar)
        padded = np.pad(shift, ((1, 1), (0, 0)), mode="edge")
        shift = np.median(np.stack([padded[:-2], padded[1:-1], padded[2:]]), axis=0)
    acc = np.zeros(len(shift), np.float32)
    if len(shift) >= 3:
        acc[1:-1] = np.linalg.norm(shift[2:] - 2 * shift[1:-1] + shift[:-2], axis=1)
    jitter = cv2.GaussianBlur(acc.reshape(1, -1), (5, 1), 0).ravel() if len(acc) >= 5 else acc
    arr["jitter"] = jitter.astype(np.float32)
    q, sharp_n, expo, stab = sample_quality(arr["sharp"], arr["luma"], arr["clo"], arr["chi"], jitter)
    # Början och slut av ett klipp är ofta skakiga (knapptryck)
    t = arr["t"]
    dur = float(t[-1]) + 1.0 / SAMPLE_FPS
    edge = (t < 0.6) | (t > dur - 0.6)
    q = np.where(edge, q * 0.6, q)
    arr["quality"] = q.astype(np.float32)
    arr["sharp_n"] = sharp_n.astype(np.float32)
    arr["expo"] = expo.astype(np.float32)
    arr["stab"] = stab.astype(np.float32)
    motion = np.linalg.norm(shift, axis=1) * 10.0 + arr["diff"] * 4.0
    arr["motion"] = np.clip(motion, 0, 1).astype(np.float32)

    # Motiv, intresse och skönhet med den inbyggda AI-modellen
    tags = []
    if model is not None and ai_rec["t"]:
        emb = np.concatenate(ai_rec["emb"])
        inter = np.concatenate(ai_rec["int"])
        probs = np.concatenate(ai_rec["probs"])
        arr["emb"] = emb.astype(np.float16)
        arr["emb_t"] = np.asarray(ai_rec["t"], np.float32)
        arr["ai_int"] = inter.astype(np.float32)
        arr["ai_beauty"] = np.concatenate(ai_rec["beauty"]).astype(np.float32)
        arr["ai_crop"] = np.stack(ai_rec["crop"]).astype(np.float32)
        arr["tag_probs"] = probs.astype(np.float16)
        sel = inter > 0.5
        tags = ai.summarize_tags(probs[sel] if sel.any() else probs[:0], model.labels, min_prob=0.2)
    elif tag_frames:
        tagger = tagging.get_tagger()
        if tagger is not None:
            emb, probs = tagger.embed(tag_frames)
            arr["emb"] = emb.astype(np.float16)
            arr["emb_t"] = np.asarray(tag_times, np.float32)
            arr["tag_probs"] = probs.astype(np.float16)
            tags = tagging.summarize_tags(probs, tagger.labels)

    # Färg: undervatten känns igen på svag röd kanal
    r_m, g_m, b_m = float(arr["r"].mean()), float(arr["g"].mean()), float(arr["b"].mean())
    underwater = ((g_m + b_m) / 2.0) / max(r_m, 1.0) > 1.45
    gray_m = (r_m + g_m + b_m) / 3.0
    strength = 0.55 if underwater else 0.25
    gains = [float(np.clip((gray_m / max(c, 1.0)) ** strength, 0.75, 1.8)) for c in (r_m, g_m, b_m)]
    if not tags:
        tags = ["Undervatten" if underwater else "Ovan ytan"]
    # Intresse och skönhet per prov (interpolerat från AI-bilderna), 0.5 = okänt
    if "ai_int" in arr:
        arr["interest"] = np.interp(t, arr["emb_t"], arr["ai_int"]).astype(np.float32)
        arr["beauty"] = np.interp(t, arr["emb_t"], arr["ai_beauty"]).astype(np.float32)
        q_sel = q * (0.4 + 0.6 * arr["interest"])
    else:
        q_sel = q

    # Bästa sekvens (3 s) för översikten
    win = max(1, int(3.0 * SAMPLE_FPS))
    if len(q) > win:
        csum = np.concatenate([[0.0], np.cumsum(q_sel)])
        means = (csum[win:] - csum[:-win]) / win
        bi = int(np.argmax(means))
        best = (float(t[bi]), float(t[min(bi + win, len(t) - 1)]))
        bsl = slice(bi, bi + win)
    else:
        best = (0.0, dur)
        bsl = slice(0, len(q))
    best_q = float(q[bsl].mean())
    best_sharp = float(sharp_n[bsl].mean())
    best_expo = float(expo[bsl].mean())
    best_stab = float(stab[bsl].mean())
    best_focus = float(arr["focus"][bsl].mean())
    best_sfocus = float(arr["sfocus"][bsl].mean())
    best_int = float(arr["interest"][bsl].mean()) if "interest" in arr else None
    best_beauty = float(arr["beauty"][bsl].mean()) if "beauty" in arr else None

    mean_motion = float(arr["motion"].mean())
    pan = float(np.abs(arr["dx"]).mean())
    if mean_motion < 0.08:
        movement = "Still"
    elif pan > abs(float(arr["dy"].mean())) * 1.5 and pan > 0.004:
        movement = "Panorering"
    else:
        movement = "Rörelse"

    out_npz = Path(out_npz)
    out_npz.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out_npz, **arr)

    return {
        "samples": int(n_samples),
        "duration": dur,
        "score": round(float(np.percentile(q, 75)), 3),
        "sharpness": round(float(np.median(sharp_n)), 3),
        "exposure": round(float(np.median(expo)), 3),
        "stability": round(float(np.median(stab)), 3),
        "motion": round(mean_motion, 3),
        "movement": movement,
        "underwater": bool(underwater),
        "wb_gains": [round(g, 3) for g in gains],
        "best": [round(best[0], 2), round(best[1], 2)],
        "best_q": round(best_q, 3), "best_sharp": round(best_sharp, 3),
        "best_expo": round(best_expo, 3), "best_stab": round(best_stab, 3),
        "subject": round(float(np.median(arr["sstr"])), 3),
        "best_focus": round(best_focus, 2), "best_sfocus": round(best_sfocus, 2),
        "best_interest": None if best_int is None else round(best_int, 3),
        "best_beauty": None if best_beauty is None else round(best_beauty, 3),
        "ai": "interest" in arr,
        "scenes": int(arr["cut"].sum()) + 1,
        "tags": tags,
        "has_embeddings": "emb" in arr,
    }


def load(npz_path) -> dict:
    with np.load(npz_path) as data:
        return {k: data[k] for k in data.files}
