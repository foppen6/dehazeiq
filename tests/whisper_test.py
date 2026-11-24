"""Tal till text på riktigt: laddar ner Whisper base och röstdetektorn och transkriberar
whisper.cpp:s exempelfil. Används av byggsystemet (DEHAZEIQ_WHISPER pekar på appens whisper-cli)."""

import os
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DEHAZEIQ_HOME", tempfile.mkdtemp(prefix="dhq_whisper_"))
os.environ["PATH"] = str(ROOT / "packaging" / "ffmpeg") + os.pathsep + os.environ.get("PATH", "")

from dehazeiq import whisper  # noqa: E402

print("whisper-cli:", whisper.binary())
t = time.time()
whisper.download(model_id="base")
print("Nedladdat på", round(time.time() - t), "s:", whisper.model_path(), whisper.vad_path())

wav = Path(os.environ["DEHAZEIQ_HOME"]) / "jfk.wav"
urllib.request.urlretrieve("https://github.com/ggml-org/whisper.cpp/raw/master/samples/jfk.wav", wav)
t = time.time()
r = whisper.transcribe(wav, lang="auto")
print("Transkriberat på", round(time.time() - t, 1), "s:", r)
text = " ".join(s["text"] for s in r["segments"]).lower()
assert "country" in text, "hittade inte talet"
assert r["lang"] == "en", "fel språk"
print("TAL TILL TEXT OK")
