"""Rendering med FFmpeg: varje klipp beskärs, färgjusteras och kodas,
sätts ihop och mixas med musik."""

import shutil
import tempfile
from pathlib import Path

from .config import COLOR_PROFILES, FORMATS, OUTPUT_FPS, RESOLUTIONS, STYLES
from .media import ffmpeg, run, video_encoder_args


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


def _shot_filter(shot, src_w, src_h, out_w, out_h, style, wb=True, fade_in=0.0, fade_out=0.0):
    cw, ch, x, y = crop_box(src_w, src_h, out_w, out_h, shot.get("cx", 0.5), shot.get("cy", 0.5))
    path = shot.get("path") or []
    if path and cw < src_w - 1:
        crop = f"crop={cw}:{ch}:x='{_path_expr(path, src_w, cw, 1)}':y={y}"
    elif path and ch < src_h - 1:
        crop = f"crop={cw}:{ch}:x={x}:y='{_path_expr(path, src_h, ch, 2)}'"
    else:
        crop = f"crop={cw}:{ch}:{x}:{y}"
    parts = [crop,
             f"scale={out_w}:{out_h}:flags=lanczos",
             f"fps={OUTPUT_FPS}", "setsar=1"]
    if wb:
        r, g, b = shot.get("wb_gains", [1, 1, 1])
        if max(abs(r - 1), abs(g - 1), abs(b - 1)) > 0.02:
            parts.append(f"colorchannelmixer=rr={r:.3f}:gg={g:.3f}:bb={b:.3f}")
    color = COLOR_PROFILES.get(style.get("color", ""))
    if color:
        parts.append(color)
    dur = shot["duration"]
    if fade_in > 0:
        parts.append(f"fade=t=in:st=0:d={min(fade_in, dur / 2):.3f}")
    if fade_out > 0:
        d = min(fade_out, dur / 2)
        parts.append(f"fade=t=out:st={dur - d:.3f}:d={d:.3f}")
    parts.append("format=yuv420p")
    return ",".join(parts)


def render(project, proposal, resolution="preview", out_path=None, progress=None,
           wb=True, use_proxies=None):
    """Rendera ett förslag. 'preview' använder proxyfiler och går snabbt."""
    style = STYLES[proposal["style"]]
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
            if not Path(src).exists():
                raise RuntimeError(f"Filen saknas: {src}")
            dur = shot["duration"]
            vf = _shot_filter(shot, sw, sh, out_w, out_h, style, wb=wb,
                              fade_in=style["fade"] if i == 0 else 0.0,
                              fade_out=style["fade"] if i == len(shots) - 1 else 0.0)
            seg = tmp / f"seg_{i:03d}.mp4"
            cmd = [ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
                   "-ss", f"{shot['src_start']:.3f}", "-t", f"{dur:.3f}", "-i", str(src)]
            has_audio = clip.get("has_audio", False)
            if not has_audio:
                cmd += ["-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
            cmd += ["-map", "0:v:0", "-map", "0:a:0" if has_audio else "1:a:0",
                    "-vf", vf,
                    "-af", "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo",
                    *video_encoder_args(out_w, out_h, quality),
                    "-r", str(OUTPUT_FPS), "-c:a", "aac", "-b:a", "160k",
                    "-t", f"{dur:.3f}", "-shortest", str(seg)]
            run(cmd)
            seg_paths.append(seg)
            if progress:
                progress((i + 1) / steps, f"Klipp {i + 1} av {len(shots)}")

        listfile = tmp / "list.txt"
        listfile.write_text("".join(f"file '{_concat_escape(p)}'\n" for p in seg_paths), "utf-8")
        joined = tmp / "joined.mp4"
        run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
             "-i", str(listfile), "-c", "copy", str(joined)])

        if progress:
            progress(len(shots) / steps, "Mixar ljud")
        music = proposal.get("music")
        orig = style["orig_audio"]
        tmp_out = out_path.with_suffix(".tmp.mp4")
        if music and Path(music).exists():
            fo = min(2.5, total / 3)
            fc = (f"[1:a]atrim=0:{total:.3f},asetpts=PTS-STARTPTS,"
                  f"aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                  f"afade=t=in:st=0:d=0.6,afade=t=out:st={max(0.0, total - fo):.3f}:d={fo:.3f}[m];"
                  f"[0:a]volume={orig:.3f}[o];[o][m]amix=inputs=2:duration=first:normalize=0[a]")
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
