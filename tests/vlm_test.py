"""Kör djupanalysen på riktigt med den minsta modellen (Qwen3-VL 2B). Används av byggsystemet
för att kontrollera att llama-server, nedladdning, anrop och tolkning av svaret fungerar."""

import os
import sys
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DEHAZEIQ_HOME", tempfile.mkdtemp(prefix="dhq_vlm_"))
os.environ["DEHAZEIQ_VLM_FORCE"] = "1"

from dehazeiq import vlm  # noqa: E402

vlm.MODEL_DIR = Path(os.environ["DEHAZEIQ_HOME"]) / "models" / "vlm"
vlm.MODELS = [(0, "Qwen/Qwen3-VL-2B-Instruct-GGUF", "Qwen3-VL 2B", 2)]
print("llama-server:", vlm.server_binary())
t = time.time()
vlm.download(lambda f, m: None)
print("Nedladdat på", round(time.time() - t), "s:", vlm.model_paths(vlm.MODELS[0][1]))

# En enkel testbild: en orange fisk mot blått vatten
img = np.zeros((480, 854, 3), np.uint8)
img[:] = (140, 90, 20)
cv2.ellipse(img, (430, 250), (140, 60), 0, 0, 360, (20, 120, 250), -1)
cv2.fillConvexPoly(img, np.array([[560, 250], [650, 190], [650, 310]]), (20, 120, 250))
cv2.circle(img, (350, 235), 12, (255, 255, 255), -1)
cv2.circle(img, (350, 235), 6, (0, 0, 0), -1)

for ngl in ("99", "0"):
    os.environ["DEHAZEIQ_NGL"] = ngl
    try:
        t = time.time()
        with vlm.Server(ctx=4096) as s:
            print("Server startad (ngl", ngl, ") på", round(time.time() - t), "s")
            t = time.time()
            r = vlm.describe(s, img, True, (("Clownfisk", "Amphiprion ocellaris"),))
            print("Svar på", round(time.time() - t, 1), "s:", r)
            assert r and r["what"], "tomt svar"
        print("DJUPANALYS OK")
        break
    except Exception as e:  # noqa: BLE001
        print("Misslyckades med ngl", ngl, ":", e)
        log = Path(os.environ["DEHAZEIQ_HOME"]) / "llama-server.log"
        if log.exists():
            print(log.read_text(errors="replace")[-3000:])
else:
    sys.exit(1)
