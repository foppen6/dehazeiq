"""Jobb som körs i bakgrunden: import, analys, musik och rendering."""

import time
from pathlib import Path

import numpy as np

from . import ai, analysis, generator, media, music, pano, photo, quality, render, timeline
from .config import AUDIO_EXT, FORMATS
from .project import Project, clip_id_for, collect_video_files, save_default_settings


def import_media(progress, pid, paths):
    proj = Project(pid)
    files = collect_video_files(paths)
    if not files:
        raise RuntimeError("Hittade inga video- eller bildfiler (MP4, MOV, JPG, HEIC, NEF …) på den platsen.")
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
        meta = None
        if photo.is_photo_file(f):
            # fotot blir ett stillbildsklipp i projektet; originalet rörs inte
            progress(0.3 * i / len(files), f"Läser bild {f.name}")
            try:
                meta = photo.to_clip(f, proj.photo_clip_path(cid))
            except Exception:  # noqa: BLE001
                failed.append(f.name)
                continue
        try:
            info = media.probe(proj.photo_clip_path(cid) if meta else f)
        except media.MediaError:
            failed.append(f.name)
            continue
        if meta:
            info.update(meta, name=f.name, is360=False, has_audio=False,
                        created=meta.get("photo_time") or f.stat().st_mtime,
                        source=photo_source(meta, f))
        if not info.get("width") or info.get("duration", 0) < 0.5:
            failed.append(f.name)
            continue
        info.update(id=cid, status="probed")
        if info["is360"]:
            info["layout360"] = pano.detect(f, info) or "equirect"
            info["note"] = "360-film: AI väljer vyer"
        proj.reload()
        proj.data["clips"][cid] = info
        proj.data["order"].append(cid)
        proj.save()
        added.append(cid)

    # 360-film: AI väljer vart kameran tittar, och vyerna blir vanliga klipp
    for cid in [c for c in added if proj.data["clips"][c].get("is360")]:
        try:
            added += make_360_views(progress, proj, cid)
        except Exception as exc:  # noqa: BLE001
            proj.update_clip(cid, status="error", error=f"360: {str(exc)[:280]}")
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


def make_360_views(progress, proj, cid):
    """360-klipp → AI-vy (följer motivet) och delad vy (motivet + andra hållet). Returnerar nya klipp-id."""
    clip = proj.data["clips"][cid]
    layout = clip.get("layout360") or "equirect"
    name = clip["name"]
    progress(0.3, f"360: förbereder {name}")
    eq = proj.dir / "pano" / f"{cid}_equi.mp4"
    pano.make_proxy(clip["path"], eq, layout)
    model = ai.get()
    progress(0.32, f"360: AI letar efter motivet i {name}")
    if model:
        found = pano.find_path(eq, model)
    else:
        found = {"path": [[0.0, 0.0, 0.0], [float(clip.get("duration") or 1), 0.0, 0.0]], "conf": 0.0}
    pano.save_meta(proj.dir, cid, {"layout": layout, "path": found["path"], "conf": found["conf"], "proxy": str(eq)})
    # så skarp som källan räcker till: equirect-bredden × bildvinkel / 360
    ew = int(clip.get("width") or 3840) * (2 if layout == "dual" else 1)
    size = int(min(pano.VIEW_SIZE, max(720, ew * pano.VIEW_FOV / 360.0))) // 2 * 2
    new = []
    for mode, label in (("ai", "AI-vy"), ("split", "delad bild")):
        vid = f"{cid}_{mode}"
        dst = proj.dir / "views" / f"{vid}.mp4"
        progress(0.34, f"360: renderar {label} av {name}")
        pano.render_view(clip["path"], layout, found["path"], dst, mode=mode, size=size)
        info = media.probe(dst)
        info.update(id=vid, status="probed", name=f"{name} · {label}", parent360=cid, view360=mode,
                    created=clip.get("created"), source="Insta360", is360=False,
                    has_audio=info.get("has_audio", False))
        if mode == "split":
            info["portrait_only"] = True
        proj.reload()
        proj.data["clips"][vid] = info
        if vid not in proj.data["order"]:
            proj.data["order"].append(vid)
        proj.save()
        new.append(vid)
    proj.update_clip(cid, note="360-film: AI-vy och delad bild skapade", status="proxy")
    return new


def photo_source(meta, f):
    make = (meta.get("photo_make") or "").lower()
    if "nikon" in make:
        return "Nikon"
    if make in ("apple", "google", "samsung") or f.name.upper().startswith(("IMG_", "PXL_")):
        return "Mobil"
    return "Foto"


def target_version():
    """Den analysversion den här installationen kan ge (3 kräver artmodellen)."""
    if not ai.available():
        return 1
    return analysis.ANALYSIS_VERSION if ai.get_bio() else 2


def outdated(clip):
    """Analyserad med en äldre version (saknar t.ex. AI-positionen eller arten)?"""
    a = clip.get("analysis") or {}
    return bool(a) and a.get("ai") is not False and a.get("v", 1) < target_version()


def analyze(progress, pid, redo=False):
    proj = Project(pid)
    todo = [c for c in proj.clips()
            if proj.proxy_path(c["id"]).exists() and not c.get("is360")
            and (redo or not c.get("analysis") or outdated(c))]
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


def set_music(pid, path, track=None):
    proj = Project(pid)
    if track:
        from . import musiclib
        info = musiclib.track_music(track)
        if not info:
            raise RuntimeError("Låten finns inte i biblioteket längre")
        info["auto"] = False
        proj.reload()
        proj.data["music"] = info
        proj.save()
        return info
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
    recent = [p.get("theme") for p in (proj.data.get("proposals") or [])[:3] if p.get("theme")]
    props = generator.generate_set(proj, style, fmt, float(length), proj.data.get("music"), favorites, theme,
                                   avoid=recent)
    proj.reload()
    proj.data.setdefault("settings", {}).update(format=fmt, length=length, style=style)
    proj.save()
    save_default_settings(proj.data["settings"])
    proj.add_proposals(props)
    return props


def generate_plans(progress, pid, plans, render_previews=False):
    """Förslag för de valda filmtyperna (dykfilm, resefilm, reels, djurporträtt …)."""
    from . import editor
    proj = Project(pid)
    music = proj.data.get("music")
    favs = [c["id"] for c in proj.clips() if c.get("favorite") and c.get("analysis")]
    ids, made = [], []
    for k, plan in enumerate(plans):
        progress(k / max(1, len(plans)), editor.describe_plan(plan))
        recent = [p.get("theme") for p in (proj.data.get("proposals") or [])[:3] if p.get("theme")]
        props = editor.plan_proposals(proj, plan, music, favs, recent)
        made += props
        ids += [p["id"] for p in props]
    # i samma ordning som planerna
    Project(pid).add_proposals(made)
    if render_previews:
        for i, pid_ in enumerate(ids):
            render_proposal(_stage(progress, i / len(ids), (i + 1) / len(ids), f"Förhandsvisning {i + 1} av {len(ids)}"),
                            pid, pid_, "preview")
    return ids


def edit_proposal(pid, prop_id, op, args):
    from . import editor
    proj = Project(pid)
    prop = proj.proposal(prop_id)
    if not prop:
        raise RuntimeError("Förslaget finns inte")
    prop = editor.apply(proj, prop, op, args or {})
    proj.replace_proposal(prop)
    if op == "promo":
        proj.reload()
        proj.data["promo_last"] = prop["promo"]
        if (args or {}).get("all"):
            for other in proj.data.get("proposals") or []:
                same_kind = (other.get("style") == "trailer") == (prop.get("style") == "trailer")
                if other["id"] != prop["id"] and "promo" in other and same_kind:
                    other["promo"] = dict(prop["promo"])
                    other["renders"] = {}
        proj.save()
    return prop


def set_platform(pid, prop_id, platform, length=None):
    from . import editor
    proj = Project(pid)
    prop = proj.proposal(prop_id)
    if not prop:
        raise RuntimeError("Förslaget finns inte")
    new = editor.retarget(proj, prop, platform, length, keep_id=True)
    proj.replace_proposal(new)
    return new


def export_for(progress, pid, prop_id, platform, resolution="1080p", lang="sv"):
    """Exportera ett förslag för en plattform. Har förslaget ett annat format görs en kopia
    anpassad för plattformen (samma berättelse, stil, färg och titel)."""
    from . import editor
    proj = Project(pid)
    prop = proj.proposal(prop_id)
    if not prop:
        raise RuntimeError("Förslaget finns inte")
    from .config import PLATFORMS
    if platform and platform != prop.get("platform") and PLATFORMS[platform]["format"] != prop["format"]:
        progress(0.02, f"Anpassar för {PLATFORMS[platform]['label']}")
        prop = editor.retarget(proj, prop, platform, keep_id=False)
        prop["edited"] = time.time()  # gallras inte bort
        proj.add_proposals([prop])
    return render_proposal(progress, pid, prop["id"], resolution, lang)


def regenerate_one(pid, prop_id):
    proj = Project(pid)
    old = proj.proposal(prop_id)
    if not old:
        raise RuntimeError("Förslaget finns inte")
    new = generator.generate(proj, old["style"], old["format"], old["target_length"],
                             None, proj.data.get("music"), old.get("favorites", []), old.get("theme"))
    proj.add_proposals([new])
    return new


def render_proposal(progress, pid, prop_id, resolution="preview", lang="sv"):
    from . import i18n
    proj = Project(pid)
    prop = proj.proposal(prop_id)
    if not prop:
        raise RuntimeError("Förslaget finns inte")
    lang = lang if lang in i18n.LANGS else "sv"
    if resolution == "preview":
        out = proj.renders / (f"{prop_id}_preview.mp4" if lang == "sv" else f"{prop_id}_preview_{lang}.mp4")
    else:
        safe = f"{proj.data['name']} - {prop.get('title') or ''} {prop['style_label']} {prop['format'].replace(':', 'x')} {resolution}"
        if lang != "sv":
            safe += f" {lang.upper()}"
        safe = "".join(ch if (ch.isalnum() or ch in "-_") else " " for ch in safe)
        safe = " ".join(safe.split())
        out = proj.renders / f"{safe}.mp4"
    free = {}
    if lang != "sv":
        need = i18n.free_texts(prop, lang)
        cache = (proj.data.get("i18n_cache") or {}).get(lang, {})
        missing = [t for t in need if t not in cache]
        if missing:
            progress(0.01, "Översätter texterna")
            got = i18n.translate_free(missing, lang)
            if got:
                proj.reload()
                proj.data.setdefault("i18n_cache", {}).setdefault(lang, {}).update(got)
                proj.save()
                cache = dict(cache, **got)
        free = cache
    render.render(proj, prop, resolution, out, progress, lang=lang, free=free)
    renders = dict(prop.get("renders") or {})
    key = resolution if lang == "sv" else f"{resolution}:{lang}"
    renders[key] = out.name
    result = {"file": out.name, "path": str(out)}
    if resolution != "preview":
        otio = out.with_suffix(".otio")
        timeline.write_otio(proj, prop, otio)
        renders["otio"] = otio.name
        result["otio"] = otio.name
        srt = out.with_suffix(".srt")
        if render.write_srt(proj, prop, srt, lang, free):
            result["srt"] = srt.name
        lic = prop.get("music_license") or {}
        if prop.get("music_credit") or lic.get("url"):
            # musikens licens och tack, att klistra in i inläggets text
            txt = out.with_suffix(".musik.txt")
            txt.write_text("\n".join(x for x in (prop.get("music_credit") or f"Musik: {prop.get('music_name')}",
                                                  f"Licens: {lic.get('code', '').upper()} {lic.get('url', '')}".strip(),
                                                  lic.get("source", "")) if x and x != "Licens:") + "\n", "utf-8")
            result["credits"] = txt.name
    proj.update_proposal(prop_id, renders=renders)
    return result


def _keyframe_times(proj, clip, max_frames=8):
    """Tidpunkter att visa för djupanalysen: jämnt fördelade över klippets bättre delar."""
    a = clip.get("analysis") or {}
    dur = float(a.get("duration") or clip.get("duration") or 0)
    if dur <= 0:
        return []
    cands = np.arange(min(1.0, dur / 2), dur, 2.5)
    try:
        with np.load(proj.npz_path(clip["id"])) as d:
            t, q = d["t"], d["quality"]
        if len(t) > 4:
            ok = q >= np.percentile(q, 40)
            good = [x for x in cands if ok[int(np.argmin(np.abs(t - x)))]]
            cands = np.array(good or list(cands))
    except (OSError, KeyError, ValueError):
        pass
    if len(cands) > max_frames:
        cands = cands[np.linspace(0, len(cands) - 1, max_frames).round().astype(int)]
    return [round(float(x), 2) for x in cands]


def _species_hint(proj, cid, t, bio):
    if not bio:
        return ()
    try:
        with np.load(proj.npz_path(cid)) as d:
            if "bio_emb" not in d:
                return ()
            lt, be = d["loc_t"], d["bio_emb"]
        near = np.abs(lt - t) <= 2.5
        if not near.any():
            return ()
        return tuple((sp[0], sp[2]) for sp, p in bio.top(be[near].astype(np.float32), 3) if p >= 0.08)
    except (OSError, KeyError, ValueError):
        return ()


def deep_analyze(progress, pid, redo=False):
    """Djupanalys med Qwen3-VL: beskriver vad som händer i de klipp som kom med."""
    import cv2

    from . import vlm
    proj = Project(pid)
    clips = [c for c in proj.clips() if quality.is_usable(c) and c.get("analysis")
             and (redo or (c.get("vlm") or {}).get("v") != vlm.VLM_VERSION)]
    if not clips:
        return {"described": 0}
    jobs = [(c, t) for c in clips for t in _keyframe_times(proj, c)]
    bio = ai.get_bio()
    model = (vlm.choose_model() or {}).get("name")
    progress(0.0, f"Startar {model} …")
    done = 0
    with vlm.Server() as server:
        for c in clips:
            frames = []
            src = proj.proxy_path(c["id"])
            if not src.exists():
                src = Path(c["path"])
            cap = cv2.VideoCapture(str(src))
            under = bool((c.get("analysis") or {}).get("underwater", True))
            for t in _keyframe_times(proj, c):
                done += 1
                progress(done / max(1, len(jobs)), f"Beskriver {c['name']} ({done} av {len(jobs)})")
                cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
                ok, img = cap.read()
                if not ok:
                    continue
                r = vlm.describe(server, img, under, _species_hint(proj, c["id"], t, bio))
                if r:
                    r["t"] = t
                    frames.append(r)
            cap.release()
            proj.update_clip(c["id"], vlm={"v": vlm.VLM_VERSION, "model": model, "frames": frames})
    return {"described": len(clips), "frames": len(jobs)}


def analyze_all(progress, pid, redo=False):
    """Analys och – om modellen finns – djupanalys i samma jobb."""
    from . import vlm
    deep = vlm.ready()
    res = analyze(_stage(progress, 0.0, 0.7 if deep else 1.0, "Analys"), pid, redo)
    if deep:
        try:
            res["deep"] = deep_analyze(_stage(progress, 0.7, 1.0, "Djupanalys"), pid, redo)
        except Exception as e:  # noqa: BLE001
            print("Djupanalysen misslyckades:", e)
            res["deep_error"] = str(e)
    return res


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
    from . import vlm
    deep = vlm.ready()
    result["analysis"] = analyze(_stage(progress, 0.35, 0.6 if deep else 0.72, "2/4 Analyserar"), pid)
    if deep:
        try:
            result["deep"] = deep_analyze(_stage(progress, 0.6, 0.72, "2/4 Djupanalys"), pid)
        except Exception as e:  # noqa: BLE001
            print("Djupanalysen misslyckades, fortsätter utan:", e)
    proj = Project(pid)
    if not proj.usable_clips():
        raise RuntimeError("Inget klipp klarade kvalitetskraven (skärpa, exponering, stabilitet). "
                           "Markera klipp som \"Måste med\" i analysvyn om du ändå vill använda dem.")
    progress(0.74, "3/4 Skapar filmförslag")
    s = proj.data.get("settings") or {}
    favs = [c["id"] for c in proj.clips() if c.get("favorite") and c.get("analysis")]
    if s.get("plans"):
        props = generate_plans(_stage(progress, 0.74, 0.78, "3/4 Filmförslag"), pid, s["plans"], render_previews=False)
        props = [Project(pid).proposal(i) for i in props]
        props = [p for p in props if p]
    else:
        props = generate(pid, s.get("style", "auto"), s.get("format", "9:16"), s.get("length", 30), favs)
    result["proposals"] = [p["id"] for p in props]
    if not s.get("previews", True):
        props = []
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
