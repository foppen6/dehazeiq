"""Snabbtest av hela kedjan med syntetiska klipp (kräver bara FFmpeg).

Kör från projektroten:  python tests/smoke_test.py
"""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
WORK = Path(tempfile.mkdtemp(prefix="dehazeiq_test_"))
os.environ["DEHAZEIQ_HOME"] = str(WORK / "home")

from dehazeiq import pipeline  # noqa: E402
from dehazeiq.media import ffmpeg  # noqa: E402
from dehazeiq.project import Project  # noqa: E402


def make_media(folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    f = [ffmpeg(), "-hide_banner", "-loglevel", "error", "-y"]
    x264 = ["-c:v", "libx264", "-preset", "ultrafast"]
    jobs = [
        ["-f", "lavfi", "-i", "testsrc2=s=1920x1080:r=30:d=8", "-f", "lavfi", "-i", "sine=f=300:d=8",
         "-vf", "colorchannelmixer=rr=0.35:gg=0.9:bb=1.1", *x264, "-c:a", "aac", "-shortest", "DSC_0412.MOV"],
        ["-f", "lavfi", "-i", "mandelbrot=s=1280x720:r=30", "-t", "10", *x264, "VID_20260312_093100.mp4"],
        ["-f", "lavfi", "-i", "testsrc=s=1280x720:r=30:d=6", "-vf", "boxblur=10:2", *x264, "blurry.mp4"],
        ["-f", "lavfi", "-i", "life=s=540x960:r=25:mold=10:ratio=0.2", "-t", "6",
         "-vf", "scale=1080:1920:flags=neighbor", *x264, "PXL_20260312_1104.mp4"],
        ["-f", "lavfi", "-i", "aevalsrc='0.6*sin(2*PI*220*t)*exp(-12*mod(t,0.5))':s=44100:d=40",
         "-c:a", "aac", "music120.m4a"],
    ]
    for j in jobs:
        subprocess.run(f + j[:-1] + [str(folder / j[-1])], check=True)


def main():
    media = WORK / "media"
    print("Skapar testklipp i", media)
    make_media(media)
    p = Project.create("Testprojekt")

    def prog(frac=None, msg=None):
        if msg:
            print("  ", msg)

    t = time.time()
    r = pipeline.auto(prog, p.id, [str(media)])  # hela flödet: import → analys → förslag → förhandsvisningar
    print("Automatiskt:", r)
    p.reload()
    dropped = [c["name"] for c in p.clips() if c.get("auto_excluded")]
    print("Bortvalda:", dropped)
    assert "blurry.mp4" in dropped, "Det suddiga klippet borde väljas bort"
    m = pipeline.set_music(p.id, str(media / "music120.m4a"))
    print("BPM:", m["bpm"])
    assert 110 < m["bpm"] < 130, "Tempot borde vara cirka 120 BPM"
    props = pipeline.generate(p.id, "auto", "9:16", 15)
    for pr in props:
        print(pr["style"], pr["n_shots"], "klipp", pr["length"], "s")
        assert all(sh["name"] != "blurry.mp4" for sh in pr["shots"]), "Suddigt klipp i filmen"
    r = pipeline.render_proposal(prog, p.id, props[0]["id"], "preview")
    print("Förhandsvisning:", r["file"])
    r = pipeline.render_proposal(prog, p.id, props[1]["id"], "720p")
    print("Export:", r["file"], "+", r["otio"])
    # v0.13: foton, beskrivning med egna ord, reklam, musikvideo och trailer
    from dehazeiq import editor, photo, prompt
    if photo.PIL_OK:
        from PIL import Image
        img = WORK / "foto"
        img.mkdir(exist_ok=True)
        Image.new("RGB", (1600, 1200), (30, 90, 140)).save(img / "IMG_0001.jpg")
        r = pipeline.import_media(prog, p.id, [str(img)])
        print("Foton:", r)
        assert r["added"] == 1, "Fotot borde importeras"
        p.reload()
        assert any(c.get("is_photo") for c in p.clips())
    plan = prompt.parse("gör en reklamfilm för tiktok, 15 sek, två varianter", use_llm=False)
    print("Beskrivning:", plan["explain"])
    assert plan["plan"]["type"] == "promo" and plan["plan"]["platform"] == "tiktok"
    p.reload()
    for kind in ("promo", "musicvideo", "trailer"):
        made = editor.plan_proposals(p, {"type": kind, "platform": "reels", "count": 2, "length": 15}, p.data.get("music"))
        print(kind, [x["style"] for x in made])
        assert made
    made[0]["promo"] = {"hook": "Test", "points": ["Ett", "Två"], "cta": "Boka nu", "url": "exempel.se"}
    p.add_proposals(made)
    r = pipeline.render_proposal(prog, p.id, made[0]["id"], "preview")
    print("Trailer med slutbild:", r["file"])
    # v0.14: 360-film (ihopsydd 2:1 från Insta360 Studio) och musikbiblioteket
    from dehazeiq import musiclib
    import subprocess
    from dehazeiq.media import ffmpeg as _ff
    pdir = WORK / "pano"
    pdir.mkdir(exist_ok=True)
    src = next(iter(sorted(media.glob("*.mp4"))))
    subprocess.run([_ff(), "-v", "error", "-y", "-i", str(src), "-t", "4", "-vf",
                    "v360=input=flat:output=e:ih_fov=100:iv_fov=56:yaw=60:w=1920:h=960",
                    str(pdir / "VID_20260101_120000_00_001.mp4")], check=True)
    r = pipeline.import_media(prog, p.id, [str(pdir)])
    p.reload()
    views = [c for c in p.clips() if c.get("parent360")]
    print("360:", r, [c["name"] for c in views])
    assert len(views) == 2, "360-filmen borde ge AI-vy och delad bild"
    musiclib.set_dirs([str(media)])
    print("Musikbibliotek:", musiclib.scan())
    m = musiclib.pick("action", 15)
    assert m and m["bpm"] > 0, "AI:n borde välja en låt ur biblioteket"
    # tal till text: tolkning, filtrering av påhittad text och undertexter i filmens tid
    from dehazeiq import whisper
    segs, lang = whisper.parse_json({"result": {"language": "sv"}, "transcription": [
        {"offsets": {"from": 500, "to": 2600}, "text": " Titta, en bläckfisk!", "tokens": [{"text": " Titta", "p": 0.9}]},
        {"offsets": {"from": 3000, "to": 4000}, "text": " Tack för att ni tittade!", "tokens": [{"text": "x", "p": 0.9}]}]})
    assert len(segs) == 1 and lang == "sv", segs
    fake = {"a": {"duration": 6, "speech": {"segments": segs}}}
    cues = whisper.subtitle_cues({"shots": [{"clip_id": "a", "src_start": 0.0, "src_end": 3.0, "at": 2.0,
                                             "duration": 3.0}]}, fake)
    assert cues and abs(cues[0][0] - 2.5) < 0.01, cues
    print("Tal till text:", cues, whisper.whisper_status()["model"])
    print(f"OK på {time.time() - t:.1f} s. Testdata i {WORK}")


if __name__ == "__main__":
    main()
