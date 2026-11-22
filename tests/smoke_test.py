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
    print(f"OK på {time.time() - t:.1f} s. Testdata i {WORK}")


if __name__ == "__main__":
    main()
