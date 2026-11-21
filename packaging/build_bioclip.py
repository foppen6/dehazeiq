"""Bygger artigenkänningen (BioCLIP, MIT-licens) för DeHazeIQ. Körs av GitHub Actions.

BioCLIP är en CLIP-modell (ViT-B/16) tränad på miljontals bilder av organismer med artnamn.
Skriptet exporterar bilddelen till ONNX (kvantiserad till int8, ~90 MB) och räknar fram
textinbäddningar för arterna i packaging/bio_species.json:
    bioclip_vision.onnx, bio_text.npz, bio_species.json  →  packaging/models/
"""

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE / "models"
HF = "hf-hub:imageomics/bioclip"


def prompt(sp):
    _sv, _sv_def, sci, en, _group = sp
    return f"a photo of {sci} with common name {en}."


def main():
    import onnxruntime as ort
    import open_clip
    import torch
    from onnxruntime.quantization import QuantType, quantize_dynamic

    OUT.mkdir(parents=True, exist_ok=True)
    model, _, preprocess = open_clip.create_model_and_transforms(HF)
    tokenizer = open_clip.get_tokenizer(HF)
    model.eval()
    print("Förbehandling:", preprocess)

    class Vision(torch.nn.Module):
        def __init__(self, m):
            super().__init__()
            self.m = m

        def forward(self, x):
            return torch.nn.functional.normalize(self.m.encode_image(x), dim=-1)

    fp32 = HERE / "_bioclip_fp32.onnx"
    kw = dict(input_names=["pixel_values"], output_names=["image_embeds"],
              dynamic_axes={"pixel_values": {0: "batch"}, "image_embeds": {0: "batch"}}, opset_version=17)
    x = torch.randn(2, 3, 224, 224)
    try:
        torch.onnx.export(Vision(model), x, str(fp32), dynamo=False, **kw)
    except TypeError:
        torch.onnx.export(Vision(model), x, str(fp32), **kw)
    out = OUT / "bioclip_vision.onnx"
    quantize_dynamic(str(fp32), str(out), weight_type=QuantType.QUInt8)
    print("Bildmodell:", out.stat().st_size // (1 << 20), "MB")

    # Kontroll: kvantiserad modell ≈ PyTorch
    with torch.no_grad():
        ref = Vision(model)(x).numpy()
    sess = ort.InferenceSession(str(out), providers=["CPUExecutionProvider"])
    got = sess.run(None, {"pixel_values": x.numpy()})[0]
    cos = (ref * got).sum(1) / np.linalg.norm(ref, axis=1) / np.linalg.norm(got, axis=1)
    print("Likhet int8 mot fp32:", np.round(cos, 4))
    if cos.min() < 0.95:
        raise SystemExit("Kvantiseringen förstörde modellen")

    species = json.loads((HERE / "bio_species.json").read_text("utf-8"))["species"]
    with torch.no_grad():
        t = model.encode_text(tokenizer([prompt(s) for s in species]))
        t = torch.nn.functional.normalize(t, dim=-1).numpy().astype(np.float32)
    np.savez_compressed(OUT / "bio_text.npz", species=t)
    (OUT / "bio_species.json").write_text(json.dumps({"species": species}, ensure_ascii=False, indent=1), "utf-8")
    print("Arter:", len(species), "– klart")


if __name__ == "__main__":
    sys.exit(main())
