"""360-film (Insta360 X4 m.fl.): AI väljer vart kameran tittar.

Flöde vid import:
  1. 360-källan känns igen: .insv (två linser, X3/X4/X5), en ihopsydd 360-MP4 (2:1, t.ex. export
     från Insta360 Studio) eller en fil med sfärisk metadata.
  2. En liten 360-proxy (1920×960, rektangulär projektion) görs för analys och förhandsvisning.
  3. AI:n tittar åt 24 håll per sekund (CLIP), hittar motivet och räknar fram en mjuk kamerabana.
  4. Banan renderas till vanliga klipp ("virtuell kamera"): en AI-vy som följer motivet och en
     delad vy (motivet överst, andra hållet nedtill – ofta dykaren/fotografen) för stående format.
     De klippen går sedan igenom vanlig analys, urval och redigering som allt annat material.

Vid rendering kan ett klipp också tas direkt ur 360-källan med andra vyer:
liten planet, kristallkula, 360-svep och egen riktning/bildvinkel (se cam_filter).
"""

import json
import math
import os
from pathlib import Path

import numpy as np

from .media import ffmpeg, run, video_encoder_args

PROXY_W, PROXY_H = 1920, 960
LENS_FOV = 200.0          # Insta360 X-seriens linser (grader), används när .insv sys ihop av programmet
VIEW_SIZE = 2160          # sida på AI-vyns kvadratiska klipp (räcker för 9:16 och 16:9 i 1080p)
VIEW_FOV = 104.0          # bildvinkel för AI-vyn
SAMPLE_DT = 1.0           # sekunder mellan riktningsanalyser
YAWS = np.arange(0, 360, 30.0)
PITCHES = (0.0, -28.0)


# ---------- känna igen och läsa in ----------

def detect(path, info):
    """Vilken sorts 360-källa är det? 'dual' (två linsströmmar), 'dfisheye' (båda linserna i en bild),
    'equirect' (ihopsydd 2:1) eller None (vanlig platt film)."""
    path = Path(path)
    w, h = info.get("width") or 0, info.get("height") or 0
    if info.get("video_streams", 1) >= 2 and (path.suffix.lower() == ".insv" or info.get("source") == "Insta360"):
        return "dual"
    if path.suffix.lower() == ".insv":
        return "dfisheye" if h and abs(w / h - 2.0) < 0.05 else "equirect"
    if info.get("spherical") or (info.get("source") == "Insta360" and h and abs(w / h - 2.0) < 0.02):
        return "equirect"
    return None


def input_graph(layout, lens_fov=LENS_FOV):
    """Filter som gör om källan till rektangulär 360-bild (equirect). Returnerar (graf, behöver_två_strömmar)."""
    if layout == "dual":
        return (f"[0:v:0][0:v:1]hstack=inputs=2,v360=input=dfisheye:output=e:ih_fov={lens_fov}:iv_fov={lens_fov}"
                ":interp=line:reset_rot=1", True)
    if layout == "dfisheye":
        return f"v360=input=dfisheye:output=e:ih_fov={lens_fov}:iv_fov={lens_fov}:interp=line:reset_rot=1", False
    return "", False


def _ff_input(src, layout, extra_vf, start=None, dur=None):
    """FFmpeg-argument som läser källan och kör extra_vf på equirect-bilden. Returnerar (args, map_args)."""
    graph, two = input_graph(layout)
    pre = []
    if start is not None:
        pre += ["-ss", f"{start:.3f}"]
    if dur is not None:
        pre += ["-t", f"{dur:.3f}"]
    args = pre + ["-i", str(src)]
    chain = ",".join(x for x in (graph if not two else "", extra_vf) if x)
    if two:
        fc = graph + ("," + extra_vf if extra_vf else "") + "[v]"
        return args, ["-filter_complex", fc, "-map", "[v]"]
    return args, (["-vf", chain] if chain else []) + ["-map", "0:v:0"]


def make_proxy(src, dst, layout):
    """Liten equirect-proxy för analys och snabba förhandsvisningar."""
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".tmp.mp4")
    args, maps = _ff_input(src, layout, f"scale={PROXY_W}:{PROXY_H}:flags=bicubic,fps=30,format=yuv420p")
    run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *args, *maps, "-map", "0:a:0?",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-g", "15", "-c:a", "aac", "-b:a", "96k",
         "-movflags", "+faststart", str(tmp)])
    os.replace(tmp, dst)
    return dst


# ---------- AI: vart ska kameran titta? ----------

_MAPS = {}


def _view_maps(yaw, pitch, fov, n, W, H):
    """Avbildning från en platt vy (n×n, bildvinkel fov) till equirect-bilden (W×H).
    Samma riktningar som FFmpeg v360 (yaw åt höger, pitch uppåt)."""
    key = (yaw, pitch, fov, n, W, H)
    if key in _MAPS:
        return _MAPS[key]
    t = math.tan(math.radians(fov) / 2)
    g = np.linspace(-t, t, n, dtype=np.float32)
    x, y = np.meshgrid(g, -g)
    z = np.ones_like(x)
    v = np.stack([x, y, z], -1)
    v /= np.linalg.norm(v, axis=-1, keepdims=True)
    p, q = math.radians(pitch), math.radians(yaw)
    rx = np.array([[1, 0, 0], [0, math.cos(p), math.sin(p)], [0, -math.sin(p), math.cos(p)]], np.float32)
    ry = np.array([[math.cos(q), 0, math.sin(q)], [0, 1, 0], [-math.sin(q), 0, math.cos(q)]], np.float32)
    d = v @ rx.T @ ry.T
    lon = np.arctan2(d[..., 0], d[..., 2])
    lat = np.arcsin(np.clip(d[..., 1], -1, 1))
    mx = ((lon / (2 * math.pi) + 0.5) * W).astype(np.float32) % W
    my = ((0.5 - lat / math.pi) * H).astype(np.float32)
    _MAPS[key] = (mx, my)
    return mx, my


def view(frame, yaw, pitch=0.0, fov=80.0, n=224):
    import cv2
    H, W = frame.shape[:2]
    mx, my = _view_maps(float(yaw), float(pitch), float(fov), n, W, H)
    return cv2.remap(frame, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)


def _wrap(a):
    return (a + 180.0) % 360.0 - 180.0


def find_path(proxy, clip_model, progress=None):
    """Kamerabanan för AI-vyn: [[t, yaw, pitch], …] plus hur säker AI:n är per prov."""
    import cv2
    cap = cv2.VideoCapture(str(proxy))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    dur = n / fps if n else 0.0
    times = np.arange(0.2, max(0.3, dur - 0.1), SAMPLE_DT)
    dirs = [(y, p) for p in PITCHES for y in YAWS]
    scores, ts, refine = [], [], []
    for k, t in enumerate(times):
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, fr = cap.read()
        if not ok:
            break
        views = [view(fr, y, p, 80.0, 224) for y, p in dirs]
        emb = clip_model.embed(views)
        s = clip_model.interest(emb) + 0.15 * np.clip(clip_model.subject_score(emb) * 10, -1, 1)
        # lite förkärlek för horisonten och "framåt" när inget står ut
        s = s + np.array([0.04 if p == 0 else 0.0 for _, p in dirs]) + \
            np.array([0.01 * math.cos(math.radians(y)) for y, _ in dirs])
        # var i den bästa vyn ligger motivet? flytta riktningen dit (grövre rutnät → exakt)
        top = int(np.argmax(s))
        ty, tp = dirs[top]
        try:
            x, y, c, *_ = clip_model.locate(view(fr, ty, tp, 100.0, 448))
        except Exception:  # noqa: BLE001
            x, y, c = 0.5, 0.5, 0.0
        k100 = math.tan(math.radians(50.0))
        dy = math.degrees(math.atan((x - 0.5) * 2 * k100)) if c > 0.004 else 0.0
        dp = -math.degrees(math.atan((y - 0.5) * 2 * k100)) if c > 0.004 else 0.0
        refine.append((top, dy, dp))
        scores.append(s)
        ts.append(float(t))
        if progress and k % 5 == 0:
            progress(k / max(1, len(times)))
    cap.release()
    if not scores:
        return {"path": [[0.0, 0.0, 0.0]], "conf": 0.0}
    S = np.array(scores)  # (T, D)
    # Viterbi: hellre lugna kamerarörelser än att hoppa mellan motiv
    D = len(dirs)
    ang = np.array([[abs(_wrap(a[0] - b[0])) + abs(a[1] - b[1]) for b in dirs] for a in dirs]) / 180.0
    cost = 0.35 * ang
    acc = S[0].copy()
    back = np.zeros(S.shape, int)
    for i in range(1, len(S)):
        m = acc[None, :] - cost  # [till, från]
        back[i] = np.argmax(m, axis=1)
        acc = m[np.arange(D), back[i]] + S[i]
    best = [int(np.argmax(acc))]
    for i in range(len(S) - 1, 0, -1):
        best.append(int(back[i][best[-1]]))
    best = best[::-1]
    fine, finep = [], []
    for i, b in enumerate(best):
        y0, p0 = dirs[b]
        top, dy, dp = refine[i]
        if top == b:
            y0, p0 = y0 + dy, float(np.clip(p0 + dp, -70, 50))
        fine.append(y0)
        finep.append(p0)
    yaw = np.unwrap(np.radians(fine))
    pitch = np.array(finep, float)
    # mjuk bana
    if len(yaw) >= 3:
        kern = np.exp(-0.5 * (np.arange(-3, 4) / 1.3) ** 2)
        kern /= kern.sum()
        pad = 3
        yaw = np.convolve(np.pad(yaw, pad, mode="edge"), kern, mode="same")[pad:-pad]
        pitch = np.convolve(np.pad(pitch, pad, mode="edge"), kern, mode="same")[pad:-pad]
    conf = float(np.mean([S[i, b] for i, b in enumerate(best)]))
    path = [[round(t, 2), round(float(_wrap(math.degrees(y))), 1), round(float(p), 1)]
            for t, y, p in zip(ts, yaw, pitch)]
    return {"path": path, "conf": round(conf, 3)}


# ---------- rendering av vyer ----------

def _interp_path(path, t):
    ts = [p[0] for p in path]
    yaw = np.degrees(np.unwrap(np.radians([p[1] for p in path])))
    return float(_wrap(np.interp(t, ts, yaw))), float(np.interp(t, ts, [p[2] for p in path]))


def write_cmds(dst, path, start, dur, yaw_off=0.0, extra=None, step=0.2):
    """sendcmd-fil som styr v360@cam längs banan (tider relativa till klippets början)."""
    lines = []
    t = 0.0
    while t <= dur + step:
        y, p = _interp_path(path, start + t)
        y = _wrap(y + yaw_off)
        cmd = f"v360@cam yaw {y:.2f}, v360@cam pitch {p:.2f}"
        if extra:
            e = extra(t)
            if e:
                cmd += ", " + e
        lines.append(f"{t:.3f} {cmd};")
        t += step
    Path(dst).write_text("\n".join(lines) + "\n", "utf-8")
    return dst


def cam_filter(mode, out_w, out_h, cmdfile=None, fov=None, yaw=0.0, pitch=0.0, dur=3.0):
    """Filter från equirect till önskad vy. mode: view (platt vy), planet (liten planet),
    ball (kristallkula), split (två vyer över varandra – byggs separat)."""
    big = int(math.hypot(out_w, out_h)) // 2 * 2 + 2  # så stor att rotationen aldrig visar hörnen
    if mode == "planet":
        # stereografisk projektion rakt ner, långsam rotation
        return [f"v360@cam=input=e:output=sg:pitch=-90:h_fov=300:v_fov=300:w={big}:h={big}"
                f":yaw={yaw:.1f}:interp=line:reset_rot=1",
                "rotate=a='0.35*t':fillcolor=black",
                f"crop={out_w}:{out_h}"]
    if mode == "ball":
        return [f"v360@cam=input=e:output=sg:pitch=90:h_fov=290:v_fov=290:w={big}:h={big}"
                f":yaw={yaw:.1f}:interp=line:reset_rot=1",
                f"crop={out_w}:{out_h}"]
    hfov = fov or VIEW_FOV
    # bildvinkeln gäller den längsta sidan
    if out_w >= out_h:
        h_fov = hfov
        v_fov = math.degrees(2 * math.atan(math.tan(math.radians(hfov) / 2) * out_h / out_w))
    else:
        v_fov = hfov
        h_fov = math.degrees(2 * math.atan(math.tan(math.radians(hfov) / 2) * out_w / out_h))
    f = (f"v360@cam=input=e:output=flat:h_fov={h_fov:.2f}:v_fov={v_fov:.2f}:w={out_w}:h={out_h}"
         f":yaw={yaw:.1f}:pitch={pitch:.1f}:interp=line:reset_rot=1")
    out = []
    if cmdfile:
        out.append(f"sendcmd=f={Path(cmdfile).name}")
    out.append(f)
    return out


def render_view(src, layout, path, dst, mode="ai", size=VIEW_SIZE, fov=VIEW_FOV, progress=None):
    """Renderar en virtuell kamera ur 360-källan till ett vanligt klipp (kvadrat, eller delad bild)."""
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    work = dst.parent
    dur = max(p[0] for p in path) + 2.0 if path else 3600
    cmd = work / f"{dst.stem}.cmd"
    tmp = dst.with_suffix(".tmp.mp4")
    if mode == "split":
        half = size // 2
        cmd2 = work / f"{dst.stem}_b.cmd"
        write_cmds(cmd, path, 0.0, dur)
        write_cmds(cmd2, path, 0.0, dur, yaw_off=180.0)
        a = ",".join(cam_filter("view", size, half, cmd.name, fov=fov))
        b = ",".join(cam_filter("view", size, half, cmd2.name, fov=fov)).replace("v360@cam", "v360@camb")
        Path(cmd2).write_text(Path(cmd2).read_text("utf-8").replace("v360@cam", "v360@camb"), "utf-8")
        graph, two = input_graph(layout)
        head = graph if two else "[0:v:0]" + (graph or "null")
        fc = (f"{head},split[s1][s2];[s1]{a}[a];[s2]{b}[b];"
              f"[a][b]vstack,drawbox=x=0:y={half - 2}:w=iw:h=4:color=black:t=fill,format=yuv420p[v]")
        maps = ["-filter_complex", fc, "-map", "[v]"]
        args = ["-i", str(src)]
        w, h = size, size
    else:
        write_cmds(cmd, path, 0.0, dur)
        args, maps = _ff_input(src, layout, ",".join(cam_filter("view", size, size, cmd.name, fov=fov) + ["format=yuv420p"]))
        w, h = size, size
    run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *args, *maps, "-map", "0:a:0?",
         *video_encoder_args(w, h, "final"), "-r", "30", "-c:a", "aac", "-b:a", "160k",
         "-movflags", "+faststart", str(tmp)], cwd=str(work))
    os.replace(tmp, dst)
    for f in (cmd, work / f"{dst.stem}_b.cmd"):
        try:
            f.unlink()
        except OSError:
            pass
    return dst


def save_meta(project_dir, cid, data):
    d = Path(project_dir) / "pano"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{cid}.json").write_text(json.dumps(data), "utf-8")


def load_meta(project_dir, cid):
    try:
        return json.loads((Path(project_dir) / "pano" / f"{cid}.json").read_text("utf-8"))
    except (OSError, ValueError):
        return None


CAM_MODES = {"ai": "AI-vy", "planet": "Liten planet", "ball": "Kristallkula", "whip": "360-svep"}


def custom(cam):
    """Behöver klippet tas direkt ur 360-källan (annat än den färdiga AI-vyn)?"""
    cam = cam or {}
    return (cam.get("mode") or "ai") != "ai" or abs(float(cam.get("yaw") or 0)) > 0.5 or bool(cam.get("fov"))


def shot_filters(meta, cam, layout, out_w, out_h, shot, workdir, idx):
    """Filter för ett klipp ur 360-källan. Returnerar (filterlista, behöver_två_strömmar).
    Listan börjar med ihopsyning (om .insv) och slutar med en platt bild i out_w×out_h."""
    cam = cam or {}
    mode = cam.get("mode") or "ai"
    graph, two = input_graph(layout)
    pre = []
    if graph:
        pre.append(graph.split(",", 1)[1] if two else graph)  # hstack läggs till av den som kör FFmpeg
    path = meta.get("path") or [[0, 0, 0]]
    speed = float((shot.get("fx") or {}).get("speed") or 1.0)
    span = (float(shot["duration"]) + 1.0) * speed
    start = float(shot["src_start"])
    yaw0 = float(cam.get("yaw") or 0)
    if mode in ("planet", "ball"):
        y, _ = _interp_path(path, start)
        pre += cam_filter(mode, out_w, out_h, yaw=_wrap(y + yaw0))
        return pre, two
    cmd = Path(workdir) / f"cam{idx}.cmd"
    if mode == "whip":
        # snabb vridning ett halvt varv mitt i klippet: från motivet till andra hållet
        t0 = max(0.4, float(shot["duration"]) * speed * 0.5 - 0.3)

        def off(t):
            k = min(1.0, max(0.0, (t - t0) / 0.55))
            return yaw0 + 180.0 * (0.5 - 0.5 * math.cos(math.pi * k))
        _write_cmds_fn(cmd, path, start, span, off)
    else:
        write_cmds(cmd, path, start, span, yaw_off=yaw0)
    pre += cam_filter("view", out_w, out_h, cmd.name, fov=float(cam.get("fov") or VIEW_FOV))
    return pre, two


def _write_cmds_fn(dst, path, start, dur, off, step=0.1):
    lines = []
    t = 0.0
    while t <= dur + step:
        y, p = _interp_path(path, start + t)
        lines.append(f"{t:.3f} v360@cam yaw {_wrap(y + off(t)):.2f}, v360@cam pitch {p:.2f};")
        t += step
    Path(dst).write_text("\n".join(lines) + "\n", "utf-8")
    return dst
