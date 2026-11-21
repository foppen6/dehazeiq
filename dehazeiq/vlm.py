"""Djupanalys med Qwen3-VL: en språk- och bildmodell som beskriver vad som händer i klippen.

Körs lokalt med llama.cpp (llama-server), som följer med Mac-versionen och använder
Apple-chipets grafikdel. Modellen (flera GB) laddas ner först när användaren ber om det.
Storleken väljs efter datorns minne:
    ≥ 32 GB  Qwen3-VL-30B-A3B (snabb trots storleken: bara ~3 miljarder parametrar per ord)
    ≥ 16 GB  Qwen3-VL-8B
    ≥  8 GB  Qwen3-VL-4B
"""

import base64
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import cv2

from .config import HOME
from .media import subprocess_kwargs

VLM_VERSION = 2  # 2: pratbubbla (caption)
HF = "https://huggingface.co"
MODELS = [  # (minsta minne i GB, repo, visningsnamn, ungefärlig nedladdning i GB)
    (32, "Qwen/Qwen3-VL-30B-A3B-Instruct-GGUF", "Qwen3-VL 30B", 19),
    (16, "Qwen/Qwen3-VL-8B-Instruct-GGUF", "Qwen3-VL 8B", 6),
    (8, "Qwen/Qwen3-VL-4B-Instruct-GGUF", "Qwen3-VL 4B", 3),
]
MODEL_DIR = HOME / "models" / "vlm"
_download = {"state": "idle", "progress": 0.0, "message": ""}
_dl_lock = threading.Lock()


# ---------- dator och program ----------

def ram_gb():
    try:
        if sys.platform == "darwin":
            out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True,
                                 **subprocess_kwargs()).stdout
            return int(out.strip()) / 2**30
        if sys.platform.startswith("win"):
            import ctypes

            class MEM(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MEM()
            m.dwLength = ctypes.sizeof(MEM)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return m.ullTotalPhys / 2**30
        with open("/proc/meminfo") as f:
            return int(f.readline().split()[1]) / 2**20
    except Exception:  # noqa: BLE001
        return 0.0


def server_binary():
    """llama-server: inbyggd i appen, eller angiven/installerad (för utveckling)."""
    name = "llama-server.exe" if sys.platform.startswith("win") else "llama-server"
    cands = []
    if os.environ.get("DEHAZEIQ_LLAMA"):
        cands.append(Path(os.environ["DEHAZEIQ_LLAMA"]))
    base = getattr(sys, "_MEIPASS", None)
    if base:
        cands.append(Path(base) / "llama" / name)
    here = Path(__file__).resolve().parent
    cands.append(here.parent / "packaging" / "llama" / name)
    for c in cands:
        if c.is_file():
            return c
    found = shutil.which(name)
    return Path(found) if found else None


def gpu_ok():
    """Bara Apple-chip (Metal) som standard – på äldre PC utan grafikkort blir det för långsamt."""
    if os.environ.get("DEHAZEIQ_VLM_FORCE"):
        return True
    return sys.platform == "darwin" and platform.machine() == "arm64"


def choose_model():
    gb = ram_gb()
    for need, repo, name, size in MODELS:
        if gb >= need:
            return {"repo": repo, "name": name, "size_gb": size}
    return None


def model_paths(repo):
    d = MODEL_DIR / repo.split("/")[-1]
    info = d / "files.json"
    if not info.exists():
        return None
    try:
        f = json.loads(info.read_text("utf-8"))
        m, p = d / f["model"], d / f["mmproj"]
        return (m, p) if m.exists() and p.exists() else None
    except (OSError, ValueError, KeyError):
        return None


def status():
    m = choose_model()
    st = {
        "supported": bool(server_binary()) and gpu_ok() and m is not None,
        "binary": bool(server_binary()), "gpu": gpu_ok(), "ram_gb": round(ram_gb()),
        "model": m["name"] if m else None, "size_gb": m["size_gb"] if m else None,
        "ready": bool(m and model_paths(m["repo"])),
    }
    with _dl_lock:
        st["download"] = dict(_download)
    return st


def ready():
    m = choose_model()
    return bool(server_binary()) and gpu_ok() and m is not None and model_paths(m["repo"]) is not None


# ---------- nedladdning ----------

def _pick_files(repo):
    req = urllib.request.Request(f"{HF}/api/models/{repo}", headers={"User-Agent": "DeHazeIQ"})
    with urllib.request.urlopen(req, timeout=60) as r:
        files = [s["rfilename"] for s in json.loads(r.read().decode("utf-8")).get("siblings", [])]
    gguf = [f for f in files if f.lower().endswith(".gguf")]
    mm = [f for f in gguf if "mmproj" in f.lower()]
    llm = [f for f in gguf if "mmproj" not in f.lower()]

    def pick(cands, prefs):
        for p in prefs:
            hit = [f for f in cands if p in f.lower()]
            if hit:
                return sorted(hit, key=len)[0]
        return sorted(cands, key=len)[0] if cands else None

    model = pick(llm, ["q4_k_m", "q4_k_s", "q5_k_m", "q8_0"])
    mmproj = pick(mm, ["f16", "q8_0", "bf16"])
    if not model or not mmproj:
        raise RuntimeError(f"Hittade inga modellfiler i {repo}")
    return model, mmproj


def _fetch(url, dst, report):
    part = dst.with_name(dst.name + ".part")
    have = part.stat().st_size if part.exists() else 0
    headers = {"User-Agent": "DeHazeIQ"}
    if have:
        headers["Range"] = f"bytes={have}-"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=120) as r:
        if have and r.status != 206:
            have = 0  # servern kan inte fortsätta – börja om
        total = have + int(r.headers.get("Content-Length") or 0)
        with open(part, "ab" if have else "wb") as f:
            done = have
            while True:
                chunk = r.read(1 << 22)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                report(done, total)
    part.replace(dst)


def download(progress=None):
    """Laddar ner den modell som passar datorn. Kan återupptas om den avbryts."""
    m = choose_model()
    if not m:
        raise RuntimeError("Datorn har för lite minne för djupanalys")

    def setp(frac, msg):
        with _dl_lock:
            _download.update(state="running", progress=round(frac, 4), message=msg)
        if progress:
            progress(frac, msg)

    try:
        d = MODEL_DIR / m["repo"].split("/")[-1]
        d.mkdir(parents=True, exist_ok=True)
        setp(0.0, "Söker modellfiler …")
        model, mmproj = _pick_files(m["repo"])
        files = [mmproj, model]  # den lilla först
        for i, rel in enumerate(files):
            dst = d / Path(rel).name
            if dst.exists():
                continue

            def report(done, total, i=i):
                share = 0.1 if i == 0 else 0.9
                start = 0.0 if i == 0 else 0.1
                frac = start + share * (done / total if total else 0)
                setp(frac, f"Laddar ner {m['name']}: {done / 2**30:.1f} av {total / 2**30:.1f} GB")
            _fetch(f"{HF}/{m['repo']}/resolve/main/{rel}", dst, report)
        (d / "files.json").write_text(json.dumps({"model": Path(model).name, "mmproj": Path(mmproj).name}), "utf-8")
        with _dl_lock:
            _download.update(state="done", progress=1.0, message="Klar")
        return {"model": m["name"]}
    except Exception as exc:
        with _dl_lock:
            _download.update(state="error", message=str(exc))
        raise


# ---------- server ----------

def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class Server:
    """Startar llama-server i bakgrunden och pratar med den via dess OpenAI-liknande API."""

    def __init__(self, model=None, mmproj=None, ctx=8192):
        if model is None:
            m = choose_model()
            paths = model_paths(m["repo"]) if m else None
            if not paths:
                raise RuntimeError("Djupanalysens modell är inte nedladdad")
            model, mmproj = paths
        self.port = _free_port()
        cmd = [str(server_binary()), "-m", str(model), "--mmproj", str(mmproj), "--host", "127.0.0.1",
               "--port", str(self.port), "-c", str(ctx), "-ngl", os.environ.get("DEHAZEIQ_NGL", "99")]
        log = open(HOME / "llama-server.log", "w", encoding="utf-8", errors="replace")
        self.proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, **subprocess_kwargs())
        self._log = log
        self._wait()

    def _wait(self, timeout=600):
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.proc.poll() is not None:
                raise RuntimeError("Djupanalysens modell kunde inte starta (se llama-server.log)")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=5) as r:
                    if r.status == 200:
                        return
            except Exception:  # noqa: BLE001
                pass
            time.sleep(1.0)
        raise RuntimeError("Djupanalysens modell startade inte i tid")

    def chat(self, text, images=(), max_tokens=300):
        content = [{"type": "text", "text": text}]
        for img in images:
            ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 88])
            if ok:
                b64 = base64.b64encode(buf.tobytes()).decode("ascii")
                content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
        body = {"messages": [{"role": "user", "content": content}], "temperature": 0.2,
                "max_tokens": max_tokens}
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/v1/chat/completions",
                                     data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            out = json.loads(r.read().decode("utf-8"))
        return out["choices"][0]["message"]["content"]

    def close(self):
        try:
            self.proc.terminate()
            self.proc.wait(timeout=20)
        except Exception:  # noqa: BLE001
            try:
                self.proc.kill()
            except Exception:  # noqa: BLE001
                pass
        self._log.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


# ---------- beskrivning av en bild ----------

PROMPT = """You are an expert nature and underwater film editor. Look at this frame from a {kind} video.
{hint}Reply with ONLY a JSON object, no other text. Write "subject" and "what" in SWEDISH (svenska).
Fields:
 "subject": Swedish common name of the main animal or subject, or "inget"
 "species": scientific name if you are fairly sure, else ""
 "what": one short Swedish sentence (max 12 words) about what is happening
 "action": 0-10 how much is happening
 "fun": 0-10 how funny, curious or charming the moment is
 "beauty": 0-10 visual beauty of the frame
 "sharp": true if the main subject is in focus
 "role": one of "intro", "action", "climax", "calm", "detail"
 "caption": a funny Swedish speech bubble from the animal's point of view, max 4 words
Example: {{"subject": "bläckfisk", "species": "Sepiola atlantica", "what": "Bläckfisken gräver ner sig i sanden",
"action": 6, "fun": 8, "beauty": 7, "sharp": true, "role": "climax", "caption": "Ni ser mig inte!"}}"""


def parse(text):
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except ValueError:
        return None

    def num(k):
        try:
            return max(0.0, min(10.0, float(d.get(k, 0))))
        except (TypeError, ValueError):
            return 0.0
    role = str(d.get("role", "")).strip().lower()
    return {
        "subject": str(d.get("subject", "") or "").strip()[:60],
        "species": str(d.get("species", "") or "").strip()[:80],
        "what": str(d.get("what", "") or "").strip()[:140],
        "action": num("action"), "fun": num("fun"), "beauty": num("beauty"),
        "sharp": bool(d.get("sharp", True)) if not isinstance(d.get("sharp"), str)
        else d["sharp"].strip().lower() in ("true", "ja", "yes"),
        "role": role if role in ("intro", "action", "climax", "calm", "detail") else "action",
        "caption": " ".join(str(d.get("caption", "") or "").split()[:5])[:40],
    }


def describe(server, frame_bgr, underwater=True, hint_species=()):
    h, w = frame_bgr.shape[:2]
    s = 768 / max(h, w)
    if s < 1:
        frame_bgr = cv2.resize(frame_bgr, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    hint = ""
    if hint_species:
        hint = ("A species classifier suggests (may be wrong): "
                + ", ".join(f"{sv} ({sci})" for sv, sci in hint_species) + ".\n")
    text = PROMPT.format(kind="underwater" if underwater else "nature/travel", hint=hint)
    for _ in range(2):
        r = parse(server.chat(text, [frame_bgr]))
        if r:
            return r
    return None
