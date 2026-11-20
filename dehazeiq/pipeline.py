"""Jobb som körs i bakgrunden: import, analys, musik och rendering."""

from pathlib import Path

from . import analysis, generator, media, music, quality, render, timeline
from .config import AUDIO_EXT, FORMATS
from .project import Project, clip_id_for, collect_video_files, save_default_settings


def import_media(progress, pid, paths):
    proj = Project(pid)
    files = collect_video_files(paths)
    if not files:
        raise RuntimeError("Hittade inga videofiler (MP4, MOV, M4V …) på den platsen.")
    added, skipped, failed = [], 0, []
    for i, f in enumerate(files):
        progress(0.3 * i / len(files), f"Läser {f.name}")
        try:
            cid = clip_id_for(f)
        except OSError:
            failed.append(f.name)
            continue
        if cid in proj.data["clips"]:
            skipped += 1
            continue
        try:
            info = media.probe(f)
        except media.MediaError:
            failed.append(f.name)
            continue
        if not info.get("width") or info.get("duration", 0) < 0.5:
            failed.append(f.name)
            continue
        info.update(id=cid, status="probed")
        if info["is360"]:
            info["note"] = "360-material: exportera platt video från Insta360 Studio först"
        proj.reload()
        proj.data["clips"][cid] = info
        proj.data["order"].append(cid)
        proj.save()
        added.append(cid)

    todo = [c for c in added if not proj.data["clips"][c].get("is360")]
    for i, cid in enumerate(todo):
        clip = proj.data["clips"][cid]
        progress(0.3 + 0.7 * i / max(1, len(todo)), f"Skapar proxy {i + 1} av {len(todo)}: {clip['name']}")
        try:
            dst = media.make_proxy(clip["path"], proj.proxy_path(cid), clip)
            pinfo = media.probe(dst)
            proj.update_clip(cid, status="proxy", proxy_width=pinfo["width"],
                             proxy_height=pinfo["height"], has_audio=pinfo["has_audio"])
        except Exception as exc:  # noqa: BLE001
            proj.update_clip(cid, status="error", error=str(exc)[:300])
    return {"added": len(added), "skipped": skipped, "failed": failed}


def analyze(progress, pid, redo=False):
    proj = Project(pid)
    todo = [c for c in proj.clips()
            if proj.proxy_path(c["id"]).exists() and not c.get("is360")
            and (redo or not c.get("analysis"))]
    if not todo:
        return {"analyzed": 0, "excluded": assess(pid)}
    done = 0
    for i, clip in enumerate(todo):
        base = i / len(todo)

        def sub(frac, _b=base):
            progress(_b + frac / len(todo), None)

        progress(base, f"Analyserar {i + 1} av {len(todo)}: {clip['name']}")
        try:
            summary = analysis.analyze_clip(proj.proxy_path(clip["id"]), proj.npz_path(clip["id"]), sub)
            proj.update_clip(clip["id"], analysis=summary, status="analyzed")
            done += 1
        except Exception as exc:  # noqa: BLE001
            proj.update_clip(clip["id"], status="error", error=str(exc)[:300])
    excluded = assess(pid)
    return {"analyzed": done, "excluded": excluded}


def assess(pid):
    """Automatiskt bortval av svaga klipp (suddiga, skakiga, felexponerade, klart sämre)."""
    proj = Project(pid)
    proj.reload()
    n = quality.assess(list(proj.data["clips"].values()))
    proj.save()
    return n


def set_music(pid, path):
    proj = Project(pid)
    if not path:
        proj.reload()
        proj.data["music"] = None
        proj.save()
        return None
    p = Path(path).expanduser()
    if not p.is_file() or p.suffix.lower() not in AUDIO_EXT:
        raise RuntimeError("Välj en ljudfil (MP3, M4A, WAV, AIFF, FLAC).")
    info = music.analyze(p)
    info["name"] = p.stem
    proj.reload()
    proj.data["music"] = info
    proj.save()
    return info


def generate(pid, style, fmt, length, favorites=(), theme=None):
    if fmt not in FORMATS:
        raise RuntimeError(f"Okänt format: {fmt}")
    proj = Project(pid)
    props = generator.generate_set(proj, style, fmt, float(length), proj.data.get("music"), favorites, theme)
    proj.reload()
    proj.data["settings"] = {"format": fmt, "length": length, "style": style}
    proj.save()
    save_default_settings(proj.data["settings"])
    proj.add_proposals(props)
    return props


def regenerate_one(pid, prop_id):
    proj = Project(pid)
    old = proj.proposal(prop_id)
    if not old:
        raise RuntimeError("Förslaget finns inte")
    new = generator.generate(proj, old["style"], old["format"], old["target_length"],
                             None, proj.data.get("music"), old.get("favorites", []), old.get("theme"))
    proj.add_proposals([new])
    return new


def render_proposal(progress, pid, prop_id, resolution="preview"):
    proj = Project(pid)
    prop = proj.proposal(prop_id)
    if not prop:
        raise RuntimeError("Förslaget finns inte")
    if resolution == "preview":
        out = proj.renders / f"{prop_id}_preview.mp4"
    else:
        safe = f"{proj.data['name']} - {prop['style_label']} {prop['format'].replace(':', 'x')} {resolution}"
        safe = "".join(ch if (ch.isalnum() or ch in "-_") else " " for ch in safe)
        safe = " ".join(safe.split())
        out = proj.renders / f"{safe}.mp4"
    render.render(proj, prop, resolution, out, progress)
    renders = dict(prop.get("renders") or {})
    renders[resolution] = out.name
    result = {"file": out.name, "path": str(out)}
    if resolution != "preview":
        otio = out.with_suffix(".otio")
        timeline.write_otio(proj, prop, otio)
        renders["otio"] = otio.name
        result["otio"] = otio.name
    proj.update_proposal(prop_id, renders=renders)
    return result


def _stage(progress, lo, hi, label):
    def sub(frac=None, message=None):
        progress(None if frac is None else lo + (hi - lo) * frac,
                 None if message is None else f"{label} · {message}")
    return sub


def auto(progress, pid, paths=None):
    """Hela flödet utan att användaren behöver göra något:
    import → analys → bortval av svaga klipp → tre filmförslag → förhandsvisningar."""
    result = {}
    if paths:
        result["import"] = import_media(_stage(progress, 0.0, 0.35, "1/4 Läser in"), pid, paths)
    result["analysis"] = analyze(_stage(progress, 0.35, 0.72, "2/4 Analyserar"), pid)
    proj = Project(pid)
    if not proj.usable_clips():
        raise RuntimeError("Inget klipp klarade kvalitetskraven (skärpa, exponering, stabilitet). "
                           "Markera klipp som \"Måste med\" i analysvyn om du ändå vill använda dem.")
    progress(0.74, "3/4 Skapar filmförslag")
    s = proj.data.get("settings") or {}
    favs = [c["id"] for c in proj.clips() if c.get("favorite") and c.get("analysis")]
    props = generate(pid, s.get("style", "auto"), s.get("format", "9:16"), s.get("length", 30), favs)
    result["proposals"] = [p["id"] for p in props]
    for i, prop in enumerate(props):
        lo = 0.78 + 0.22 * i / len(props)
        hi = 0.78 + 0.22 * (i + 1) / len(props)
        render_proposal(_stage(progress, lo, hi, f"4/4 Förhandsvisning {i + 1} av {len(props)}"),
                        pid, prop["id"], "preview")
    return result


def diagnostics(pid):
    """Liten rapport (utan filmerna) för att kunna justera AI:ns gränser:
    projektdata, analysvärden och en bild per klipp från dess bästa sekvens."""
    import io
    import json
    import time
    import zipfile

    import cv2

    proj = Project(pid)
    name = f"DeHazeIQ-rapport-{time.strftime('%Y%m%d-%H%M')}.zip"
    out = proj.renders / name
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("project.json", json.dumps(proj.data, ensure_ascii=False, indent=1))
        rows = ["fil;i_filmen;orsaker;skarpa;fokus;exponering;stabilitet;intresse;skonhet;taggar"]
        for c in proj.clips():
            a = c.get("analysis") or {}
            rows.append(";".join(str(x) for x in (
                c["name"], quality.is_usable(c), "/".join(c.get("reasons") or []),
                a.get("best_sharp"), a.get("best_focus"), a.get("best_expo"), a.get("best_stab"),
                a.get("best_interest"), a.get("best_beauty"), "/".join(a.get("tags") or []))))
            px = proj.proxy_path(c["id"])
            if a and px.exists():
                cap = cv2.VideoCapture(str(px))
                cap.set(cv2.CAP_PROP_POS_MSEC, (a["best"][0] + a["best"][1]) / 2 * 1000)
                ok, img = cap.read()
                cap.release()
                if ok:
                    h, w = img.shape[:2]
                    img = cv2.resize(img, (480, int(h * 480 / w)), interpolation=cv2.INTER_AREA)
                    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    tag = "MED" if quality.is_usable(c) else "BORT"
                    z.writestr(f"bilder/{tag}_{c['name']}.jpg", buf.tobytes())
        z.writestr("klipp.csv", "\n".join(rows))
    return out


def themes(pid):
    proj = Project(pid)
    if not proj.usable_clips():
        return []
    s = proj.data.get("settings") or {}
    try:
        return generator.themes(proj, s.get("format", "9:16"))
    except generator.GenerateError:
        return []
