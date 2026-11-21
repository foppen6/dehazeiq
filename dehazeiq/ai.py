"""Inbyggd bildförståelse med CLIP (ONNX, körs lokalt med onnxruntime).

Ger för varje bild:
  - motiv (svenska etiketter: Sköldpadda, Dykare, Rev …)
  - intresse  0..1  – finns det något sevärt i bilden, eller är det tomt vatten/sand/mörker?
  - skönhet   0..1  – ser bilden ut som en snygg, proffsig bild?
  - inbäddning      – för att hitta liknande klipp och undvika upprepning
och för beskärning: hur tydligt motivet syns i olika utsnitt av bilden.

Modellen (CLIP ViT-B/32, OpenAI, MIT-licens) byggs in i appen av byggsystemet.
Saknas den fungerar DeHazeIQ ändå, med enklare bildanalys.
"""

import json
import os
import sys
import threading
from pathlib import Path

import cv2
import numpy as np

MEAN = np.array([0.48145466, 0.4578275, 0.40821073], np.float32).reshape(1, 3, 1, 1)
STD = np.array([0.26862954, 0.26130258, 0.27577711], np.float32).reshape(1, 3, 1, 1)
SIZE = 224
# Utsnitt för beskärning: smal remsa (ungefär 9:16 ur 16:9) på fem positioner
CROP_CENTERS = (0.2, 0.35, 0.5, 0.65, 0.8)
CROP_WIDTH = 0.34
# Rutnät för att hitta var djuret är: 5 × 3 överlappande utsnitt
GRID_X = (0.2, 0.35, 0.5, 0.65, 0.8)
GRID_Y = (0.3, 0.5, 0.7)
GRID_W, GRID_H = 0.36, 0.55
# Etiketter som är miljöer, inte motiv att centrera
SCENE_LABELS = {"Rev och koraller", "Vrak", "Grotta", "Kelp och tång", "Ytan underifrån", "Båt", "Strand",
                "Solnedgång", "Berg", "Stad", "Landskap"}


def model_dirs():
    dirs = []
    if os.environ.get("DEHAZEIQ_MODELS"):
        dirs.append(Path(os.environ["DEHAZEIQ_MODELS"]))
    base = getattr(sys, "_MEIPASS", None)
    if base:
        dirs.append(Path(base) / "models")
    here = Path(__file__).resolve().parent
    dirs += [here / "models", here.parent / "packaging" / "models"]
    from .config import HOME
    dirs.append(HOME / "models")
    return dirs


class Clip:
    def __init__(self, folder: Path):
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = max(1, (os.cpu_count() or 2) // 2)
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.sess = ort.InferenceSession(str(folder / "clip_vision.onnx"), opts,
                                         providers=["CPUExecutionProvider"])
        self.input = self.sess.get_inputs()[0].name
        outs = [o.name for o in self.sess.get_outputs()]
        self.output = "image_embeds" if "image_embeds" in outs else outs[0]
        with np.load(folder / "text_embeds.npz") as t:
            self.text = {k: t[k].astype(np.float32) for k in t.files}
        prompts = json.loads((folder / "prompts.json").read_text("utf-8"))
        self.labels = [sv for sv, _ in prompts["labels"]]
        self.creature_idx = np.array([i for i, sv in enumerate(self.labels) if sv not in SCENE_LABELS], int)
        self.folder = folder
        self._lock = threading.Lock()

    # ---------- grundfunktioner ----------
    @staticmethod
    def _prep(img_bgr):
        h, w = img_bgr.shape[:2]
        s = SIZE / min(h, w)
        img = cv2.resize(img_bgr, (max(SIZE, round(w * s)), max(SIZE, round(h * s))),
                         interpolation=cv2.INTER_CUBIC if s > 1 else cv2.INTER_AREA)
        h, w = img.shape[:2]
        y, x = (h - SIZE) // 2, (w - SIZE) // 2
        img = img[y:y + SIZE, x:x + SIZE, ::-1]  # BGR → RGB
        return img.transpose(2, 0, 1).astype(np.float32) / 255.0

    def embed(self, images_bgr, batch=16):
        if not images_bgr:
            return np.zeros((0, 512), np.float32)
        out = []
        for i in range(0, len(images_bgr), batch):
            x = np.stack([self._prep(im) for im in images_bgr[i:i + batch]])
            x = (x - MEAN) / STD
            with self._lock:
                e = self.sess.run([self.output], {self.input: x})[0]
            e = e.reshape(e.shape[0], -1)
            out.append(e / np.maximum(np.linalg.norm(e, axis=1, keepdims=True), 1e-6))
        return np.concatenate(out).astype(np.float32)

    @staticmethod
    def _softmax(z):
        z = z - z.max(axis=1, keepdims=True)
        e = np.exp(z)
        return e / e.sum(axis=1, keepdims=True)

    # ---------- tolkning ----------
    def interest(self, emb):
        """Sannolikhet att bilden visar ett motiv (djur, dykare, rev, landskap) snarare än 'inget'."""
        sub, emp = self.text["subject"], self.text["empty"]
        p = self._softmax(100.0 * np.concatenate([emb @ sub.T, emb @ emp.T], axis=1))
        return p[:, : len(sub)].sum(axis=1)

    def beauty(self, emb):
        good, bad = self.text["beautiful"], self.text["ugly"]
        p = self._softmax(100.0 * np.concatenate([emb @ good.T, emb @ bad.T], axis=1))
        return p[:, : len(good)].sum(axis=1)

    def label_probs(self, emb):
        return self._softmax(100.0 * (emb @ self.text["labels"].T))

    def subject_score(self, emb):
        """Råpoäng (inte normaliserad) för hur mycket motiv det finns – används för att jämföra utsnitt."""
        return (emb @ self.text["subject"].T).max(axis=1) - (emb @ self.text["empty"].T).max(axis=1)

    def crop_scores(self, frame_bgr):
        """Motivpoäng för fem vertikala utsnitt (vänster → höger) av en liggande bild."""
        h, w = frame_bgr.shape[:2]
        cw = max(8, int(w * CROP_WIDTH))
        crops = []
        for c in CROP_CENTERS:
            x0 = int(min(max(c * w - cw / 2, 0), w - cw))
            crops.append(frame_bgr[:, x0:x0 + cw])
        return self.subject_score(self.embed(crops))


    def group_prob(self, emb, pos, neg):
        """Sannolikhet för grupp pos mot grupp neg (t.ex. 'funny' mot 'plain'). None om grupperna saknas."""
        if pos not in self.text or neg not in self.text:
            return None
        a, b = self.text[pos], self.text[neg]
        p = self._softmax(100.0 * np.concatenate([emb @ a.T, emb @ b.T], axis=1))
        return p[:, : len(a)].sum(axis=1)

    def locate(self, frame_bgr):
        """Var i bilden är djuret/motivet? Jämför 15 överlappande utsnitt med alla djuretiketter.
        Returnerar (x, y, säkerhet, inbäddning av bästa utsnittet). x, y är 0..1."""
        h, w = frame_bgr.shape[:2]
        cw, ch = max(8, int(w * GRID_W)), max(8, int(h * GRID_H))
        crops, centers = [], []
        for gy in GRID_Y:
            for gx in GRID_X:
                x0 = int(min(max(gx * w - cw / 2, 0), w - cw))
                y0 = int(min(max(gy * h - ch / 2, 0), h - ch))
                crops.append(frame_bgr[y0:y0 + ch, x0:x0 + cw])
                centers.append(((x0 + cw / 2) / w, (y0 + ch / 2) / h))
        e = self.embed(crops)
        lab = self.text["labels"][self.creature_idx] if len(self.creature_idx) else self.text["subject"]
        s = (e @ lab.T).max(axis=1) - (e @ self.text["empty"].T).max(axis=1)
        wgt = np.exp((s - s.max()) * 40.0)
        wgt /= wgt.sum()
        c = (wgt[:, None] * np.asarray(centers, np.float32)).sum(axis=0)
        conf = float(s.max() - np.median(s))
        best = int(np.argmax(s))
        return float(c[0]), float(c[1]), conf, float(s.max()), e[best], crops[best]


class Bio:
    """Artigenkänning med BioCLIP (tränad på miljontals bilder av organismer med artnamn).
    Används på utsnittet där djuret syns."""

    def __init__(self, folder: Path):
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = max(1, (os.cpu_count() or 2) // 2)
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.sess = ort.InferenceSession(str(folder / "bioclip_vision.onnx"), opts,
                                         providers=["CPUExecutionProvider"])
        self.input = self.sess.get_inputs()[0].name
        with np.load(folder / "bio_text.npz") as t:
            self.text = t["species"].astype(np.float32)
        self.species = json.loads((folder / "bio_species.json").read_text("utf-8"))["species"]
        self._lock = threading.Lock()

    def embed(self, images_bgr, batch=16):
        if not images_bgr:
            return np.zeros((0, self.text.shape[1]), np.float32)
        out = []
        for i in range(0, len(images_bgr), batch):
            x = np.stack([Clip._prep(im) for im in images_bgr[i:i + batch]])
            x = (x - MEAN) / STD
            with self._lock:
                e = self.sess.run(None, {self.input: x})[0]
            out.append(e / np.maximum(np.linalg.norm(e, axis=1, keepdims=True), 1e-6))
        return np.concatenate(out).astype(np.float32)

    def probs(self, emb):
        return Clip._softmax(100.0 * np.asarray(emb, np.float32) @ self.text.T)

    def top(self, emb, k=3):
        p = self.probs(np.atleast_2d(emb)).mean(axis=0)
        idx = np.argsort(-p)[:k]
        return [(self.species[i], float(p[i])) for i in idx]


_BIO = None
_BIO_LOCK = threading.Lock()


def get_bio():
    global _BIO
    with _BIO_LOCK:
        if _BIO is None:
            _BIO = False
            for d in model_dirs():
                if (d / "bioclip_vision.onnx").exists() and (d / "bio_text.npz").exists():
                    try:
                        _BIO = Bio(d)
                        print(f"Artigenkänning (BioCLIP) laddad från {d}")
                    except Exception as e:  # noqa: BLE001
                        print("Artigenkänningen kunde inte laddas:", e)
                    break
        return _BIO or None


_MODEL = None
_TRIED = False
_LOCK = threading.Lock()


def get():
    """Returnerar CLIP-modellen eller None om den inte finns/inte går att ladda."""
    global _MODEL, _TRIED
    with _LOCK:
        if _TRIED:
            return _MODEL
        _TRIED = True
        if os.environ.get("DEHAZEIQ_NO_AI"):
            return None
        for d in model_dirs():
            if (d / "clip_vision.onnx").exists() and (d / "text_embeds.npz").exists():
                try:
                    _MODEL = Clip(d)
                    print("AI-modell:", d)
                    break
                except Exception as e:  # noqa: BLE001
                    print("Kunde inte ladda AI-modellen:", e)
        return _MODEL


def available() -> bool:
    return get() is not None


def summarize_tags(probs, labels, top=3, min_prob=0.12):
    if probs is None or len(probs) == 0:
        return []
    mean = probs.mean(axis=0)
    peak = probs.max(axis=0)
    order = np.argsort(-mean)
    return [labels[i] for i in order[:top] if mean[i] >= min_prob or peak[i] >= 0.5]
