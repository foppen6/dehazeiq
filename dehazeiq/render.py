"""Rendering med FFmpeg: varje klipp beskärs, färgjusteras och kodas,
sätts ihop och mixas med musik."""

import re
import shutil
import tempfile
from pathlib import Path

import numpy as np

from .config import COLOR_PROFILES, FORMATS, GRADE_KEYS, LOOKS, OUTPUT_FPS, RESOLUTIONS, STYLES
from . import divelog, i18n, pano
from . import effects as fx_mod
from .media import MediaError, ffmpeg, run, video_encoder_args


def _concat_escape(p: Path) -> str:
    """FFmpeg concat-listor: apostrof måste skrivas som '\\''."""
    return p.as_posix().replace("'", "'\\''")


def target_size(fmt: str, resolution: str):
    w, h = FORMATS.get(fmt, FORMATS["16:9"])
    f = RESOLUTIONS.get(resolution, 1.0)
    w, h = int(round(w * f / 2) * 2), int(round(h * f / 2) * 2)
    return w, h


def _even(v):
    return max(2, int(v) // 2 * 2)


def crop_box(src_w, src_h, out_w, out_h, cx=0.5, cy=0.5):
    """Beskär källan till målets bildförhållande, centrerat kring (cx, cy)."""
    target = out_w / out_h
    if src_w / src_h > target:
        ch = _even(src_h)
        cw = _even(src_h * target)
        x = int(min(max(cx * src_w - cw / 2, 0), src_w - cw))
        y = 0
    else:
        cw = _even(src_w)
        ch = _even(src_w / target)
        x = 0
        y = int(min(max(cy * src_h - ch / 2, 0), src_h - ch))
    return cw, ch, x, y


FIT_BG = {"blur": "Suddig bakgrund", "black": "Svart", "white": "Vit", "sand": "Sand", "ocean": "Havsblå"}
_BG_COLORS = {"black": "0x000000", "white": "0xF4F4F2", "sand": "0xE8DCC4", "ocean": "0x0B3A53"}


def fit_box(src_w, src_h, out_w, out_h, zoom):
    """Hur stor del av källan som syns vid en viss zoom (1 = fyller bilden, som vanlig beskärning;
    0 = hela bilden syns, med bakgrund runt; över 1 = tajtare). Returnerar (rw, rh) i källans pixlar
    – kan vara större än källan, då blir det kant/bakgrund."""
    cw, ch, _, _ = crop_box(src_w, src_h, out_w, out_h)
    target = out_w / out_h
    z = max(0.0, min(2.0, float(zoom)))
    if z >= 1.0:
        rw = cw / z
    elif cw < src_w - 1:  # beskärs i sidled: zooma ut mot hela bredden
        rw = src_w * (cw / src_w) ** z
    else:
        rw = (src_h * (ch / src_h) ** z) * target
    return rw, rw / target


def place_filters(shot, src_w, src_h, out_w, out_h, cx=None, cy=None, uid="p"):
    """Utsnitt ur källan till målformatet. Beskär (vanligt) eller – med shot["fit"] – zoomar ut och
    lägger bilden på en suddig eller färgad bakgrund. Följer motivets bana om den finns.
    cx/cy: fast punkt (stillbild) i stället för banan. Ger bilden i out_w×out_h (eller beskärningen,
    som skalas senare)."""
    fit = shot.get("fit") or {}
    zoom = float(fit.get("zoom", 1.0))
    path = [] if cx is not None else (shot.get("path") or [])
    cx = shot.get("cx", 0.5) if cx is None else cx
    cy = shot.get("cy", 0.5) if cy is None else cy
    if abs(zoom - 1.0) < 0.01:
        cw, ch, x, y = crop_box(src_w, src_h, out_w, out_h, cx, cy)
        if path and cw < src_w - 1:
            return [f"crop={cw}:{ch}:x='{_path_expr(path, src_w, cw, 1)}':y={y}"]
        if path and ch < src_h - 1:
            return [f"crop={cw}:{ch}:x={x}:y='{_path_expr(path, src_h, ch, 2)}'"]
        return [f"crop={cw}:{ch}:{x}:{y}"]
    rw, rh = fit_box(src_w, src_h, out_w, out_h, zoom)
    vw, vh = _even(min(rw, src_w)), _even(min(rh, src_h))

    def pos(size, crop, c, idx):
        if path and crop < size - 1:
            return f"'{_path_expr(path, size, crop, idx)}'"
        return str(int(min(max(c * size - crop / 2, 0), size - crop)))
    crop = f"crop={vw}:{vh}:x={pos(src_w, vw, cx, 1)}:y={pos(src_h, vh, cy, 2)}"
    if rw <= src_w + 1 and rh <= src_h + 1:
        return [crop]  # tajtare än vanligt eller ryms ändå: bara beskärning
    fw, fh = _even(out_w * vw / rw), _even(out_h * vh / rh)
    bg = fit.get("bg", "blur")
    if bg == "blur":
        cw, ch, x, y = crop_box(src_w, src_h, out_w, out_h, cx, cy)
        sw_, sh_ = max(16, _even(out_w / 10)), max(16, _even(out_h / 10))
        back = (f"crop={cw}:{ch}:{x}:{y},scale={sw_}:{sh_},gblur=sigma=3,scale={out_w}:{out_h}:flags=bicubic,"
                f"eq=brightness=-0.06:saturation=0.85")
    else:
        col = _BG_COLORS.get(bg) or (bg if re.fullmatch(r"0x[0-9A-Fa-f]{6}", str(bg)) else "0x000000")
        back = f"scale={out_w}:{out_h},drawbox=x=0:y=0:w=iw:h=ih:color={col}:t=fill"
    return [f"split[{uid}a][{uid}b];[{uid}b]{back}[{uid}g];[{uid}a]{crop},scale={fw}:{fh}:flags=bicubic,setsar=1[{uid}f];"
            f"[{uid}g][{uid}f]overlay=x=(W-w)/2:y=(H-h)/2"]


def _path_expr(keys, size, crop, idx):
    """Styckvis linjär bana (sekunder → pixel) som FFmpeg-uttryck för crop x/y.
    keys: [[t, cx, cy], …] med motivets mittpunkt normaliserad 0..1."""
    lim = max(0, size - crop)

    def px(v):
        return int(round(min(max(v * size - crop / 2, 0), lim)))

    pts = [(float(k[0]), px(k[idx])) for k in keys]
    if not pts:
        return str(lim // 2)
    if all(p[1] == pts[0][1] for p in pts):
        return str(pts[0][1])
    expr = str(pts[-1][1])
    for (t0, v0), (t1, v1) in reversed(list(zip(pts[:-1], pts[1:]))):
        span = max(t1 - t0, 1e-3)
        expr = f"if(lt(t,{t1:.3f}),{v0}+({v1 - v0})*(t-{t0:.3f})/{span:.3f},{expr})"
    return f"if(lt(t,{pts[0][0]:.3f}),{pts[0][1]},{expr})"


def _title_size(text, out_w, out_h):
    base = min(out_w, out_h) * 0.1
    fit = out_w * 0.86 / max(1, 0.56 * len(text))
    return max(14, int(min(base, fit)))


def _title_filter(text, out_w, out_h, visible):
    """drawtext med typsnitt och text som filer i arbetsmappen (inga sökvägar att escapa)."""
    a0, a1 = 0.35, 0.95
    b1 = max(a1 + 0.6, min(3.6, visible - 0.1))
    b0 = b1 - 0.6
    alpha = (f"if(lt(t,{a0}),0,if(lt(t,{a1}),(t-{a0})/{a1 - a0:.2f},"
             f"if(lt(t,{b0:.2f}),1,if(lt(t,{b1:.2f}),({b1:.2f}-t)/0.6,0))))")
    fs = _title_size(text, out_w, out_h)
    return (f"drawtext=fontfile=font.ttf:textfile=title.txt:fontcolor=white:fontsize={fs}"
            f":x=(w-text_w)/2:y=h*0.70:shadowcolor=black@0.55:shadowx=2:shadowy=2"
            f":alpha='{alpha}'")


def _alpha(t0, t1, f=0.35):
    t1 = max(t0 + 2 * f + 0.05, t1)
    return (f"if(lt(t,{t0:.2f}),0,if(lt(t,{t0 + f:.2f}),(t-{t0:.2f})/{f},"
            f"if(lt(t,{t1 - f:.2f}),1,if(lt(t,{t1:.2f}),({t1:.2f}-t)/{f},0))))")


def _fit(text, out_w, base):
    return max(12, int(min(base, out_w * 0.86 / max(1, 0.56 * len(text)))))


def _longest(text):
    return max((str(text) or " ").split("\n"), key=len)


ENDCARD_SECONDS = 3.2


def _append_endcard(joined, out, tmp, promo, variant, out_w, out_h, quality, total):
    """Reklamens slutbild: sista bilden fryses, mörkas och blir suddig; logga, uppmaning och adress
    tonas in. Returnerar filmens nya längd."""
    D, X = ENDCARD_SECONDS, 0.5
    last = tmp / "last.png"
    run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-sseof", "-0.15", "-i", str(joined),
         "-frames:v", "1", "-update", "1", str(last)])
    m = min(out_w, out_h)
    inputs = ["-loop", "1", "-framerate", str(OUTPUT_FPS), "-t", f"{D:.2f}", "-i", str(last)]
    logo = promo.get("logo")
    has_logo = bool(logo and Path(logo).exists())
    if has_logo:
        shutil.copyfile(logo, tmp / ("logo" + Path(logo).suffix.lower()))
        inputs += ["-loop", "1", "-framerate", str(OUTPUT_FPS), "-t", f"{D:.2f}", "-i", "logo" + Path(logo).suffix.lower()]
    inputs += ["-f", "lavfi", "-t", f"{D:.2f}", "-i", "anullsrc=r=48000:cl=stereo"]
    dark = {"premium": -0.32, "energy": -0.18, "trailer": -0.42}.get(variant, -0.24)
    fc = [f"[0:v]scale={out_w}:{out_h},setsar=1,gblur=sigma={max(6, m // 40)},eq=brightness={dark}:saturation=0.75[bg]"]
    cur = "bg"
    if has_logo:
        lw, lh = int(out_w * (0.42 if out_h > out_w else 0.24)), int(out_h * 0.2)
        fc.append(f"[1:v]scale=w={lw}:h={lh}:force_original_aspect_ratio=decrease,format=rgba,"
                  f"fade=t=in:st=0.15:d=0.45:alpha=1[lg]")
        ly = "H*0.18" if (promo.get("cta") or promo.get("url")) else "(H-h)/2"
        fc.append(f"[{cur}][lg]overlay=x=(W-w)/2:y={ly}:format=auto[v1]")
        cur = "v1"
    draws = []
    cta, url = promo.get("cta") or "", promo.get("url") or ""
    y_cta = "h*0.50" if has_logo else "h*0.42"
    if cta:
        (tmp / "cta.txt").write_text(cta, "utf-8")
        fs = _fit(_longest(cta), out_w, m * 0.085)
        box = (f":box=1:boxcolor=0xE8452C@0.95:boxborderw={max(10, fs // 3)}" if variant == "energy" else
               f":box=1:boxcolor=white@0.95:boxborderw={max(10, fs // 3)}:fontcolor=0x111111" if variant == "info" else "")
        col = "" if variant == "info" else ":fontcolor=white"
        draws.append(f"drawtext=fontfile=font.ttf:textfile=cta.txt:fontsize={fs}{col}:x=(w-text_w)/2:y={y_cta}"
                     f":line_spacing={fs // 4}{box}:shadowcolor=black@0.5:shadowx=2:shadowy=2:alpha='{_alpha(0.45, D + 1, 0.35)}'")
    if url:
        (tmp / "url.txt").write_text(url, "utf-8")
        fs2 = _fit(url, out_w, m * 0.05)
        draws.append(f"drawtext=fontfile=font.ttf:textfile=url.txt:fontsize={fs2}:fontcolor=0xE6EEF3:x=(w-text_w)/2"
                     f":y={'h*0.66' if cta else y_cta}:shadowcolor=black@0.5:shadowx=1:shadowy=1"
                     f":alpha='{_alpha(0.8, D + 1, 0.35)}'")
    fc.append(f"[{cur}]" + ",".join(draws + ["format=yuv420p"]) + "[v]")
    card = tmp / "endcard.mp4"
    a_in = 2 if has_logo else 1
    run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *inputs, "-filter_complex", ";".join(fc),
         "-map", "[v]", "-map", f"{a_in}:a", *video_encoder_args(out_w, out_h, quality), "-r", str(OUTPUT_FPS),
         "-c:a", "aac", "-b:a", "160k", "-t", f"{D:.2f}", str(card)], cwd=str(tmp))
    off = max(0.0, total - X)
    fc2 = (f"[0:v][1:v]xfade=transition=fade:duration={X}:offset={off:.3f},format=yuv420p[v];"
           f"[0:a][1:a]acrossfade=d={X}[a]")
    run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(joined), "-i", str(card),
         "-filter_complex", fc2, "-map", "[v]", "-map", "[a]", *video_encoder_args(out_w, out_h, quality),
         "-r", str(OUTPUT_FPS), "-c:a", "aac", "-b:a", "160k", str(out)], cwd=str(tmp))
    return total - X + D


def _lyric_cues(lines, proposal):
    """Sångtexten i takt: varje rad visas i ett antal taktslag (standard 8 = två takter)."""
    ly = proposal.get("lyrics") or {}
    bpm = float(proposal.get("bpm") or 0) or 100.0
    beat = 60.0 / bpm
    per = max(1, int(ly.get("beats_per_line") or 8)) * beat
    t = float(ly.get("start") or 0.0)
    total = sum(s["duration"] for s in proposal.get("shots", []))
    cues = []
    for line in lines:
        line = str(line).strip()
        if line and t < total:
            cues.append((t, min(total, t + per - 0.05), line))
        t += per
    return cues


def text_filters(kind, text, sub, files, out_w, out_h, dur, freeze=0.0, start=0.5, big=False,
                 variant=None, end=None):
    """drawtext för textskyltar. files: (fil för rad 1, fil för rad 2) i arbetsmappen."""
    m = min(out_w, out_h)
    fa, fb = files
    out = []
    if kind == "hook":  # reklamens krok: stor text de första sekunderna
        fs = _fit(_longest(text), out_w, m * (0.11 if variant == "energy" else 0.085))
        a = _alpha(0.1, min(dur - 0.05, 2.6), 0.18)
        ls = int(fs * 0.25)
        if variant == "energy":
            look = f":fontcolor=white:box=1:boxcolor=0xE8452C@0.92:boxborderw={max(10, fs // 3)}"
            y = "h*0.30-text_h/2"
        elif variant == "premium":
            look = ":fontcolor=white:shadowcolor=black@0.6:shadowx=2:shadowy=2"
            y = "h*0.62"
        elif variant == "info":
            look = f":fontcolor=white:box=1:boxcolor=0x14232E@0.85:boxborderw={max(10, fs // 3)}"
            y = "h*0.12"
        elif variant == "trailer":
            look = ":fontcolor=white:shadowcolor=black@0.7:shadowx=2:shadowy=2"
            y = "(h-text_h)/2"
        else:
            look = ":fontcolor=white:shadowcolor=black@0.55:shadowx=2:shadowy=2"
            y = "(h-text_h)/2"
        out.append(f"drawtext=fontfile=font.ttf:textfile={fa}:fontsize={fs}:line_spacing={ls}:x=(w-text_w)/2:y={y}"
                   f"{look}:alpha='{a}'")
        return out
    if kind == "point":  # säljpunkt som textskylt
        fs = _fit(_longest(text), out_w, m * (0.07 if variant in ("energy", "info") else 0.058))
        a = _alpha(start, end if end is not None else min(dur - 0.1, start + 3.2), 0.2)
        if variant == "trailer":  # stor textskylt mitt i bild, bilden mörkas under texten
            fs = _fit(_longest(text), out_w, m * 0.09)
            out.append(f"drawtext=fontfile=font.ttf:textfile={fa}:fontsize={fs}:fontcolor=white:x=(w-text_w)/2"
                       f":y=(h-text_h)/2:box=1:boxcolor=black@0.55:boxborderw={max(14, fs // 2)}"
                       f":line_spacing={fs // 4}:alpha='{a}'")
        elif variant == "premium":
            out.append(f"drawtext=fontfile=font.ttf:textfile={fa}:fontsize={fs}:fontcolor=white:x=(w-text_w)/2"
                       f":y=h*0.80:shadowcolor=black@0.6:shadowx=2:shadowy=2:alpha='{a}'")
        elif variant == "experience":
            out.append(f"drawtext=fontfile=font.ttf:textfile={fa}:fontsize={fs}:fontcolor=white:x=(w-text_w)/2"
                       f":y=h*0.76:box=1:boxcolor=black@0.35:boxborderw={max(8, fs // 3)}:alpha='{a}'")
        else:
            col = "0xE8452C" if variant == "energy" else "0x14232E"
            out.append(f"drawtext=fontfile=font.ttf:textfile={fa}:fontsize={fs}:fontcolor=white:x={int(out_w * 0.06)}"
                       f":y=h*0.72:box=1:boxcolor={col}@0.9:boxborderw={max(8, fs // 3)}:alpha='{a}'")
        return out
    if kind == "free":  # fria texter i vald stil
        end = end if end is not None else dur
        a = _alpha(start, end, 0.18)
        st = variant or "caption"
        two = bool(sub)
        if st == "doc":  # namnskylt nere till vänster med tunn linje
            fs = _fit(_longest(text), out_w * 0.8, m * 0.06)
            x, y = int(out_w * 0.07), int(out_h * (0.76 if out_h > out_w else 0.72))
            out.append(f"drawbox=x={x - int(m * 0.018)}:y={y}:w={max(3, m // 160)}:h={int(fs * (2.3 if two else 1.2))}"
                       f":color=white@0.9:t=fill:enable='between(t,{max(0, start):.2f},{end:.2f})'")
            out.append(f"drawtext=fontfile=font.ttf:textfile={fa}:fontsize={fs}:fontcolor=white:x={x}:y={y}"
                       f":shadowcolor=black@0.6:shadowx=2:shadowy=2:alpha='{a}'")
            if two:
                out.append(f"drawtext=fontfile=font.ttf:textfile={fb}:fontsize={int(fs * 0.62)}:fontcolor=0xD6E4EA"
                           f":x={x}:y={y + int(fs * 1.35)}:shadowcolor=black@0.6:shadowx=1:shadowy=1:alpha='{a}'")
            return out
        if st == "fun":  # pratbubbla: svart text på gul ruta
            fs = _fit(_longest(text), out_w * 0.85, m * 0.07)
            out.append(f"drawtext=fontfile=font.ttf:textfile={fa}:fontsize={fs}:fontcolor=0x111111:x=(w-text_w)/2"
                       f":y=h*0.16:box=1:boxcolor=0xFFD84A@0.96:boxborderw={max(12, fs // 2)}:line_spacing={fs // 4}"
                       f":alpha='{a}'")
            return out
        if st == "title":
            fs = _fit(_longest(text), out_w * 0.86, m * 0.11)
            out.append(f"drawtext=fontfile=font.ttf:textfile={fa}:fontsize={fs}:fontcolor=white:x=(w-text_w)/2"
                       f":y=(h-text_h)/2-{int(fs * 0.4) if two else 0}:shadowcolor=black@0.6:shadowx=3:shadowy=3"
                       f":line_spacing={fs // 4}:alpha='{a}'")
            if two:
                out.append(f"drawtext=fontfile=font.ttf:textfile={fb}:fontsize={int(fs * 0.45)}:fontcolor=0xE6EEF3"
                           f":x=(w-text_w)/2:y=(h+text_h)/2+{int(fs * 0.5)}:shadowcolor=black@0.6:shadowx=2:shadowy=2"
                           f":alpha='{a}'")
            return out
        if st == "place":  # reseskylt uppe till vänster, versaler
            fs = _fit(_longest(text).upper(), out_w * 0.8, m * 0.075)
            x, y = int(out_w * 0.07), int(out_h * 0.09)
            out.append(f"drawtext=fontfile=font.ttf:textfile={fa}:fontsize={fs}:fontcolor=white:x={x}:y={y}"
                       f":shadowcolor=black@0.6:shadowx=2:shadowy=2:alpha='{a}'")
            if two:
                out.append(f"drawtext=fontfile=font.ttf:textfile={fb}:fontsize={int(fs * 0.5)}:fontcolor=0x9FE7F0"
                           f":x={x}:y={y + int(fs * 1.25)}:shadowcolor=black@0.6:shadowx=1:shadowy=1:alpha='{a}'")
            return out
        if st == "meme":  # versaler med svart kant upptill
            fs = _fit(_longest(text).upper(), out_w * 0.9, m * 0.09)
            out.append(f"drawtext=fontfile=font.ttf:textfile={fa}:fontsize={fs}:fontcolor=white:borderw={max(3, fs // 12)}"
                       f":bordercolor=black:x=(w-text_w)/2:y=h*0.08:line_spacing={fs // 5}:alpha='{a}'")
            return out
        if st == "minimal":
            fs = _fit(_longest(text), out_w * 0.7, m * 0.042)
            out.append(f"drawtext=fontfile=font.ttf:textfile={fa}:fontsize={fs}:fontcolor=white@0.92:x={int(out_w * 0.07)}"
                       f":y=h-text_h-{int(out_h * 0.08)}:alpha='{a}'")
            return out
        if st == "chapter":
            return text_filters("chapter", text, sub, files, out_w, out_h, dur, start=max(0.0, start))
        # undertext: centrerad nere med halvgenomskinlig ruta
        fs = _fit(_longest(text), out_w * 0.86, m * 0.052)
        out.append(f"drawtext=fontfile=font.ttf:textfile={fa}:fontsize={fs}:fontcolor=white:x=(w-text_w)/2"
                   f":y=h*0.80:box=1:boxcolor=black@0.45:boxborderw={max(8, fs // 3)}:line_spacing={fs // 4}"
                   f":alpha='{a}'")
        return out
    if kind == "credit":  # musiktack längst ner på slutet
        fs = _fit(text, out_w, m * 0.032)
        a = _alpha(start, dur + 5, 0.4)
        out.append(f"drawtext=fontfile=font.ttf:textfile={fa}:fontsize={fs}:fontcolor=0xE6EEF3:x=(w-text_w)/2"
                   f":y=h-text_h-{int(out_h * 0.045)}:shadowcolor=black@0.7:shadowx=1:shadowy=1:alpha='{a}'")
        return out
    if kind == "speech":  # undertext från tal: längst ner, gul-vit med mörk ruta, läsbar på allt
        fs = _fit(_longest(text), out_w * 0.9, m * 0.048)
        a = _alpha(start, end if end is not None else dur, 0.08)
        out.append(f"drawtext=fontfile=font.ttf:textfile={fa}:fontsize={fs}:fontcolor=0xFFF6D5:x=(w-text_w)/2"
                   f":y=h-text_h-{int(out_h * 0.07)}:box=1:boxcolor=black@0.55:boxborderw={max(8, fs // 3)}"
                   f":line_spacing={fs // 4}:alpha='{a}'")
        return out
    if kind == "lyric":  # sångtext, en rad i taget
        fs = _fit(_longest(text), out_w, m * 0.072)
        a = _alpha(start, end if end is not None else dur, 0.12)
        out.append(f"drawtext=fontfile=font.ttf:textfile={fa}:fontsize={fs}:fontcolor=white:x=(w-text_w)/2"
                   f":y=h*0.78:shadowcolor=black@0.7:shadowx=2:shadowy=2:borderw=1:bordercolor=black@0.4:alpha='{a}'")
        return out
    if kind == "label":  # artnamn nere till vänster, som i en naturdokumentär
        fs = _fit(text, out_w, m * 0.058)
        fs2 = max(11, int(fs * 0.62))
        y1 = int(out_h * 0.80)
        a = _alpha(start, min(dur - 0.2, start + 4.3))
        x = int(out_w * 0.06)
        out.append(f"drawtext=fontfile=font.ttf:textfile={fa}:fontcolor=white:fontsize={fs}:x={x}:y={y1}"
                   f":box=1:boxcolor=black@0.38:boxborderw={max(6, fs // 3)}:alpha='{a}'")
        if sub:
            out.append(f"drawtext=fontfile=font.ttf:textfile={fb}:fontcolor=0xD9E4EC:fontsize={fs2}:x={x}"
                       f":y={y1 + int(fs * 1.55)}:box=1:boxcolor=black@0.38:boxborderw={max(5, fs2 // 3)}:alpha='{a}'")
    elif kind == "chapter":
        fs = _fit(text, out_w, m * 0.075)
        a = _alpha(0.15, min(dur - 0.15, 2.8))
        out.append(f"drawtext=fontfile=font.ttf:textfile={fa}:fontcolor=white:fontsize={fs}:x=(w-text_w)/2"
                   f":y=(h-text_h)/2:box=1:boxcolor=black@0.45:boxborderw={max(8, fs // 2)}:alpha='{a}'")
    elif kind == "pop":  # pratbubbla på frysbilden
        fs = _fit(text, out_w, m * 0.09)
        t0 = max(0.0, dur - freeze - 0.05) if freeze else dur * 0.45
        a = _alpha(t0, dur, 0.12)
        out.append(f"drawtext=fontfile=font.ttf:textfile={fa}:fontcolor=0x111111:fontsize={fs}:x=(w-text_w)/2"
                   f":y=h*0.16:box=1:boxcolor=white@0.92:boxborderw={max(10, fs // 2)}:alpha='{a}'")
    elif kind == "dive":  # djup och temperatur från dykdatorn
        fs = int(m * (0.05 if big else 0.034))
        a = _alpha(0.0, dur, 0.2)
        out.append(f"drawtext=fontfile=font.ttf:textfile={fa}:fontcolor=white:fontsize={fs}:x=w-text_w-{int(out_w * 0.05)}"
                   f":y={int(out_h * 0.05)}:box=1:boxcolor=black@{0.45 if big else 0.3}:boxborderw={max(5, fs // 3)}"
                   f":alpha='{a}'")
    elif kind == "subtitle":  # datum under titeln
        fs = _fit(text, out_w, m * 0.04)
        a = _alpha(0.6, min(3.6, dur - 0.1))
        out.append(f"drawtext=fontfile=font.ttf:textfile={fa}:fontcolor=0xDDE6EE:fontsize={fs}:x=(w-text_w)/2"
                   f":y=h*0.70+{int(m * 0.13)}:shadowcolor=black@0.5:shadowx=1:shadowy=1:alpha='{a}'")
    return out


# ---------- bildförbättring: dis, partiklar, skakighet ----------

_HAZE = {}


def haze_levels(src, clip_id):
    """Svart- och vitnivå per färgkanal (percentiler ur några bilder) – grunden för dehaze."""
    if clip_id in _HAZE:
        return _HAZE[clip_id]
    import cv2
    cap = cv2.VideoCapture(str(src))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    lo, hi = [], []
    for k in (0.2, 0.5, 0.8):
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(n * k)))
        ok, fr = cap.read()
        if not ok:
            continue
        small = cv2.resize(fr, (320, int(320 * fr.shape[0] / fr.shape[1])))
        px = small.reshape(-1, 3).astype(np.float32)
        lo.append(np.percentile(px, 1.0, axis=0))
        hi.append(np.percentile(px, 99.6, axis=0))
    cap.release()
    if not lo:
        res = None
    else:
        b, g, r = np.mean(lo, axis=0) / 255.0
        bh, gh, rh = np.mean(hi, axis=0) / 255.0
        haze = float(min(b, g, r))  # hur högt "golvet" ligger = hur disigt
        res = {"lo": (float(r), float(g), float(b)), "hi": (float(rh), float(gh), float(bh)), "haze": haze}
    _HAZE[clip_id] = res
    return res


def enhance_filters(enh, levels):
    """Dehaze (lyfter bort dis-slöjan per kanal + lokal kontrast) och partikelreducering."""
    out = []
    d = float(enh.get("dehaze") or 0.0)
    if d > 0.01 and levels:
        a = 0.85 * d
        (rl, gl, bl), (rh, gh, bh) = levels["lo"], levels["hi"]
        out.append("colorlevels="
                   f"rimin={a * rl:.3f}:gimin={a * gl:.3f}:bimin={a * bl:.3f}:"
                   f"rimax={1 - a * (1 - max(rh, 0.5)):.3f}:gimax={1 - a * (1 - max(gh, 0.5)):.3f}:"
                   f"bimax={1 - a * (1 - max(bh, 0.5)):.3f}")
        out.append(f"unsharp=lx=13:ly=13:la={0.55 * d:.2f}:cx=5:cy=5:ca=0")
        out.append(f"eq=saturation={1 + 0.18 * d:.3f}")
    pt = float(enh.get("particles") or 0.0)
    if pt > 0.01:
        k = 3 + 10 * pt
        out.append(f"hqdn3d=luma_spatial={1 + 1.5 * pt:.2f}:chroma_spatial={1 + 1.5 * pt:.2f}"
                   f":luma_tmp={k:.2f}:chroma_tmp={k:.2f}")
    return out


def style_filters(look_fx, out_w, out_h, beat_flash=False):
    """Stileffekter: filmkorn, svarta kanter (bredbild), glöd, blixt på takt, Super 8-fladder."""
    out = []
    if look_fx.get("weave"):  # lite ojämn bild som i en gammal projektor
        out += [f"crop=iw-8:ih-8:4+3*sin(t*11):4+3*cos(t*13)", f"scale={out_w}:{out_h}"]
    if look_fx.get("glow"):
        out.append("split[g0][g1];[g1]gblur=sigma=18[g2];[g0][g2]blend=all_mode=screen:all_opacity=0.28")
    if look_fx.get("rgbshift"):  # glitch: färgkanalerna glider isär en kort stund i början av klippet
        px = max(2, int(out_w * 0.008))
        out.append(f"rgbashift=rh={px}:bh=-{px}:enable='lt(t,0.22)'")
    if beat_flash:
        out.append("eq=brightness='0.35*max(0,1-t/0.14)':eval=frame")
    if look_fx.get("grain"):
        out.append(f"noise=alls={int(8 + 10 * float(look_fx['grain']))}:allf=t")
    if look_fx.get("letterbox"):
        bar = int(round((out_h - out_w / 2.39) / 2)) if out_w / out_h > 1.2 else int(out_h * 0.1)
        if bar > 0:
            out.append(f"drawbox=x=0:y=0:w=iw:h={bar}:color=black:t=fill,"
                       f"drawbox=x=0:y=ih-{bar}:w=iw:h={bar}:color=black:t=fill")
    return out


def grade_values(g):
    """Färgutseende × styrka + egna reglage → värden (se config.LOOKS)."""
    g = g or {}
    look = LOOKS.get(g.get("look") or "none", {})
    k = float(g.get("strength", 1.0))
    v = {key: float(look.get(key, 0.0)) * k for key in GRADE_KEYS + ("bw", "sepia")}
    for key in GRADE_KEYS:
        v[key] += float(g.get(key, 0.0) or 0.0)
    return v


def grade_active(g):
    if not g:
        return False
    v = grade_values(g)
    return any(abs(x) > 1e-3 for x in v.values())


def grade_filter(g):
    """FFmpeg-filter för färgjusteringen (tom lista om inget är ändrat)."""
    if not grade_active(g):
        return []
    v = grade_values(g)
    out = []
    t, tint = v["temperature"], v["tint"]
    if abs(t) > 1e-3 or abs(tint) > 1e-3:
        out.append(f"colorchannelmixer=rr={1 + 0.14 * t:.3f}:gg={1 - 0.07 * tint:.3f}:bb={1 - 0.14 * t:.3f}")
    bw = max(0.0, min(1.0, v["bw"]))
    sat = max(0.0, 1.0 + v["saturation"]) * (1.0 - bw)
    br = 0.22 * v["exposure"]
    con = max(0.2, 1.0 + 0.6 * v["contrast"])
    if abs(br) > 1e-3 or abs(con - 1) > 1e-3 or abs(sat - 1) > 1e-3:
        out.append(f"eq=brightness={br:.3f}:contrast={con:.3f}:saturation={sat:.3f}")
    a = max(0.0, min(1.0, v["sepia"]))
    if a > 1e-3:
        out.append("colorchannelmixer="
                   f"rr={1 - a + a * .393:.3f}:rg={a * .769:.3f}:rb={a * .189:.3f}:"
                   f"gr={a * .349:.3f}:gg={1 - a + a * .686:.3f}:gb={a * .168:.3f}:"
                   f"br={a * .272:.3f}:bg={a * .534:.3f}:bb={1 - a + a * .131:.3f}")
    if v["sharpen"] > 1e-3:
        out.append(f"unsharp=5:5:{min(2.0, 1.5 * v['sharpen']):.2f}")
    if v["vignette"] > 1e-3:
        out.append(f"vignette=angle={0.25 + 0.6 * min(1.0, v['vignette']):.3f}")
    return out


def kb_photo(fx):
    return bool((fx or {}).get("kenburns"))


def _shot_filter(shot, src_w, src_h, out_w, out_h, style, wb=True, fade_in=0.0, fade_out=0.0,
                 fx=None, pad=0.0, vignette=False, title=None, grade=None, texts=None,
                 enh=None, levels=None, look_fx=None, flash=False, pre=None):
    """fx: {"speed": 0.5} slowmotion, {"zoom": 0.05} långsam inzoomning. pad: extra sekunder i slutet
    (för mjuka övergångar). title: text som visas i början (font.ttf/title.txt i arbetsmappen)."""
    fx = fx or {}
    crop = ",".join(place_filters(shot, src_w, src_h, out_w, out_h))
    dur = shot["duration"]
    parts = list(pre or [])  # t.ex. 360-vy ur källan (då är bilden redan out_w×out_h)
    if (enh or {}).get("stabilize") and not kb_photo(fx) and not pre:
        parts.append("deshake=rx=32:ry=32:edge=mirror")
    parts.append(crop)  # banan följer källans tid, därför före ev. slowmotion
    speed = fx.get("speed")
    if speed:
        parts.append(f"setpts=(PTS-STARTPTS)/{speed:.3f}")
    freeze = float(fx.get("freeze") or 0.0)
    if freeze > 0 or pad > 0:
        # frysbild och/eller förlängning för övergången: sista bilden står kvar
        parts.append(f"tpad=stop_mode=clone:stop_duration={freeze + pad:.3f}")
    # Zoom som funktion av tiden: långsam inzoomning, zoomryck vid klippet, inzoomning på frysbilden
    terms = []
    span = dur + pad
    if fx.get("zoom"):
        terms.append(f"{float(fx['zoom']):.3f}*t/{span:.3f}")
    kb = float(fx.get("kenburns") or 0.0)
    if kb > 0:   # foto: zooma mjukt in mot motivet (beskärningen är redan centrerad på det)
        terms.append(f"{kb:.3f}*(0.5-0.5*cos(PI*min(1,t/{span:.3f})))")
    elif kb < 0:  # eller börja nära och dra sig långsamt ut
        terms.append(f"{-kb:.3f}*(0.5+0.5*cos(PI*min(1,t/{span:.3f})))")
    if fx.get("punch"):
        terms.append(f"{float(fx['punch']):.3f}*pow(max(0,1-t/0.35),2)")
    if freeze > 0:
        t0 = dur - freeze
        terms.append(f"0.14*min(1,max(0,(t-{t0:.3f})/0.25))")
    if terms:
        z = "(1+" + "+".join(terms) + ")"
        parts += [f"scale=w='2*trunc({out_w}*{z}/2)':h='2*trunc({out_h}*{z}/2)':eval=frame:flags=bicubic",
                  f"crop={out_w}:{out_h}", f"scale={out_w}:{out_h}"]  # ny bildbuffert: vissa filter kraschar annars
    else:
        parts.append(f"scale={out_w}:{out_h}:flags=lanczos")
    if fx.get("roll"):  # barrel roll: ett varv runt mitt i klippet (förstorat så att hörnen täcks)
        t0 = max(0.2, dur * 0.5 - 0.45)
        t1 = t0 + 0.9
        parts += [f"scale={int(out_w * 1.42) // 2 * 2}:{int(out_h * 1.42) // 2 * 2}",
                  f"rotate=a='2*PI*if(lt(t,{t0:.2f}),0,if(gt(t,{t1:.2f}),1,(1-cos(PI*(t-{t0:.2f})/0.9))/2))'"
                  f":ow={out_w}:oh={out_h}:fillcolor=black"]
    parts += [f"fps={OUTPUT_FPS}", "setsar=1"]
    if wb:
        r, g, b = shot.get("wb_gains", [1, 1, 1])
        if max(abs(r - 1), abs(g - 1), abs(b - 1)) > 0.02:
            parts.append(f"colorchannelmixer=rr={r:.3f}:gg={g:.3f}:bb={b:.3f}")
    parts += enhance_filters(enh or {}, levels)
    look_set = bool(grade and (grade.get("look") or "none") != "none")
    color = None if look_set else COLOR_PROFILES.get(style.get("color", ""))
    if color:
        parts.append(color)
    parts += grade_filter(grade)
    parts += style_filters(look_fx or {}, out_w, out_h, flash)
    if vignette:
        parts.append("vignette=angle=PI/5")
    if title:
        parts.append(_title_filter(title, out_w, out_h, dur + pad))
    parts += texts or []
    if fade_in > 0:
        parts.append(f"fade=t=in:st=0:d={min(fade_in, dur / 2):.3f}")
    if fade_out > 0:
        d = min(fade_out, dur / 2)
        parts.append(f"fade=t=out:st={dur - d:.3f}:d={d:.3f}")
    parts.append("format=yuv420p")
    return ",".join(parts)


def _audio_filter(fx, total):
    parts = []
    speed = (fx or {}).get("speed")
    if speed:
        s = speed
        while s < 0.5 - 1e-6:  # atempo klarar 0.5–2 per steg
            parts.append("atempo=0.5")
            s /= 0.5
        parts += [f"atempo={s:.3f}", "volume=0.6"]
    parts += ["aresample=48000", "aformat=sample_fmts=fltp:channel_layouts=stereo",
              f"apad=whole_dur={total:.3f}"]
    return ",".join(parts)


SFX = {
    "whoosh": "anoisesrc=d=0.5:c=pink:a=0.6,highpass=f=500,lowpass=f=4000,"
              "afade=t=in:st=0:d=0.22,afade=t=out:st=0.22:d=0.28,volume=0.55",
    "pling": "sine=frequency=1568:duration=0.6,afade=t=out:st=0.03:d=0.55,volume=0.35",
}


def _mix_sfx(src, events, out, total):
    """Lägg in ljudeffekter (genererade, inga ljudfiler behövs) vid givna tider."""
    cmd = [ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(src)]
    fc = []
    for k, e in enumerate(events):
        cmd += ["-f", "lavfi", "-i", SFX[e["kind"]]]
        ms = int(max(0.0, min(e["t"], total - 0.1)) * 1000)
        fc.append(f"[{k + 1}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                  f"adelay={ms}|{ms}[s{k}]")
    mix = "".join(f"[s{k}]" for k in range(len(events)))
    fc.append(f"[0:a]{mix}amix=inputs={len(events) + 1}:duration=first:normalize=0[a]")
    cmd += ["-filter_complex", ";".join(fc), "-map", "0:v", "-map", "[a]", "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k", str(out)]
    run(cmd)


def _join_xfade(seg_paths, durs, pads, out, out_w, out_h, quality, kinds=None):
    """Övergångar med xfade/acrossfade. Klipp i som inte är sist är pads[i] sekunder längre,
    så att bytena fortfarande ligger exakt på takten. kinds: övergång per byte."""
    if not isinstance(pads, (list, tuple)):
        pads = [pads] * (len(seg_paths) - 1)
    kinds = kinds or ["fade"] * len(pads)
    n = len(seg_paths)
    cmd = [ffmpeg(), "-hide_banner", "-loglevel", "error", "-y"]
    for p in seg_paths:
        cmd += ["-i", str(p)]
    fc = [f"[{i}:v]fps={OUTPUT_FPS},settb=AVTB,setpts=PTS-STARTPTS[v{i}];[{i}:a]asetpts=PTS-STARTPTS[a{i}]"
          for i in range(n)]
    vprev, aprev, acc = "v0", "a0", 0.0
    for i in range(1, n):
        acc += durs[i - 1]
        T = pads[i - 1]
        kind = kinds[i - 1] if kinds[i - 1] != "cut" else "fade"
        vo, ao = f"vx{i}", f"ax{i}"
        fc.append(f"[{vprev}][v{i}]xfade=transition={kind}:duration={T:.3f}:offset={acc:.3f}[{vo}]")
        fc.append(f"[{aprev}][a{i}]acrossfade=d={T:.3f}:c1=tri:c2=tri[{ao}]")
        vprev, aprev = vo, ao
    cmd += ["-filter_complex", ";".join(fc), "-map", f"[{vprev}]", "-map", f"[{aprev}]",
            *video_encoder_args(out_w, out_h, quality), "-r", str(OUTPUT_FPS),
            "-c:a", "aac", "-b:a", "192k", "-t", f"{sum(durs):.3f}", str(out)]
    run(cmd)


def _join_copy(seg_paths, durs, tmp, out, padded):
    listfile = tmp / "list.txt"
    lines = []
    for p, d in zip(seg_paths, durs):
        lines.append(f"file '{_concat_escape(p)}'\n")
        if padded:
            lines.append(f"outpoint {d:.3f}\n")
    listfile.write_text("".join(lines), "utf-8")
    run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
         "-i", str(listfile), "-c", "copy", str(out)])


def render(project, proposal, resolution="preview", out_path=None, progress=None,
           wb=True, use_proxies=None, effects=None, lang="sv", free=None):
    """Rendera ett förslag. 'preview' använder proxyfiler och går snabbt.
    effects: vilka effekter som är påslagna (se effects.enabled)."""
    style = STYLES[proposal["style"]]
    on = effects if effects is not None else fx_mod.enabled(project.data.get("settings"))
    plan = proposal.get("effects") or {}
    out_w, out_h = target_size(proposal["format"], resolution)
    if use_proxies is None:
        use_proxies = resolution == "preview"
    quality = "preview" if resolution == "preview" else "final"
    clips = project.data["clips"]
    shots = proposal["shots"]
    if not shots:
        raise RuntimeError("Förslaget saknar klipp")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="dehazeiq_", dir=project.cache))
    total = sum(s["duration"] for s in shots)
    steps = len(shots) + 1
    durs = [float(s["duration"]) for s in shots]
    # Övergång efter varje klipp (AI:ns val eller användarens). Äldre förslag: en sort för alla.
    n = len(shots)
    trs = []
    for i in range(n - 1):
        t = shots[i].get("tr")
        if t is None and "tr" not in shots[i]:
            t = "fade" if plan.get("transition") == "fade" else "cut"
        trs.append(t if on["transitions"] and t in fx_mod.TR_DUR else "cut")
    pads = []
    for i, t in enumerate(trs):
        d = fx_mod.TR_DUR.get(t, 0.0) if t != "fade" else plan.get("transition_d", 0.45)
        d = min(d, durs[i] * 0.4, durs[i + 1] * 0.4)
        pads.append(round(d, 3) if d >= 0.12 else 0.0)
    for i in range(len(trs)):
        if pads[i] == 0.0:
            trs[i] = "cut"
    any_tr = any(t != "cut" for t in trs)
    if any_tr:  # raka klipp i en kedja med övergångar: en bildruta lång toning
        pads = [p if p > 0 else 0.04 for p in pads]
    pads.append(0.0)
    # Texter på valt språk
    bio = None
    try:
        from . import ai as _ai
        bio = _ai.get_bio()
    except Exception:  # noqa: BLE001
        pass
    sp_map = {}
    if bio:
        for row in bio.species:
            sp_map[row[0]] = row
            sp_map[row[1]] = row
    loc = i18n.localize(proposal, lang, sp_map, free)
    if style.get("no_text"):
        on = dict(on, title=False, labels=False)
    title = None
    dive_on = bool(on.get("divedata") and (project.data.get("divelog") or {}).get("dives"))
    promo = loc.get("promo") or {}
    variant = style.get("promo")
    has_promo = bool(variant and (promo.get("hook") or promo.get("points") or promo.get("cta") or promo.get("url")))
    lyric_cues = _lyric_cues(loc.get("lyrics") or [], proposal) if style.get("music_video") == "lyrics" else []
    credit = (proposal.get("music_credit") or "") if on.get("credits", True) and not style.get("no_music") else ""
    from . import texts as texts_mod
    free_cues = [(a, b, it, (loc.get("overlays") or {}).get(it["id"]) or it) for a, b, it in texts_mod.timeline(proposal)]
    from . import whisper as whisper_mod
    talk = not style.get("no_text") and style.get("music_video") != "lyrics"
    speech_cues = whisper_mod.subtitle_cues(proposal, clips) if talk and on.get("speech", True) else []
    voice = whisper_mod.speech_ranges(proposal, clips) if talk and on.get("voice", True) else []
    texts_needed = ((on["title"] and loc["title"]) or (on["labels"] and any(loc["shots"])) or dive_on
                    or has_promo or bool(lyric_cues) or bool(credit) or bool(free_cues) or bool(speech_cues))
    font = fx_mod.title_font() if texts_needed else None
    if font:
        shutil.copyfile(font, tmp / "font.ttf")
    if font and on["title"] and loc["title"]:
        (tmp / "title.txt").write_text(loc["title"], "utf-8")
        title = loc["title"]
        if loc["subtitle"]:
            (tmp / "subtitle.txt").write_text(loc["subtitle"], "utf-8")
    units = (project.data.get("settings") or {}).get("units", "metric")

    if variant == "trailer" and not (promo.get("cta") or promo.get("url") or promo.get("logo")):
        promo = dict(promo, cta=loc["title"] or (proposal.get("title") or ""))  # titeln som slutbild
    endcard = bool(variant and promo.get("endcard", True)
                   and (promo.get("cta") or promo.get("url") or promo.get("logo")))
    if variant or style.get("music_video"):
        dive_on = False  # reklam och musikvideo: inga dykdata i bild
    point_cues = []
    if variant and promo.get("points"):
        # säljpunkterna fördelas jämnt efter kroken, var och en läsbar i minst 2 sekunder
        pts = promo["points"][:6]
        t0 = 2.9 if promo.get("hook") else 0.6
        span = max(2.0 * len(pts), total - t0 - 0.6)
        per = span / len(pts)
        for k, ptxt in enumerate(pts):
            a = t0 + k * per
            point_cues.append((a, a + min(per, 3.4) - 0.15, ptxt))

    def overlays(i, shot, fx, out_len):
        out = []
        for k, (a0, a1, it, tx) in enumerate(free_cues if font else []):
            s0, s1 = a0 - shot["at"], a1 - shot["at"]
            if s1 <= 0 or s0 >= out_len:
                continue
            fa_, fb_ = f"o{i}_{k}a.txt", f"o{i}_{k}b.txt"
            up = it.get("style") in ("place", "meme")
            (tmp / fa_).write_text((tx.get("text") or "").upper() if up else (tx.get("text") or ""), "utf-8")
            (tmp / fb_).write_text(tx.get("sub") or " ", "utf-8")
            out += text_filters("free", tx.get("text") or "", tx.get("sub") or "", (fa_, fb_), out_w, out_h, out_len,
                                start=s0, end=s1, variant=it.get("style"))
        if font and credit and i == len(shots) - 1:
            (tmp / "credit.txt").write_text(credit, "utf-8")
            out += text_filters("credit", credit, "", ("credit.txt", ""), out_w, out_h, out_len,
                                start=max(0.2, shot["duration"] - 3.5))
        if font and variant:
            if i == 0 and promo.get("hook"):
                (tmp / "hook.txt").write_text(promo["hook"], "utf-8")
                out += text_filters("hook", promo["hook"], "", ("hook.txt", ""), out_w, out_h, out_len,
                                    variant=variant)
            for k, (a0, a1, ptxt) in enumerate(point_cues):
                s0, s1 = a0 - shot["at"], a1 - shot["at"]
                if s1 <= 0 or s0 >= out_len:
                    continue
                fp = f"p{i}_{k}.txt"
                (tmp / fp).write_text(ptxt, "utf-8")
                out += text_filters("point", ptxt, "", (fp, ""), out_w, out_h, out_len,
                                    start=s0, variant=variant, end=s1)
        if font and lyric_cues:
            for k, (a0, a1, line) in enumerate(lyric_cues):
                s0, s1 = a0 - shot["at"], a1 - shot["at"]
                if s1 <= 0 or s0 >= out_len:
                    continue
                fl = f"l{i}_{k}.txt"
                (tmp / fl).write_text(line, "utf-8")
                out += text_filters("lyric", line, "", (fl, ""), out_w, out_h, out_len, start=s0, end=s1)
        if font and speech_cues:
            for k, (a0, a1, line) in enumerate(speech_cues):
                s0, s1 = a0 - shot["at"], a1 - shot["at"]
                if s1 <= 0 or s0 >= out_len:
                    continue
                fs_ = f"s{i}_{k}.txt"
                (tmp / fs_).write_text(line, "utf-8")
                out += text_filters("speech", line, "", (fs_, ""), out_w, out_h, out_len, start=s0, end=s1)
        if i == 0 and title and loc["subtitle"]:
            out += text_filters("subtitle", loc["subtitle"], "", ("subtitle.txt", ""), out_w, out_h, out_len)
        tx = loc["shots"][i] if i < len(loc["shots"]) else None
        if font and on["labels"] and tx and tx.get("text"):
            fa, fb = f"t{i}a.txt", f"t{i}b.txt"
            (tmp / fa).write_text(tx["text"], "utf-8")
            (tmp / fb).write_text(tx.get("sub") or "", "utf-8")
            start = 0.5 if not (i == 0 and title) else max(0.5, min(3.8, shot["duration"] - 1.6))
            out += text_filters(tx.get("kind", "label"), tx["text"], tx.get("sub"), (fa, fb), out_w, out_h,
                                shot["duration"], float(fx.get("freeze") or 0.0), start)
        if font and dive_on:
            mid = shot["src_start"] + (shot["src_end"] - shot["src_start"]) / 2
            dd = divelog.at(project, shot["clip_id"], mid)
            if dd and dd[0] >= 0.5:
                fd = f"d{i}.txt"
                (tmp / fd).write_text(i18n.dive_text(dd[0], dd[1], lang, units), "utf-8")
                out += text_filters("dive", "", "", (fd, ""), out_w, out_h, shot["duration"],
                                    big=proposal["style"] in ("playful", "action", "musicvideo", "vlog"))
        return out

    vignette = bool(on["vignette"] and plan.get("vignette"))
    try:
        seg_paths = []
        for i, shot in enumerate(shots):
            clip = clips[shot["clip_id"]]
            if use_proxies:
                src = project.proxy_path(clip["id"])
                sw, sh = clip.get("proxy_width") or clip["width"], clip.get("proxy_height") or clip["height"]
            else:
                src = Path(clip["path"])
                sw, sh = clip["width"], clip["height"]
            pano_pre, pano_two, fshot = None, False, shot
            cam = shot.get("cam360") or {}
            if cam and not cam.get("manual") and not on.get("cam360", True):
                cam = {}  # AI:ns 360-effekter avslagna
            if shot.get("parent360") and pano.custom(cam):
                meta = pano.load_meta(project.dir, shot["parent360"])
                parent = clips.get(shot["parent360"]) or {}
                if meta:
                    if use_proxies or not Path(parent.get("path", "")).exists():
                        src, lay = Path(meta["proxy"]), "equirect"
                    else:
                        src, lay = Path(parent["path"]), meta.get("layout", "equirect")
                    pano_pre, pano_two = pano.shot_filters(meta, cam, lay, out_w, out_h, shot, tmp, i)
                    sw, sh = out_w, out_h
                    fshot = dict(shot, cx=0.5, cy=0.5, path=[])
            if not Path(src).exists():
                raise RuntimeError(f"Filen saknas: {src}")
            dur = shot["duration"]
            # lite extra i slutet så att övergången alltid har bilder att arbeta med (avrundning till bildrutor)
            pad = pads[i] + 0.12 if any_tr and i < len(shots) - 1 else 0.0
            fx = {k: v for k, v in (shot.get("fx") or {}).items()
                  if (k == "speed" and v < 1 and on["slowmo"]) or (k == "speed" and v > 1 and on["fast"])
                  or (k == "zoom" and on["zoom"]) or (k == "punch" and on["punch"])
                  or (k == "freeze" and on["freeze"]) or k == "kenburns" or (k == "roll" and on.get("cam360", True))}
            seg = tmp / f"seg_{i:03d}.mp4"
            has_audio = clip.get("has_audio", False)
            out_len = dur + pad
            # bildförbättring: användarens värden, annars AI:ns automatik för undervattensklipp
            g = shot.get("grade") or proposal.get("grade") or {}
            a = clip.get("analysis") or {}
            enh = {}
            if on.get("enhance"):
                if a.get("underwater") or shot.get("underwater"):
                    lv = haze_levels(src, clip["id"])
                    enh["dehaze"] = round(min(0.8, max(0.25, ((lv or {}).get("haze", 0.1) - 0.03) * 6)), 2)
                    enh["particles"] = 0.35
            if on.get("stabilize") and float(a.get("best_stab", 1.0)) < 0.72:
                enh["stabilize"] = True
            for k in ("dehaze", "particles", "stabilize"):
                if g.get(k) is not None:
                    enh[k] = g[k]
            levels = haze_levels(src, clip["id"]) if float(enh.get("dehaze") or 0) > 0.01 else None
            lfx = dict(style.get("look_fx") or {})
            if not on.get("grain"):
                lfx.pop("grain", None)
                lfx.pop("weave", None)
                lfx.pop("glow", None)
            if not on.get("letterbox"):
                lfx.pop("letterbox", None)
            flash = bool(on.get("flash") and style.get("beat_flash") and i % int(style["beat_flash"]) == 0 and i > 0)

            def encode(fx, vignette, title, texts):
                vf = _shot_filter(fshot, sw, sh, out_w, out_h, style, wb=wb,
                                  fade_in=style["fade"] if i == 0 else 0.0,
                                  fade_out=style["fade"] if i == len(shots) - 1 and not endcard else 0.0,
                                  fx=fx, pad=pad, vignette=vignette, title=title,
                                  grade=shot.get("grade") or proposal.get("grade"), texts=texts,
                                  enh=enh if texts is not None else {}, levels=levels,
                                  look_fx=lfx if texts is not None else {}, flash=flash and texts is not None,
                                  pre=pano_pre)
                read = (out_len - pad - float(fx.get("freeze") or 0.0)) * fx.get("speed", 1.0) + 0.05
                cmd = [ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
                       "-ss", f"{shot['src_start']:.3f}", "-t", f"{read:.3f}", "-i", str(src)]
                if not has_audio:
                    cmd += ["-f", "lavfi", "-t", f"{out_len:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
                vmap = (["-filter_complex", f"[0:v:0][0:v:1]hstack=inputs=2,{vf}[v]", "-map", "[v]"] if pano_two
                        else ["-map", "0:v:0", "-vf", vf])
                cmd += [*vmap, "-map", "0:a:0" if has_audio else "1:a:0",
                        "-af", _audio_filter(fx if has_audio else {}, out_len),
                        *video_encoder_args(out_w, out_h, quality),
                        "-r", str(OUTPUT_FPS), "-c:a", "aac", "-b:a", "160k",
                        "-t", f"{out_len:.3f}", str(seg)]
                run(cmd, cwd=str(tmp))

            try:
                try:
                    encode(fx, vignette, title if i == 0 else None, overlays(i, shot, fx, out_len))
                except MediaError:  # ett försök till (FFmpeg kan krascha sporadiskt med många filter)
                    encode(fx, vignette, title if i == 0 else None, overlays(i, shot, fx, out_len))
            except MediaError:
                if not (fx or vignette or (title and i == 0) or shot.get("text") or enh or lfx or flash or dive_on):
                    raise
                encode({}, False, None, None)  # effekten stöds inte av FFmpeg-versionen: rendera utan
            seg_paths.append(seg)
            if progress:
                progress((i + 1) / steps, f"Klipp {i + 1} av {len(shots)}")

        joined = tmp / "joined.mp4"
        if any_tr:
            if progress:
                progress(len(shots) / steps, "Övergångar")
            try:
                _join_xfade(seg_paths, durs, pads[:-1], joined, out_w, out_h, quality, trs)
            except MediaError:
                try:  # äldre FFmpeg utan alla övergångar: vanliga toningar
                    _join_xfade(seg_paths, durs, pads[:-1], joined, out_w, out_h, quality,
                                ["fade"] * len(trs))
                except MediaError:
                    _join_copy(seg_paths, durs, tmp, joined, padded=True)
        else:
            _join_copy(seg_paths, durs, tmp, joined, padded=False)

        events = fx_mod.plan_sfx(shots, trs, proposal["style"]) if on["sfx"] else []
        if events:
            try:
                with_sfx = tmp / "sfx.mp4"
                _mix_sfx(joined, events, with_sfx, total)
                joined = with_sfx
            except MediaError as e:
                print("Ljudeffekterna kunde inte läggas till:", e)

        if endcard:
            try:
                if not font:
                    shutil.copyfile(fx_mod.title_font(), tmp / "font.ttf")
                with_end = tmp / "endcard_joined.mp4"
                total = _append_endcard(joined, with_end, tmp, promo, variant, out_w, out_h, quality, total)
                joined = with_end
            except (MediaError, OSError, TypeError) as e:
                print("Slutbilden kunde inte läggas till:", e)

        if progress:
            progress(len(shots) / steps, "Mixar ljud")
        music = None if style.get("no_music") else proposal.get("music")
        orig = style["orig_audio"]
        tmp_out = out_path.with_suffix(".tmp.mp4")
        if music and Path(music).exists():
            fo = min(2.5, total / 3)
            ovol, mvol = f"{orig:.3f}", "1"
            if voice:  # någon pratar: talet upp, musiken ner (mjukt in och ut)
                win = "+".join(f"clip((t-{a - 0.25:.2f})/0.25,0,1)*clip(({b + 0.3:.2f}-t)/0.3,0,1)"
                               for a, b in _merge_ranges(voice)[:60])
                ovol = f"'{orig:.3f}+({1.0 - orig:.3f})*min(1,{win})':eval=frame"
                mvol = f"'1-0.75*min(1,{win})':eval=frame"
            moff = float(proposal.get("music_offset") or 0.0)  # förhandsvisning av ett klipp mitt i filmen
            fades = ("" if moff else f"afade=t=in:st=0:d=0.6,afade=t=out:st={max(0.0, total - fo):.3f}:d={fo:.3f},")
            fc = (f"[1:a]atrim={moff:.3f}:{moff + total:.3f},asetpts=PTS-STARTPTS,"
                  f"aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,{fades}"
                  f"volume={mvol}[m];"
                  f"[0:a]volume={ovol}[o];[o][m]amix=inputs=2:duration=first:normalize=0[a]")
            run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
                 "-i", str(joined), "-i", str(music), "-filter_complex", fc,
                 "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                 "-movflags", "+faststart", str(tmp_out)])
        else:
            run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(joined),
                 "-c:v", "copy", "-af", f"volume={max(orig, 0.8):.2f}", "-c:a", "aac",
                 "-b:a", "192k", "-movflags", "+faststart", str(tmp_out)])
        tmp_out.replace(out_path)
        if progress:
            progress(1.0, "Klart")
        return out_path
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def shot_preview(project, proposal, idx, out_dir):
    """Snabb förhandsvisning av ett enda klipp, exakt som i filmen (utsnitt, inpassning, effekter,
    färg, texter, musik på rätt ställe). Sparas efter innehåll, så en oförändrad ändring återanvänds."""
    import hashlib
    import json as _json
    shots = proposal["shots"]
    if not 0 <= idx < len(shots):
        raise RuntimeError("Klippet finns inte")
    shot = dict(shots[idx])
    at = float(shot.get("at", 0.0))
    uid = shot.get("uid")
    mini = {k: v for k, v in proposal.items() if k not in ("shots", "history", "renders", "overlays")}
    mini["shots"] = [dict(shot, at=0.0, tr="cut")]
    mini["overlays"] = [o for o in proposal.get("overlays") or [] if o.get("shot_uid") == uid]
    mini["music_offset"] = at
    if idx != 0:
        mini["effects"] = dict(proposal.get("effects") or {}, title="")
        mini["title"] = ""
    if mini.get("promo"):
        mini["promo"] = dict(mini["promo"], endcard=False)
        if idx != 0:
            mini["promo"]["hook"] = ""
    mini["music_credit"] = ""
    on = fx_mod.enabled(project.data.get("settings"))
    key = hashlib.sha1(_json.dumps([mini, on, project.data["clips"][shot["clip_id"]].get("speech")],
                                   sort_keys=True, default=str).encode()).hexdigest()[:16]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"shot_{key}.mp4"
    if not out.exists():
        old = sorted(out_dir.glob("shot_*.mp4"), key=lambda p: p.stat().st_mtime)
        for p in old[:-40]:  # håll mappen liten
            p.unlink(missing_ok=True)
        render(project, mini, "preview", out, effects=on)
    return out


def _merge_ranges(rs, gap=0.6):
    out = []
    for a, b in sorted(rs):
        if out and a - out[-1][1] < gap:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def still(project, proposal, idx, at=0.5, width=480, graded=True, effects=None):
    """En bild ur ett klipp i förslaget, utsnitt, inpassning, bildförbättring och färg som i filmen
    (för redigeringen). graded=False: originalbilden i samma utsnitt (för före/efter).
    at: andel av klippets längd (0..1). Returnerar JPEG-bytes."""
    import subprocess

    from .media import subprocess_kwargs
    shot = proposal["shots"][idx]
    clip = project.data["clips"][shot["clip_id"]]
    proxy = project.proxy_path(clip["id"])
    src = proxy if proxy.exists() else Path(clip["path"])
    sw, sh = (clip.get("proxy_width") or clip["width"], clip.get("proxy_height") or clip["height"]) if proxy.exists() else (clip["width"], clip["height"])
    out_w, out_h = target_size(proposal["format"], "preview")
    scale = width / out_w
    out_w, out_h = int(out_w * scale) // 2 * 2, int(out_h * scale) // 2 * 2
    speed = float((shot.get("fx") or {}).get("speed", 1.0))
    rel = max(0.0, min(0.999, at)) * shot["duration"] * speed
    t = shot["src_start"] + rel
    # beskärningens position vid den tiden (banan är styckvis linjär)
    cx, cy = shot.get("cx", 0.5), shot.get("cy", 0.5)
    path = shot.get("path") or []
    if path:
        ts = [k[0] for k in path]
        cx = float(np.interp(rel, ts, [k[1] for k in path]))
        cy = float(np.interp(rel, ts, [k[2] for k in path]))
    style = STYLES[proposal["style"]]
    parts = place_filters(shot, sw, sh, out_w, out_h, cx, cy) + [f"scale={out_w}:{out_h}:flags=bicubic", "setsar=1"]
    if graded:
        on = effects if effects is not None else fx_mod.enabled(project.data.get("settings"))
        r, g, b = shot.get("wb_gains", [1, 1, 1])
        if max(abs(r - 1), abs(g - 1), abs(b - 1)) > 0.02:
            parts.append(f"colorchannelmixer=rr={r:.3f}:gg={g:.3f}:bb={b:.3f}")
        grade = shot.get("grade") or proposal.get("grade")
        gg = grade or {}
        enh = {}
        a = clip.get("analysis") or {}
        if on.get("enhance") and (a.get("underwater") or shot.get("underwater")):
            lv = haze_levels(src, clip["id"])
            enh["dehaze"] = round(min(0.8, max(0.25, ((lv or {}).get("haze", 0.1) - 0.03) * 6)), 2)
            enh["particles"] = 0.35
        for k in ("dehaze", "particles"):
            if gg.get(k) is not None:
                enh[k] = gg[k]
        levels = haze_levels(src, clip["id"]) if float(enh.get("dehaze") or 0) > 0.01 else None
        parts += enhance_filters(enh, levels)
        look_set = bool(grade and (grade.get("look") or "none") != "none")
        color = None if look_set else COLOR_PROFILES.get(style.get("color", ""))
        if color:
            parts.append(color)
        parts += grade_filter(grade)
        lfx = dict(style.get("look_fx") or {})
        for k in ("grain", "weave", "flash"):
            lfx.pop(k, None)
        if not on.get("letterbox"):
            lfx.pop("letterbox", None)
        parts += style_filters(lfx, out_w, out_h, False)
    cmd = [ffmpeg(), "-hide_banner", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(src),
           "-frames:v", "1", "-vf", ",".join(parts), "-f", "image2", "-c:v", "mjpeg", "-q:v", "4", "pipe:1"]
    r = subprocess.run(cmd, capture_output=True, timeout=60, **subprocess_kwargs())
    if r.returncode != 0 or not r.stdout:
        if graded:  # något filter fungerar inte på den här bilden: visa åtminstone utsnittet
            return still(project, proposal, idx, at, width, False)
        raise MediaError(r.stderr.decode("utf-8", "replace")[-400:])
    return r.stdout


def write_srt(project, proposal, path, lang="sv", free=None):
    """Undertextfil med filmens texter (titel, artnamn, kapitel, pratbubblor)."""
    loc = i18n.localize(proposal, lang, None, free)
    cues = []
    if loc["title"]:
        cues.append((0.3, min(3.6, proposal["shots"][0]["duration"] if proposal["shots"] else 3.6), loc["title"]))
    for s, tx in zip(proposal["shots"], loc["shots"]):
        if tx and tx.get("text"):
            line = tx["text"] + (f"\n{tx['sub']}" if tx.get("sub") else "")
            cues.append((s["at"] + 0.3, s["at"] + min(s["duration"] - 0.1, 4.5), line))
    from . import whisper as whisper_mod
    cues += whisper_mod.subtitle_cues(proposal, project.data["clips"])  # det som sägs i filmen
    cues.sort(key=lambda c: c[0])
    if not cues:
        return False

    def ts(x):
        ms = int(round(x * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    Path(path).write_text("".join(f"{k + 1}\n{ts(a)} --> {ts(b)}\n{t}\n\n" for k, (a, b, t) in enumerate(cues)),
                          "utf-8")
    return True
