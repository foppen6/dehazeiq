"""FFmpeg/ffprobe-hjälpare: metadata, proxyfiler, kodare."""

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from .config import PROXY_SHORT_SIDE


class MediaError(RuntimeError):
    pass


def _bundled_dirs():
    """Platser där en inbakad FFmpeg kan ligga i den installerade appen."""
    dirs = []
    base = getattr(sys, "_MEIPASS", None)
    if base:
        dirs.append(Path(base) / "ffmpeg")
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        dirs += [exe_dir / "ffmpeg", exe_dir.parent / "Frameworks" / "ffmpeg",
                 exe_dir.parent / "Resources" / "ffmpeg"]
    return dirs


def _find_bin(name: str) -> str:
    exe = name + (".exe" if sys.platform.startswith("win") else "")
    for d in _bundled_dirs():  # den installerade appens egen FFmpeg först
        p = d / exe
        if p.exists():
            return str(p)
    found = shutil.which(name)
    if found:
        return found
    dirs = ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin"]
    if sys.platform.startswith("win"):
        local = os.environ.get("LOCALAPPDATA", "")
        dirs = [os.path.join(local, "Microsoft", "WinGet", "Links"), r"C:\ffmpeg\bin",
                r"C:\Program Files\ffmpeg\bin"]
        name += ".exe"
    for d in dirs:
        p = Path(d) / name
        if p.exists():
            return str(p)
    hint = ("winget install ffmpeg" if sys.platform.startswith("win") else "brew install ffmpeg")
    raise MediaError(f"Hittar inte {name}. Installera FFmpeg, till exempel med: {hint}")


@lru_cache(maxsize=None)
def ffmpeg() -> str:
    return _find_bin("ffmpeg")


@lru_cache(maxsize=None)
def ffprobe() -> str:
    return _find_bin("ffprobe")


IS_WIN = sys.platform.startswith("win")
# Windows: inget konsolfönster för FFmpeg och lägre prioritet så att datorn går att använda samtidigt
_WIN_FLAGS = (0x08000000 | 0x00004000) if IS_WIN else 0  # CREATE_NO_WINDOW | BELOW_NORMAL_PRIORITY_CLASS


def subprocess_kwargs():
    """Gemensamma inställningar för alla bakgrundsprocesser (FFmpeg m.fl.)."""
    if IS_WIN:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
        return {"creationflags": _WIN_FLAGS, "startupinfo": si}
    return {}


def lower_priority():
    """Kör hela DeHazeIQ med låg prioritet: analys och rendering tar bara ledig datorkraft."""
    try:
        if IS_WIN:
            import ctypes
            k32 = ctypes.windll.kernel32
            k32.SetPriorityClass(k32.GetCurrentProcess(), 0x00004000)  # BELOW_NORMAL
        else:
            os.nice(10)  # ärvs av FFmpeg-processerna
    except Exception:  # noqa: BLE001
        pass
    try:
        import cv2
        cv2.setNumThreads(max(1, (os.cpu_count() or 2) // 2))
    except Exception:  # noqa: BLE001
        pass


def run(cmd, timeout=None):
    """Kör ett kommando och kasta MediaError med slutet av stderr vid fel."""
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout, **subprocess_kwargs())
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        tail = "\n".join(err[-8:])
        raise MediaError(f"{Path(cmd[0]).name} misslyckades:\n{tail}")
    return proc


@lru_cache(maxsize=None)
def has_encoder(name: str) -> bool:
    try:
        out = run([ffmpeg(), "-hide_banner", "-encoders"]).stdout.decode("utf-8", "replace")
    except MediaError:
        return False
    return re.search(rf"\s{re.escape(name)}\s", out) is not None


# Hårdvarukodare per plattform, i prioritetsordning
_HW_LABELS = {
    "h264_videotoolbox": "Apple VideoToolbox",
    "h264_nvenc": "Nvidia NVENC",
    "h264_qsv": "Intel Quick Sync",
    "h264_amf": "AMD AMF",
}


def _hw_candidates():
    if sys.platform == "darwin":
        return ["h264_videotoolbox"]
    if sys.platform.startswith("win"):
        return ["h264_nvenc", "h264_qsv", "h264_amf"]
    return ["h264_nvenc", "h264_qsv"]


def _encoder_works(name: str) -> bool:
    """Finns kodaren och fungerar den på just den här datorn? Prova en kort kodning."""
    if not has_encoder(name):
        return False
    try:
        run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-f", "lavfi",
             "-i", "color=black:s=256x256:d=0.2", *_encoder_args(name, 256, 256, "preview"),
             "-f", "null", "-"], timeout=30)
        return True
    except Exception:  # noqa: BLE001
        return False


_HW = "unset"


def hw_encoder():
    """Namnet på en fungerande hårdvarukodare, eller None (då används libx264)."""
    global _HW
    if _HW == "unset":
        if os.environ.get("DEHAZEIQ_NO_HW"):
            _HW = None
        else:
            _HW = next((e for e in _hw_candidates() if _encoder_works(e)), None)
    return _HW


def encoder_label() -> str:
    hw = hw_encoder()
    return _HW_LABELS.get(hw, "Programkodning (x264)") if hw else "Programkodning (x264)"


def use_videotoolbox() -> bool:  # bakåtkompatibelt
    return hw_encoder() == "h264_videotoolbox"


def _encoder_args(name, width, height, quality):
    pixels = width * height
    final = quality == "final"
    if name == "h264_videotoolbox":
        base = 14000 if final else (2500 if quality == "proxy" else 4000)
        kbps = int(base * pixels / (1920 * 1080)) if quality != "proxy" else base
        kbps = max(1500, min(kbps, 80000))
        return ["-c:v", name, "-b:v", f"{kbps}k", "-maxrate", f"{int(kbps * 1.5)}k",
                "-profile:v", "high", "-pix_fmt", "yuv420p"]
    q = "19" if final else ("27" if quality == "proxy" else "24")
    if name == "h264_nvenc":
        return ["-c:v", name, "-preset", "p5", "-rc", "vbr", "-cq", q, "-b:v", "0",
                "-profile:v", "high", "-pix_fmt", "yuv420p"]
    if name == "h264_qsv":
        return ["-c:v", name, "-global_quality", q, "-look_ahead", "0",
                "-profile:v", "high", "-pix_fmt", "nv12"]
    if name == "h264_amf":
        return ["-c:v", name, "-quality", "quality", "-rc", "cqp", "-qp_i", q, "-qp_p", q,
                "-profile:v", "high", "-pix_fmt", "yuv420p"]
    crf = "18" if final else ("26" if quality == "proxy" else "24")
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", crf,
            "-pix_fmt", "yuv420p", "-profile:v", "high"]


def video_encoder_args(width: int, height: int, quality: str = "final"):
    """Kodarinställningar: hårdvarukodning om den finns, annars libx264.
    quality: 'final', 'preview' eller 'proxy'."""
    return _encoder_args(hw_encoder() or "libx264", width, height, quality)


def _parse_rate(rate: str) -> float:
    try:
        if "/" in rate:
            a, b = rate.split("/")
            return float(a) / float(b) if float(b) else 0.0
        return float(rate)
    except (ValueError, ZeroDivisionError):
        return 0.0


def _parse_time(value: str):
    if not value:
        return None
    try:
        v = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return None


def detect_source(path: Path, tags: dict) -> str:
    name = path.name.upper()
    make = (tags.get("com.apple.quicktime.make") or tags.get("make") or "").lower()
    model = (tags.get("com.apple.quicktime.model") or tags.get("model") or "").lower()
    if path.suffix.lower() == ".insv" or "insta360" in make or "insta360" in model:
        return "Insta360"
    if name.startswith("VID_") and re.match(r"VID_\d{8}_\d{6}", name):
        return "Insta360"
    if "nikon" in make or name.startswith("DSC_") or name.startswith("_DSC"):
        return "Nikon"
    if name.startswith(("GX", "GH", "GOPR")) or "gopro" in make:
        return "GoPro"
    if make in ("apple", "google", "samsung") or name.startswith(("PXL_", "IMG_")):
        return "Mobil"
    return "Kamera"


def probe(path) -> dict:
    """Läs metadata med ffprobe och returnera en förenklad beskrivning."""
    path = Path(path)
    out = run([ffprobe(), "-v", "error", "-print_format", "json",
               "-show_format", "-show_streams", str(path)]).stdout
    data = json.loads(out or b"{}")
    streams = data.get("streams", [])
    fmt = data.get("format", {})
    tags = {k.lower(): v for k, v in (fmt.get("tags") or {}).items()}
    # Behåll originalnycklar för Apple-taggar
    tags.update({k: v for k, v in (fmt.get("tags") or {}).items()})

    vstreams = [s for s in streams if s.get("codec_type") == "video"
                and not (s.get("disposition") or {}).get("attached_pic")]
    astreams = [s for s in streams if s.get("codec_type") == "audio"]

    info = {
        "path": str(path),
        "name": path.name,
        "size": path.stat().st_size,
        "duration": float(fmt.get("duration") or 0.0),
        "has_audio": bool(astreams),
        "video_streams": len(vstreams),
        "tags": {k: v for k, v in tags.items() if isinstance(v, str) and len(v) < 200},
    }
    if vstreams:
        v = vstreams[0]
        w, h = int(v.get("width") or 0), int(v.get("height") or 0)
        rotation = 0
        for sd in v.get("side_data_list") or []:
            if "rotation" in sd:
                try:
                    rotation = int(float(sd["rotation"]))
                except (TypeError, ValueError):
                    pass
        if not rotation and (v.get("tags") or {}).get("rotate"):
            try:
                rotation = int(v["tags"]["rotate"])
            except ValueError:
                pass
        if abs(rotation) % 180 == 90:
            w, h = h, w
        fps = _parse_rate(v.get("avg_frame_rate") or "") or _parse_rate(v.get("r_frame_rate") or "")
        info.update({
            "width": w,
            "height": h,
            "fps": round(fps, 3) if fps else 30.0,
            "codec": v.get("codec_name", ""),
            "pix_fmt": v.get("pix_fmt", ""),
            "bit_depth": 10 if "10" in (v.get("pix_fmt") or "") else 8,
            "rotation": rotation,
        })
        if not info["duration"]:
            info["duration"] = float(v.get("duration") or 0.0)
    created = None
    for key in ("com.apple.quicktime.creationdate", "creation_time"):
        created = _parse_time(tags.get(key, ""))
        if created:
            break
    info["created"] = created or path.stat().st_mtime
    loc = tags.get("com.apple.quicktime.location.ISO6709") or tags.get("location")
    info["location"] = loc
    info["source"] = detect_source(path, tags)
    w, h = info.get("width", 0), info.get("height", 0)
    info["is360"] = (path.suffix.lower() == ".insv" or len(vstreams) > 1
                     or (info["source"] == "Insta360" and h and abs(w / h - 2.0) < 0.02))
    return info


def make_proxy(src, dst, info: dict):
    """Skapa en lätt H.264-proxy (kortsida 540 px) för analys och förhandsvisning."""
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".tmp.mp4")
    s = PROXY_SHORT_SIDE
    scale = f"scale='if(gt(iw,ih),-2,{s})':'if(gt(iw,ih),{s},-2)':flags=bicubic"
    vf = scale
    if info.get("fps", 30) > 31:
        vf += ",fps=30"
    vf += ",format=yuv420p"
    cmd = [ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
           "-map", "0:v:0", "-map", "0:a:0?", "-vf", vf, "-g", "15"]
    cmd += _encoder_args(hw_encoder() or "libx264", 960, 540, "proxy")
    cmd += ["-c:a", "aac", "-b:a", "96k", "-ac", "2", "-movflags", "+faststart", str(tmp)]
    run(cmd)
    os.replace(tmp, dst)
    return dst
