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
    print(pipeline.import_media(prog, p.id, [str(media)]))
    print(pipeline.analyze(prog, p.id))
    m = pipeline.set_music(p.id, str(media / "music120.m4a"))
    print("BPM:", m["bpm"])
    assert 110 < m["bpm"] < 130, "Tempot borde vara cirka 120 BPM"
    props = pipeline.generate(p.id, "auto", "9:16", 15)
    for pr in props:
        print(pr["style"], pr["n_shots"], "klipp", pr["length"], "s")
        assert abs(pr["length"] - 15) < 1.5
    r = pipeline.render_proposal(prog, p.id, props[0]["id"], "preview")
    print("Förhandsvisning:", r["file"])
    r = pipeline.render_proposal(prog, p.id, props[1]["id"], "720p")
    print("Export:", r["file"], "+", r["otio"])
    print(f"OK på {time.time() - t:.1f} s. Testdata i {WORK}")


if __name__ == "__main__":
    main()
