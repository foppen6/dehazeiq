"""Stillbilder i filmerna.

Varje foto görs om till ett kort stillbildsklipp (H.264, några sekunder) när det importeras.
Då fungerar analys, AI, generator, redigering och rendering precis som för video. Klippet får
flaggan is_photo, och effektplanen ger det en långsam rörelse mot motivet (Ken Burns).

Format: JPG, PNG, TIFF, WebP, HEIC/HEIF (om pillow-heif finns) och RAW (NEF, ARW, CR2, CR3,
DNG, RAF, ORF, RW2: den största inbäddade JPEG-förhandsbilden används).
"""

import io
import os
from datetime import datetime
from pathlib import Path

from .media import ffmpeg, run

PHOTO_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".heic", ".heif",
             ".nef", ".arw", ".cr2", ".cr3", ".dng", ".raf", ".orf", ".rw2"}
RAW_EXT = {".nef", ".arw", ".cr2", ".cr3", ".dng", ".raf", ".orf", ".rw2"}
PHOTO_SECONDS = 6.0   # stillbildsklippets längd (generatorn väljer 2–4 s av det)
MAX_SIDE = 3840       # långsidan på stillbildsklippet (räcker till 4K och lite zoom)

try:
    from PIL import Image, ImageOps
    try:
        import pillow_heif  # type: ignore
        pillow_heif.register_heif_opener()
        HEIF = True
    except Exception:  # noqa: BLE001
        HEIF = False
    PIL_OK = True
except Exception:  # noqa: BLE001
    PIL_OK = HEIF = False


def is_photo_file(path) -> bool:
    return Path(path).suffix.lower() in PHOTO_EXT


def _embedded_jpeg(data: bytes):
    """Största inbäddade JPEG i en RAW-fil (kamerans egen förhandsbild, ofta i full upplösning)."""
    best, best_px = None, 0
    pos = 0
    while True:
        i = data.find(b"\xff\xd8\xff", pos)
        if i < 0:
            break
        pos = i + 3
        try:
            im = Image.open(io.BytesIO(data[i:]))
            px = im.size[0] * im.size[1]
            if px > best_px:
                im.load()
                best, best_px = im, px
        except Exception:  # noqa: BLE001
            continue
        if len(data) > 200_000_000:
            break
    return best


def _exif_time(im):
    try:
        ex = im.getexif()
        raw = None
        try:
            raw = ex.get_ifd(0x8769).get(0x9003)  # DateTimeOriginal
        except Exception:  # noqa: BLE001
            pass
        raw = raw or ex.get(0x0132)  # DateTime
        if raw:
            return datetime.strptime(str(raw).strip()[:19], "%Y:%m:%d %H:%M:%S").timestamp()
    except Exception:  # noqa: BLE001
        pass
    return None


def _exif_camera(im):
    try:
        ex = im.getexif()
        make, model = str(ex.get(0x010F) or "").strip(), str(ex.get(0x0110) or "").strip()
        return make, model
    except Exception:  # noqa: BLE001
        return "", ""


def load(path):
    """Öppna fotot rättvänt i RGB. Returnerar (bild, tidpunkt, märke, modell)."""
    path = Path(path)
    if not PIL_OK:
        raise RuntimeError("Bildstöd saknas i den här installationen")
    if path.suffix.lower() in RAW_EXT:
        data = path.read_bytes()
        im = _embedded_jpeg(data)
        if im is None:
            raise RuntimeError("Hittade ingen förhandsbild i RAW-filen")
        meta = im
        try:
            outer = Image.open(path)  # TIFF-baserade RAW (NEF, DNG …) har EXIF i ytterfilen
            meta = outer if outer.getexif() else im
        except Exception:  # noqa: BLE001
            pass
    else:
        if path.suffix.lower() in (".heic", ".heif") and not HEIF:
            raise RuntimeError("HEIC kräver pillow-heif")
        im = Image.open(path)
        meta = im
    when = _exif_time(meta) or _exif_time(im)
    make, model = _exif_camera(meta)
    im = ImageOps.exif_transpose(im)
    if im.mode != "RGB":
        im = im.convert("RGB")
    return im, when, make, model


def to_clip(src, dst, seconds=PHOTO_SECONDS):
    """Gör fotot till ett stillbildsklipp. Returnerar metadata (tid, kamera, originalmått)."""
    src, dst = Path(src), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    jpg = dst.with_suffix(".src.jpg")
    meta = {"photo_path": str(src), "is_photo": True}
    if PIL_OK:
        im, when, make, model = load(src)
        meta.update(photo_width=im.size[0], photo_height=im.size[1], photo_make=make, photo_model=model)
        if when:
            meta["photo_time"] = when
        scale = min(1.0, MAX_SIDE / max(im.size))
        if scale < 1:
            im = im.resize((max(2, int(im.size[0] * scale)), max(2, int(im.size[1] * scale))), Image.LANCZOS)
        im.save(jpg, "JPEG", quality=94)
        inp = jpg
    else:  # utan Pillow: ffmpeg läser JPG/PNG direkt (EXIF-rotation används inte)
        if src.suffix.lower() not in (".jpg", ".jpeg", ".png"):
            raise RuntimeError("Bildstöd saknas för det här formatet")
        inp = src
    tmp = dst.with_suffix(".tmp.mp4")
    vf = (f"scale='min({MAX_SIDE},iw)':'-2':force_original_aspect_ratio=decrease,"
          "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p")
    run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-loop", "1", "-framerate", "30",
         "-i", str(inp), "-t", f"{seconds:.2f}", "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
         "-tune", "stillimage", "-crf", "16", "-g", "30", "-movflags", "+faststart", str(tmp)])
    os.replace(tmp, dst)
    if inp == jpg:
        try:
            jpg.unlink()
        except OSError:
            pass
    return meta
