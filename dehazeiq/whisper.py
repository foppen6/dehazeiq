"""Tal till text med Whisper (whisper.cpp), helt lokalt.

whisper-cli följer med appen (byggs av byggsystemet). Modellen laddas ner första gången:
    Mac (Apple-chip):  large-v3-turbo (0,57 GB) – bäst, snabb med grafikdelen
    PC:                small (0,19 GB) – snabbare på processorn (turbo går att välja)
En liten röstdetektor (Silero VAD, 1 MB) gör att bubbel, vind och motorljud inte blir påhittad text.

Resultat per klipp: clip["speech"] = {"v", "model", "lang", "segments": [{"start","end","text","p"}]}
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from . import net

net.setup()

from .config import HOME
from .media import ffmpeg, subprocess_kwargs

SPEECH_VERSION = 1
HF = "https://huggingface.co"
MODELS = [
    {"id": "turbo", "file": "ggml-large-v3-turbo-q5_0.bin", "name": "Whisper large-v3-turbo", "size": 0.57,
     "about": "Bäst kvalitet, snabb på Mac. Långsam på äldre PC."},
    {"id": "small", "file": "ggml-small-q5_1.bin", "name": "Whisper small", "size": 0.19,
     "about": "Snabbare på äldre datorer, lite sämre på svenska."},
    {"id": "base", "file": "ggml-base-q5_1.bin", "name": "Whisper base", "size": 0.06,
     "about": "Snabbast, för korta repliker."},
]
VAD_FILE = "ggml-silero-v5.1.2.bin"
VAD_URL = f"{HF}/ggml-org/whisper-vad/resolve/main/{VAD_FILE}"
MODEL_DIR = HOME / "models" / "whisper"
CHOICE_FILE = HOME / "whisper.json"
LANGS = {"auto": "Automatiskt", "sv": "Svenska", "en": "Engelska"}

_dl = {"state": "idle", "progress": 0.0, "message": ""}
_lock = threading.Lock()

# Whisper "hör" ibland de här fraserna i tystnad eller brus – de räknas inte som tal
HALLU = re.compile(
    r"(tack för att (ni|du) (tittade|lyssnade|kollade)|textning|undertext(er|ning)|svensktextning|"
    r"prenumerera|subscribe|thanks? for watching|thank you\.?$|^\W*(musik|music|applåder|applause)\W*$|"
    r"amara\.org|www\.|\.com|^\W*$|^\s*\[.*\]\s*$|^\s*\(.*\)\s*$|♪)", re.I)


# ---------- program och modell ----------

def binary():
    name = "whisper-cli.exe" if sys.platform.startswith("win") else "whisper-cli"
    cands = []
    if os.environ.get("DEHAZEIQ_WHISPER"):
        cands.append(Path(os.environ["DEHAZEIQ_WHISPER"]))
    base = getattr(sys, "_MEIPASS", None)
    if base:
        cands.append(Path(base) / "whisper" / name)
    here = Path(__file__).resolve().parent
    cands.append(here.parent / "packaging" / "whisper" / name)
    for c in cands:
        if c.is_file():
            return c
    found = shutil.which(name)
    return Path(found) if found else None


def default_id():
    """Stora modellen på Apple-chip (grafikdelen gör jobbet), mindre på PC där processorn räknar."""
    import platform
    return "turbo" if sys.platform == "darwin" and platform.machine() == "arm64" else "small"


def chosen_id():
    try:
        mid = json.loads(CHOICE_FILE.read_text("utf-8")).get("model")
        if mid in {m["id"] for m in MODELS}:
            return mid
    except (OSError, ValueError):
        pass
    have = [m["id"] for m in MODELS if (MODEL_DIR / m["file"]).is_file()]
    return have[0] if have else default_id()


def settings():
    try:
        return json.loads(CHOICE_FILE.read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(**kw):
    s = settings()
    kw = {k: v for k, v in kw.items() if v is not None}
    if "model" in kw and kw["model"] not in {m["id"] for m in MODELS}:
        raise ValueError("Okänd talmodell")
    if "lang" in kw and kw["lang"] not in LANGS:
        raise ValueError("Okänt språk")
    s.update(kw)
    CHOICE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CHOICE_FILE.write_text(json.dumps(s), "utf-8")
    return s


def model():
    mid = chosen_id()
    return next(m for m in MODELS if m["id"] == mid)


def model_path(m=None):
    m = m or model()
    p = MODEL_DIR / m["file"]
    return p if p.is_file() else None


def vad_path():
    p = MODEL_DIR / VAD_FILE
    return p if p.is_file() else None


def ready():
    return bool(binary() and model_path())


def whisper_status():
    m = model()
    with _lock:
        dl = dict(_dl)
    return {
        "available": bool(binary()),
        "ready": ready(),
        "model": {"id": m["id"], "name": m["name"], "size_gb": m["size"]},
        "models": [{"id": x["id"], "name": x["name"], "size_gb": x["size"], "about": x["about"],
                    "installed": bool(model_path(x)), "current": x["id"] == m["id"],
                    "recommended": x["id"] == default_id()} for x in MODELS],
        "lang": settings().get("lang", "auto"),
        "langs": LANGS,
        "download": dl,
    }


def download(progress=None, model_id=None):
    from .vlm import _fetch
    if model_id:
        save_settings(model=model_id)
    m = model()

    def setp(frac, msg):
        with _lock:
            _dl.update(state="running", progress=round(frac, 4), message=msg)
        if progress:
            progress(frac, msg)

    try:
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        if not vad_path():
            setp(0.0, "Hämtar röstdetektorn …")
            try:
                _fetch(VAD_URL, MODEL_DIR / VAD_FILE, lambda d, t: None)
            except Exception as e:  # noqa: BLE001 – fungerar utan, bara sämre mot brus
                print("Röstdetektorn kunde inte hämtas:", e)
        dst = MODEL_DIR / m["file"]
        if not dst.exists():
            _fetch(f"{HF}/ggerganov/whisper.cpp/resolve/main/{m['file']}", dst,
                   lambda d, t: setp(d / t if t else 0, f"Laddar ner {m['name']}: "
                                     f"{d / 2**20:.0f} av {t / 2**20:.0f} MB"))
        with _lock:
            _dl.update(state="done", progress=1.0, message="Klar")
        return {"model": m["name"]}
    except Exception as exc:
        with _lock:
            _dl.update(state="error", message=str(exc))
        raise


# ---------- transkribering ----------

def _extract_wav(src, dst, max_s=None):
    cmd = [ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-vn",
           "-map", "0:a:0", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le"]
    if max_s:
        cmd += ["-t", f"{max_s:.2f}"]
    cmd.append(str(dst))
    r = subprocess.run(cmd, capture_output=True, **subprocess_kwargs())
    return r.returncode == 0 and Path(dst).exists() and Path(dst).stat().st_size > 3200


def _ms(v):
    return float(v) / 1000.0


def clean_text(t):
    t = re.sub(r"\s+", " ", (t or "").replace("[BLANK_AUDIO]", "")).strip()
    t = re.sub(r"^[-–—]\s*", "", t)
    return t


def is_speech(text, p=1.0):
    t = clean_text(text)
    if len(re.sub(r"[^\wåäöÅÄÖ]", "", t)) < 2 or HALLU.search(t):
        return False
    words = re.findall(r"\w+", t.lower())
    if len(words) >= 4 and len(set(words)) <= max(1, len(words) // 4):
        return False  # "la la la la la" – upprepning
    return p >= 0.4


def parse_json(data):
    """whisper-cli --output-json(-full) → [{"start","end","text","p"}]."""
    segs = []
    for s in data.get("transcription") or []:
        off = s.get("offsets") or {}
        toks = [t for t in (s.get("tokens") or []) if not str(t.get("text", "")).startswith("[_")]
        p = sum(float(t.get("p", 1)) for t in toks) / len(toks) if toks else 1.0
        text = clean_text(s.get("text"))
        if not is_speech(text, p):
            continue
        a, b = _ms(off.get("from", 0)), _ms(off.get("to", 0))
        if b - a < 0.25:
            continue
        segs.append({"start": round(a, 2), "end": round(b, 2), "text": text, "p": round(p, 3)})
    lang = (data.get("result") or {}).get("language")
    return segs, lang


def transcribe(src, lang=None, threads=None):
    """Transkriberar ljudet i en video eller ljudfil. Returnerar {"segments", "lang"}."""
    exe, m = binary(), model_path()
    if not exe or not m:
        raise RuntimeError("Tal till text är inte installerat")
    lang = lang or settings().get("lang", "auto")
    threads = threads or max(2, min(8, (os.cpu_count() or 4) - 1))
    with tempfile.TemporaryDirectory(prefix="dhq_whisper_") as td:
        wav = Path(td) / "a.wav"
        if not _extract_wav(src, wav):
            return {"segments": [], "lang": None}
        out = Path(td) / "out"
        cmd = [str(exe), "-m", str(m), "-f", str(wav), "-l", lang, "-t", str(threads),
               "-ojf", "-of", str(out), "-np", "-sns", "-mc", "0"]
        v = vad_path()
        if v:
            cmd += ["--vad", "--vad-model", str(v)]
        r = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=3600,
                           **subprocess_kwargs())
        js = out.with_suffix(".json")
        if r.returncode != 0 or not js.exists():
            if v:  # en äldre whisper-cli utan röstdetektor? försök igen utan
                cmd = cmd[: cmd.index("--vad")]
                r = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=3600,
                                   **subprocess_kwargs())
            if r.returncode != 0 or not js.exists():
                raise RuntimeError("Whisper misslyckades: " + (r.stderr or "")[-300:])
        data = json.loads(js.read_bytes().decode("utf-8", errors="replace"))
    segs, det = parse_json(data)
    return {"segments": segs, "lang": det or (None if lang == "auto" else lang)}


# ---------- användning i filmer ----------

def speech_in(clip, a, b):
    """Talsegment som överlappar [a, b] i klippets egen tid."""
    sp = (clip or {}).get("speech") or {}
    return [s for s in sp.get("segments") or [] if s["end"] > a + 0.1 and s["start"] < b - 0.1]


def speech_share(clip, a=None, b=None):
    """Andel av [a, b] där någon pratar (0–1)."""
    sp = (clip or {}).get("speech") or {}
    segs = sp.get("segments") or []
    if not segs:
        return 0.0
    a = 0.0 if a is None else a
    b = float(clip.get("duration") or segs[-1]["end"]) if b is None else b
    if b <= a:
        return 0.0
    tot = sum(max(0.0, min(b, s["end"]) - max(a, s["start"])) for s in segs)
    return min(1.0, tot / (b - a))


def snap_to_speech(clip, a, b, max_len=None):
    """Flytta/förläng ett utsnitt så att det inte klipper av en mening mitt i."""
    segs = speech_in(clip, a, b)
    if not segs:
        return a, b
    dur = float(clip.get("duration") or b)
    na = min(a, segs[0]["start"] - 0.15) if segs[0]["start"] < a else a
    nb = max(b, segs[-1]["end"] + 0.2) if segs[-1]["end"] > b else b
    na, nb = max(0.0, na), min(dur, nb)
    if max_len and nb - na > max_len:
        return a, b
    return round(na, 2), round(nb, 2)


def _shot_src(s):
    speed = float((s.get("fx") or {}).get("speed") or 1.0) or 1.0
    a = float(s.get("src_start", 0))
    b = float(s.get("src_end") or a + float(s.get("duration", 0)) * speed)
    return a, b, speed


def speech_ranges(prop, clips):
    """Tider i filmen där någon pratar (bara klipp i normal fart): [(start, slut)]."""
    out = []
    for s in prop.get("shots", []):
        c = clips.get(s.get("clip_id"))
        if not c or not c.get("speech"):
            continue
        a, b, speed = _shot_src(s)
        if abs(speed - 1.0) > 0.1:
            continue
        at = float(s.get("at", 0))
        for seg in speech_in(c, a, b):
            sa = at + max(a, seg["start"]) - a
            sb = at + min(b, seg["end"]) - a
            if sb - sa >= 0.3:
                out.append((round(sa, 2), round(sb, 2)))
    return out


def subtitle_cues(prop, clips):
    """Undertexter för en film: [(start, slut, text)] i filmens tid, från klippens tal."""
    cues = []
    for s in prop.get("shots", []):
        c = clips.get(s.get("clip_id"))
        if not c or not c.get("speech"):
            continue
        a, b, speed = _shot_src(s)
        if abs(speed - 1.0) > 0.1:
            continue  # snabbspolat eller slowmotion: talet hörs inte begripligt
        at = float(s.get("at", 0))
        for seg in speech_in(c, a, b):
            sa = at + max(a, seg["start"]) - a
            sb = at + min(b, seg["end"]) - a + 0.25
            sb = min(sb, at + float(s.get("duration", sb - at)))
            if sb - sa < 0.5:
                continue
            for part, pa, pb in _split(seg["text"], sa, sb):
                cues.append((round(pa, 2), round(pb, 2), part))
    return cues


def _split(text, a, b, max_chars=42):
    """Dela långa repliker i rader som hinner läsas."""
    words = text.split()
    lines, cur = [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_chars:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    chunks = ["\n".join(lines[i:i + 2]) for i in range(0, len(lines), 2)]
    if len(chunks) <= 1:
        return [(text if len(lines) <= 1 else "\n".join(lines), a, b)]
    total = sum(len(c) for c in chunks)
    out, t = [], a
    for c in chunks:
        d = (b - a) * len(c) / total
        out.append((c, t, t + d))
        t += d
    return out


def srt(cues):
    def ts(x):
        h, r = divmod(int(x * 1000), 3600000)
        m, r = divmod(r, 60000)
        s, ms = divmod(r, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    return "\n".join(f"{i}\n{ts(a)} --> {ts(b)}\n{t}\n" for i, (a, b, t) in enumerate(cues, 1))
