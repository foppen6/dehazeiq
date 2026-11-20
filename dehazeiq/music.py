"""Musikanalys utan extra beroenden: tempo (BPM), taktslag och energi.

Ljudet avkodas med FFmpeg till mono 22 kHz. Takten hittas med spektralt
flöde (onset-kurva) och autokorrelation.
"""

import subprocess

import numpy as np

from .media import MediaError, ffmpeg

SR = 22050
HOP = 512
FRAME = 1024


def decode(path, sr=SR) -> np.ndarray:
    proc = subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-i", str(path),
                           "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                          capture_output=True)
    if proc.returncode != 0:
        raise MediaError("Kunde inte läsa musikfilen: "
                         + proc.stderr.decode("utf-8", "replace")[-300:])
    return np.frombuffer(proc.stdout, dtype=np.float32)


def onset_envelope(y: np.ndarray) -> np.ndarray:
    if len(y) < FRAME * 4:
        return np.zeros(1, np.float32)
    n = 1 + (len(y) - FRAME) // HOP
    idx = np.arange(FRAME)[None, :] + HOP * np.arange(n)[:, None]
    frames = y[idx] * np.hanning(FRAME).astype(np.float32)[None, :]
    mag = np.abs(np.fft.rfft(frames, axis=1))
    logmag = np.log1p(10.0 * mag)
    flux = np.maximum(0.0, np.diff(logmag, axis=0)).sum(axis=1)
    flux = np.concatenate([[0.0], flux])
    # Ta bort långsam trend och normalisera
    k = 16
    if len(flux) > k:
        trend = np.convolve(flux, np.ones(k) / k, mode="same")
        flux = np.maximum(0.0, flux - trend)
    m = flux.max()
    return (flux / m).astype(np.float32) if m > 0 else flux.astype(np.float32)


def estimate_tempo(env: np.ndarray, sr=SR, hop=HOP, lo=60.0, hi=180.0):
    fps = sr / hop
    if len(env) < fps * 4:
        return 0.0, 0.0
    # Jämna ut skarpa toppar så att taktperioder som inte är heltal ändå matchar
    k = np.exp(-0.5 * (np.arange(-4, 5) / 1.5) ** 2)
    e = np.convolve(env, k / k.sum(), mode="same")
    e = e - e.mean()
    n = len(e)
    spec = np.fft.rfft(e, 2 * n)
    ac = np.fft.irfft(spec * np.conj(spec))[:n]
    ac /= ac[0] if ac[0] else 1.0
    lag_min = int(fps * 60.0 / hi)
    lag_max = min(n - 2, int(fps * 60.0 / lo))
    lags = np.arange(lag_min, lag_max + 1)
    bpms = 60.0 * fps / lags
    # Lätt förväntan runt 110 BPM så att dubbelt/halvt tempo inte vinner
    prior = np.exp(-0.5 * (np.log2(bpms / 110.0) / 0.9) ** 2)
    score = ac[lags] * prior
    i = int(np.argmax(score))
    lag = float(lags[i])
    if 0 < i < len(lags) - 1:  # parabolisk interpolation
        a, b, c = score[i - 1], score[i], score[i + 1]
        denom = a - 2 * b + c
        if denom:
            lag += 0.5 * (a - c) / denom
    return 60.0 * fps / lag, lag


def beat_times(env: np.ndarray, period: float, sr=SR, hop=HOP) -> np.ndarray:
    if period <= 0:
        return np.zeros(0)
    best_off, best = 0.0, -1.0
    for off in np.linspace(0, period, int(period) + 1, endpoint=False):
        pos = np.arange(off, len(env) - 1, period).astype(int)
        s = env[pos].sum()
        if s > best:
            best, best_off = s, off
    pos = np.arange(best_off, len(env) - 1, period)
    return pos * hop / sr


def analyze(path) -> dict:
    y = decode(path)
    duration = len(y) / SR
    env = onset_envelope(y)
    bpm, period = estimate_tempo(env)
    beats = beat_times(env, period)
    # Energi per sekund (för framtida dramaturgi)
    sec = SR
    n = int(len(y) // sec)
    energy = []
    if n:
        rms = np.sqrt((y[: n * sec].reshape(n, sec) ** 2).mean(axis=1))
        mx = rms.max() or 1.0
        energy = [round(float(v / mx), 3) for v in rms]
    return {
        "path": str(path),
        "duration": round(duration, 3),
        "bpm": round(float(bpm), 1),
        "beats": [round(float(b), 3) for b in beats],
        "energy": energy,
    }
