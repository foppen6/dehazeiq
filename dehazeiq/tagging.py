"""Valfri motivigenkänning med CLIP (open_clip).

Körs bara om torch och open_clip_torch är installerade
(pip install -r requirements-ai.txt). Annars hoppar analysen över taggning
och använder färghistogram för att hitta liknande klipp.
"""

import numpy as np

try:  # pragma: no cover - beror på valfria paket
    import torch
    import open_clip
    AVAILABLE = True
except Exception:  # noqa: BLE001
    AVAILABLE = False

# (svensk etikett, engelsk beskrivning för CLIP)
LABELS = [
    ("Sköldpadda", "a photo of a sea turtle swimming underwater"),
    ("Dykare", "a photo of a scuba diver underwater"),
    ("Rev och koraller", "a photo of a colorful coral reef underwater"),
    ("Fiskstim", "a photo of a large school of fish underwater"),
    ("Haj", "a photo of a shark underwater"),
    ("Rocka", "a photo of a manta ray or stingray underwater"),
    ("Bläckfisk", "a photo of an octopus or squid underwater"),
    ("Manet", "a photo of a jellyfish"),
    ("Muräna", "a photo of a moray eel"),
    ("Nakensnäcka", "a macro photo of a nudibranch sea slug"),
    ("Makro", "an extreme close-up macro photo of a small sea creature"),
    ("Vrak", "a photo of a shipwreck underwater"),
    ("Grotta", "a photo of an underwater cave"),
    ("Kelp och tång", "a photo of a kelp forest or seaweed underwater"),
    ("Blått vatten", "a photo of open blue water with nothing in it"),
    ("Sandbotten", "a photo of a sandy sea floor underwater"),
    ("Ytan underifrån", "a photo of the water surface seen from below with sun rays"),
    ("Båt", "a photo of a boat on the sea"),
    ("Strand", "a photo of a beach"),
    ("Solnedgång", "a photo of a sunset over the sea"),
    ("Berg", "a photo of mountains"),
    ("Stad", "a photo of a city street"),
    ("Människor", "a photo of people smiling"),
    ("Landskap", "a photo of a wide natural landscape"),
]


class Tagger:  # pragma: no cover - kräver valfria paket
    def __init__(self):
        if not AVAILABLE:
            raise RuntimeError("open_clip är inte installerat")
        if torch.backends.mps.is_available():
            self.device = "mps"
        elif torch.cuda.is_available():
            self.device = "cuda"
        else:
            self.device = "cpu"
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            "ViT-B-32", pretrained="laion2b_s34b_b79k", device=self.device)
        self.model.eval()
        tok = open_clip.get_tokenizer("ViT-B-32")
        with torch.no_grad():
            t = self.model.encode_text(tok([p for _, p in LABELS]).to(self.device))
            t = t / t.norm(dim=-1, keepdim=True)
        self.text = t
        self.labels = [l for l, _ in LABELS]

    def embed(self, frames_rgb):
        """frames_rgb: lista med numpy-bilder (H, W, 3, uint8, RGB)."""
        from PIL import Image
        if not frames_rgb:
            return np.zeros((0, 512), np.float32), np.zeros((0, len(self.labels)), np.float32)
        imgs = torch.stack([self.preprocess(Image.fromarray(f)) for f in frames_rgb]).to(self.device)
        with torch.no_grad():
            e = self.model.encode_image(imgs)
            e = e / e.norm(dim=-1, keepdim=True)
            probs = (100.0 * e @ self.text.T).softmax(dim=-1)
        return e.float().cpu().numpy(), probs.float().cpu().numpy()


_TAGGER = None


def get_tagger():
    global _TAGGER
    if not AVAILABLE:
        return None
    if _TAGGER is None:
        try:
            _TAGGER = Tagger()
        except Exception:  # noqa: BLE001
            return None
    return _TAGGER


def summarize_tags(probs: np.ndarray, labels, top=3, min_prob=0.12):
    """Välj klippets taggar utifrån medelsannolikhet över bildrutorna."""
    if probs is None or len(probs) == 0:
        return []
    mean = probs.mean(axis=0)
    peak = probs.max(axis=0)
    order = np.argsort(-mean)
    tags = [labels[i] for i in order[:top] if mean[i] >= min_prob or peak[i] >= 0.5]
    return tags
