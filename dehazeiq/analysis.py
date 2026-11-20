"""Bildanalys per klipp: skärpa, exponering, stabilitet, rörelse, scenbyten,
färgbalans och (valfritt) motiv med CLIP.

Varje klipp analyseras från sin proxyfil med cirka 4 prov per sekund.
Rådata sparas i en .npz-fil per klipp; en sammanfattning hamnar i projektet.
"""

from pathlib import Path

import cv2
import numpy as np

from . import tagging

SAMPLE_FPS = 4.0
WORK_WIDTH = 320
TAG_EVERY = 2.0  # sekunder mellan bildrutor till CLIP


def _hist(hsv):
    h = cv2.calcHist([hsv], [0, 1, 2], None, [8, 4, 4], [0, 180, 0, 256, 0, 256]).flatten()
    s = h.sum()
    return (h / s).astype(np.float32) if s > 0 else h.astype(np.float32)


def sample_quality(sharp, luma, clip_lo, clip_hi, jitter):
    """Kvalitet 0..1 per prov. Exponeras även för generatorn."""
    sharp_n = np.clip((np.log10(sharp + 1.0) - 1.0) / 1.6, 0.0, 1.0)
    expo = 1.0 - np.minimum(1.0, np.abs(luma - 118.0) / 110.0) - 2.0 * (clip_lo + clip_hi)
    expo = np.clip(expo, 0.0, 1.0)
    stab = np.clip(1.0 - jitter * 35.0, 0.0, 1.0)
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
                           "cx", "dx", "dy", "diff", "cut")}
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

        gf = gray.astype(np.float32)
        if window is None or window.shape != gf.shape:
            window = cv2.createHanningWindow(gf.shape[::-1], cv2.CV_32F)
        small = cv2.resize(gray, (64, 36), interpolation=cv2.INTER_AREA).astype(np.float32)
        hist = _hist(cv2.cvtColor(frame, cv2.COLOR_BGR2HSV))
        if prev_gray is not None and prev_gray.shape == gf.shape:
            (dx, dy), _ = cv2.phaseCorrelate(prev_gray, gf, window)
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
        if with_tags and tagging.AVAILABLE and n_samples % tag_step == 0:
            tag_frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            tag_times.append(t)
        prev_gray, prev_small, prev_hist = gf, small, hist
        n_samples += 1
        idx += 1
        if progress and total and n_samples % 20 == 0:
            progress(min(0.99, idx / total))
    cap.release()

    if n_samples < 2:
        raise RuntimeError("För kort eller oläsbart klipp")

    arr = {k: np.asarray(v, dtype=np.float32) for k, v in rec.items()}
    arr["cut"] = np.asarray(rec["cut"], dtype=bool)
    arr["hist"] = np.stack(hists).astype(np.float32)

    # Skakighet: andraderivatan av kamerans förflyttning (ryck), inte jämn panorering
    shift = np.stack([arr["dx"], arr["dy"]], axis=1)
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
    motion = np.linalg.norm(shift, axis=1) * 10.0 + arr["diff"] * 4.0
    arr["motion"] = np.clip(motion, 0, 1).astype(np.float32)

    # Motiv med CLIP (valfritt)
    tags = []
    if tag_frames:
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

    # Bästa sekvens (3 s) för översikten
    win = max(1, int(3.0 * SAMPLE_FPS))
    if len(q) > win:
        csum = np.concatenate([[0.0], np.cumsum(q)])
        means = (csum[win:] - csum[:-win]) / win
        bi = int(np.argmax(means))
        best = (float(t[bi]), float(t[min(bi + win, len(t) - 1)]))
    else:
        best = (0.0, dur)

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
        "scenes": int(arr["cut"].sum()) + 1,
        "tags": tags,
        "has_embeddings": "emb" in arr,
    }


def load(npz_path) -> dict:
    with np.load(npz_path) as data:
        return {k: data[k] for k in data.files}
