"""Bygger AI-modellpaketet för DeHazeIQ (körs av GitHub Actions, inte av appen).

Hämtar CLIP ViT-B/32 (OpenAI, MIT-licens) i ONNX-format, räknar fram text-
inbäddningarna för packaging/ai_prompts.json och skriver till packaging/models/:
    clip_vision.onnx   – bildmodellen (kvantiserad, ~90 MB)
    text_embeds.npz    – färdiga textinbäddningar per grupp
    prompts.json       – kopia av prompterna (svenska etiketter)
Appen behöver alltså bara bildmodellen och onnxruntime.
"""

import json
import sys
import urllib.request
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE / "models"
REPO = "Xenova/clip-vit-base-patch32"
BASE = f"https://huggingface.co/{REPO}/resolve/main/"


def fetch(rel, dst):
    url = BASE + rel
    print("Hämtar", url)
    req = urllib.request.Request(url, headers={"User-Agent": "dehazeiq-build"})
    with urllib.request.urlopen(req, timeout=300) as r, open(dst, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    print("  ", dst.name, dst.stat().st_size // 1024, "kB")


def first_available(candidates, dst):
    last = None
    for rel in candidates:
        try:
            fetch(rel, dst)
            return rel
        except Exception as e:  # noqa: BLE001
            print("  saknas:", rel, e)
            last = e
    raise SystemExit(f"Kunde inte hämta någon av {candidates}: {last}")


def main():
    import onnxruntime as ort
    from tokenizers import Tokenizer

    OUT.mkdir(parents=True, exist_ok=True)
    tmp = HERE / "_tmp_models"
    tmp.mkdir(exist_ok=True)
    first_available(["onnx/vision_model_quantized.onnx", "onnx/vision_model.onnx"], OUT / "clip_vision.onnx")
    first_available(["onnx/text_model_quantized.onnx", "onnx/text_model.onnx"], tmp / "text.onnx")
    fetch("tokenizer.json", tmp / "tokenizer.json")

    prompts = json.loads((HERE / "ai_prompts.json").read_text("utf-8"))
    tok = Tokenizer.from_file(str(tmp / "tokenizer.json"))
    sess = ort.InferenceSession(str(tmp / "text.onnx"), providers=["CPUExecutionProvider"])
    in_names = [i.name for i in sess.get_inputs()]
    out_names = [o.name for o in sess.get_outputs()]
    print("Textmodell in:", in_names, "ut:", out_names)
    out_name = "text_embeds" if "text_embeds" in out_names else out_names[0]

    def embed(texts):
        vecs = []
        for t in texts:
            ids = tok.encode(t).ids[:77]
            feed = {}
            for n in in_names:
                if "input_ids" in n:
                    feed[n] = np.array([ids], dtype=np.int64)
                elif "attention" in n:
                    feed[n] = np.ones((1, len(ids)), dtype=np.int64)
            v = sess.run([out_name], feed)[0]
            v = v.reshape(v.shape[0], -1)[0] if v.ndim > 2 else v[0]
            vecs.append(v / np.linalg.norm(v))
        return np.stack(vecs).astype(np.float32)

    groups = {}
    groups["labels"] = embed([p for _, p in prompts["labels"]])
    for g, texts in prompts.items():
        if g in ("labels",) or g.startswith("_"):
            continue
        groups[g] = embed(texts)
    np.savez_compressed(OUT / "text_embeds.npz", **groups)
    (OUT / "prompts.json").write_text(json.dumps(prompts, ensure_ascii=False, indent=1), "utf-8")

    # Snabbkontroll av bildmodellen: rätt in- och utdata
    vs = ort.InferenceSession(str(OUT / "clip_vision.onnx"), providers=["CPUExecutionProvider"])
    print("Bildmodell in:", [(i.name, i.shape) for i in vs.get_inputs()],
          "ut:", [(o.name, o.shape) for o in vs.get_outputs()])
    x = np.random.rand(2, 3, 224, 224).astype(np.float32)
    outs = vs.run(None, {vs.get_inputs()[0].name: x})
    print("Utdata-former:", [o.shape for o in outs])
    print("Klart:", sorted(p.name for p in OUT.iterdir()))


if __name__ == "__main__":
    sys.exit(main())
