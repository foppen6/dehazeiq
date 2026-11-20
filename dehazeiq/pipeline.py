"""Jobb som körs i bakgrunden: import, analys, musik och rendering."""

from pathlib import Path

from . import analysis, generator, media, music, render, timeline
from .config import AUDIO_EXT, FORMATS
from .project import Project, clip_id_for, collect_video_files


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
        return {"analyzed": 0}
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
    return {"analyzed": done}


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


def generate(pid, style, fmt, length, favorites=()):
    if fmt not in FORMATS:
        raise RuntimeError(f"Okänt format: {fmt}")
    proj = Project(pid)
    props = generator.generate_set(proj, style, fmt, float(length), proj.data.get("music"), favorites)
    proj.reload()
    proj.data["settings"] = {"format": fmt, "length": length, "style": style}
    proj.save()
    proj.add_proposals(props)
    return props


def regenerate_one(pid, prop_id):
    proj = Project(pid)
    old = proj.proposal(prop_id)
    if not old:
        raise RuntimeError("Förslaget finns inte")
    new = generator.generate(proj, old["style"], old["format"], old["target_length"],
                             None, proj.data.get("music"), old.get("favorites", []))
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
