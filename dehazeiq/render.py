"""Rendering med FFmpeg: varje klipp beskärs, färgjusteras och kodas,
sätts ihop och mixas med musik."""

import shutil
import tempfile
from pathlib import Path

from .config import COLOR_PROFILES, FORMATS, OUTPUT_FPS, RESOLUTIONS, STYLES
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


def _shot_filter(shot, src_w, src_h, out_w, out_h, style, wb=True, fade_in=0.0, fade_out=0.0,
                 fx=None, pad=0.0, vignette=False, title=None):
    """fx: {"speed": 0.5} slowmotion, {"zoom": 0.05} långsam inzoomning. pad: extra sekunder i slutet
    (för mjuka övergångar). title: text som visas i början (font.ttf/title.txt i arbetsmappen)."""
    fx = fx or {}
    cw, ch, x, y = crop_box(src_w, src_h, out_w, out_h, shot.get("cx", 0.5), shot.get("cy", 0.5))
    path = shot.get("path") or []
    if path and cw < src_w - 1:
        crop = f"crop={cw}:{ch}:x='{_path_expr(path, src_w, cw, 1)}':y={y}"
    elif path and ch < src_h - 1:
        crop = f"crop={cw}:{ch}:x={x}:y='{_path_expr(path, src_h, ch, 2)}'"
    else:
        crop = f"crop={cw}:{ch}:{x}:{y}"
    dur = shot["duration"]
    parts = [crop]  # banan följer källans tid, därför före ev. slowmotion
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
    if fx.get("punch"):
        terms.append(f"{float(fx['punch']):.3f}*pow(max(0,1-t/0.35),2)")
    if freeze > 0:
        t0 = dur - freeze
        terms.append(f"0.14*min(1,max(0,(t-{t0:.3f})/0.25))")
    if terms:
        z = "(1+" + "+".join(terms) + ")"
        parts += [f"scale=w='2*trunc({out_w}*{z}/2)':h='2*trunc({out_h}*{z}/2)':eval=frame:flags=bicubic",
                  f"crop={out_w}:{out_h}"]
    else:
        parts.append(f"scale={out_w}:{out_h}:flags=lanczos")
    parts += [f"fps={OUTPUT_FPS}", "setsar=1"]
    if wb:
        r, g, b = shot.get("wb_gains", [1, 1, 1])
        if max(abs(r - 1), abs(g - 1), abs(b - 1)) > 0.02:
            parts.append(f"colorchannelmixer=rr={r:.3f}:gg={g:.3f}:bb={b:.3f}")
    color = COLOR_PROFILES.get(style.get("color", ""))
    if color:
        parts.append(color)
    if vignette:
        parts.append("vignette=angle=PI/5")
    if title:
        parts.append(_title_filter(title, out_w, out_h, dur + pad))
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


def _join_xfade(seg_paths, durs, T, out, out_w, out_h, quality):
    """Mjuka övergångar: xfade/acrossfade. Varje segment utom det sista är T sekunder längre,
    så att klippen fortfarande byts exakt på takten."""
    n = len(seg_paths)
    cmd = [ffmpeg(), "-hide_banner", "-loglevel", "error", "-y"]
    for p in seg_paths:
        cmd += ["-i", str(p)]
    fc = [f"[{i}:v]fps={OUTPUT_FPS},settb=AVTB,setpts=PTS-STARTPTS[v{i}];[{i}:a]asetpts=PTS-STARTPTS[a{i}]"
          for i in range(n)]
    vprev, aprev, acc = "v0", "a0", 0.0
    for i in range(1, n):
        acc += durs[i - 1]
        vo, ao = f"vx{i}", f"ax{i}"
        fc.append(f"[{vprev}][v{i}]xfade=transition=fade:duration={T:.3f}:offset={acc:.3f}[{vo}]")
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
           wb=True, use_proxies=None, effects=None):
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
    T = 0.0
    if on["transitions"] and plan.get("transition") == "fade" and len(shots) > 1:
        T = round(min(plan.get("transition_d", 0.45), min(durs) * 0.4), 3)
        if T < 0.12:
            T = 0.0
    title = None
    if on["title"] and plan.get("title"):
        font = fx_mod.title_font()
        if font:
            shutil.copyfile(font, tmp / "font.ttf")
            (tmp / "title.txt").write_text(plan["title"], "utf-8")
            title = plan["title"]
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
            if not Path(src).exists():
                raise RuntimeError(f"Filen saknas: {src}")
            dur = shot["duration"]
            pad = T if i < len(shots) - 1 else 0.0
            fx = {k: v for k, v in (shot.get("fx") or {}).items()
                  if (k == "speed" and v < 1 and on["slowmo"]) or (k == "speed" and v > 1 and on["fast"])
                  or (k == "zoom" and on["zoom"]) or (k == "punch" and on["punch"])
                  or (k == "freeze" and on["freeze"])}
            seg = tmp / f"seg_{i:03d}.mp4"
            has_audio = clip.get("has_audio", False)
            out_len = dur + pad

            def encode(fx, vignette, title):
                vf = _shot_filter(shot, sw, sh, out_w, out_h, style, wb=wb,
                                  fade_in=style["fade"] if i == 0 else 0.0,
                                  fade_out=style["fade"] if i == len(shots) - 1 else 0.0,
                                  fx=fx, pad=pad, vignette=vignette, title=title)
                read = (out_len - pad - float(fx.get("freeze") or 0.0)) * fx.get("speed", 1.0) + 0.05
                cmd = [ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
                       "-ss", f"{shot['src_start']:.3f}", "-t", f"{read:.3f}", "-i", str(src)]
                if not has_audio:
                    cmd += ["-f", "lavfi", "-t", f"{out_len:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
                cmd += ["-map", "0:v:0", "-map", "0:a:0" if has_audio else "1:a:0",
                        "-vf", vf, "-af", _audio_filter(fx if has_audio else {}, out_len),
                        *video_encoder_args(out_w, out_h, quality),
                        "-r", str(OUTPUT_FPS), "-c:a", "aac", "-b:a", "160k",
                        "-t", f"{out_len:.3f}", str(seg)]
                run(cmd, cwd=str(tmp))

            try:
                encode(fx, vignette, title if i == 0 else None)
            except MediaError:
                if not (fx or vignette or (title and i == 0)):
                    raise
                encode({}, False, None)  # effekten stöds inte av FFmpeg-versionen: rendera utan
            seg_paths.append(seg)
            if progress:
                progress((i + 1) / steps, f"Klipp {i + 1} av {len(shots)}")

        joined = tmp / "joined.mp4"
        if T > 0:
            if progress:
                progress(len(shots) / steps, "Övergångar")
            try:
                _join_xfade(seg_paths, durs, T, joined, out_w, out_h, quality)
            except MediaError:
                _join_copy(seg_paths, durs, tmp, joined, padded=True)
        else:
            _join_copy(seg_paths, durs, tmp, joined, padded=False)

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
