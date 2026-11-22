"""CLIP:s textdel i appen: sök i materialet med egna ord.

Tokeniseraren är skriven i ren Python (samma regler som Hugging Face-filen tokenizer.json:
NFC, gemener, CLIP-regex, byte-nivå och BPE med </w>), så att inga extra paket behövs.

Svenska sökord översätts först med en liten ordlista till engelska (CLIP förstår engelska
bäst). Ord som inte finns i ordlistan skickas som de är; på Mac kan Qwen översätta resten.
"""

import json
import re
import threading
import unicodedata
from functools import lru_cache

import numpy as np

from . import ai

_PAT = re.compile(r"<\|startoftext\|>|<\|endoftext\|>|'s|'t|'re|'ve|'m|'ll|'d|[^\W\d_]+|\d|(?:[^\s\w]|_)+",
                  re.IGNORECASE)


def _bytes_to_unicode():
    bs = list(range(ord("!"), ord("~") + 1)) + list(range(ord("¡"), ord("¬") + 1)) + list(range(ord("®"), ord("ÿ") + 1))
    cs = bs[:]
    n = 0
    for b in range(256):
        if b not in bs:
            bs.append(b)
            cs.append(256 + n)
            n += 1
    return dict(zip(bs, map(chr, cs)))


class Tokenizer:
    def __init__(self, path):
        data = json.loads(open(path, encoding="utf-8").read())
        m = data["model"]
        self.vocab = m["vocab"]
        merges = [tuple(x.split(" ")) if isinstance(x, str) else tuple(x) for x in m["merges"]]
        self.ranks = {p: i for i, p in enumerate(merges)}
        self.suffix = m.get("end_of_word_suffix") or "</w>"
        self.byte_enc = _bytes_to_unicode()
        self.bos = self.vocab.get("<|startoftext|>", 49406)
        self.eos = self.vocab.get("<|endoftext|>", 49407)
        self.cache = {}

    def _bpe(self, token):
        if token in self.cache:
            return self.cache[token]
        word = list(token[:-1]) + [token[-1] + self.suffix]
        while len(word) > 1:
            pairs = [(self.ranks.get((word[i], word[i + 1]), 1 << 30), i) for i in range(len(word) - 1)]
            rank, j = min(pairs)
            if rank == 1 << 30:
                break
            a, b = word[j], word[j + 1]
            out, i = [], 0
            while i < len(word):
                if i < len(word) - 1 and word[i] == a and word[i + 1] == b:
                    out.append(a + b)
                    i += 2
                else:
                    out.append(word[i])
                    i += 1
            word = out
        self.cache[token] = word
        return word

    def encode(self, text, max_len=77):
        text = unicodedata.normalize("NFC", text)
        text = re.sub(r"\s+", " ", text).lower()
        ids = [self.bos]
        for piece in _PAT.findall(text):
            enc = "".join(self.byte_enc[b] for b in piece.encode("utf-8"))
            for t in self._bpe(enc):
                ids.append(self.vocab.get(t, self.eos))
        ids = ids[:max_len - 1] + [self.eos]
        return ids


# Vanliga svenska sökord → engelska (CLIP är tränad på engelska bildtexter)
SV_EN = {
    "bläckfisk": "octopus", "bläckfiskar": "octopus", "sepia": "cuttlefish", "bläckfisken": "octopus",
    "fisk": "fish", "fiskar": "fish", "fiskstim": "school of fish", "stim": "school of fish",
    "haj": "shark", "hajar": "sharks", "rocka": "ray", "manta": "manta ray", "sköldpadda": "sea turtle",
    "sköldpaddor": "sea turtles", "säl": "seal", "delfin": "dolphin", "delfiner": "dolphins", "val": "whale",
    "krabba": "crab", "krabbor": "crabs", "räka": "shrimp", "räkor": "shrimp", "hummer": "lobster",
    "snäcka": "sea snail", "nakensnäcka": "nudibranch", "nakensnäckor": "nudibranchs", "sjöstjärna": "starfish",
    "sjöborre": "sea urchin", "manet": "jellyfish", "maneter": "jellyfish", "ål": "eel", "muräna": "moray eel",
    "sjöhäst": "seahorse", "korall": "coral", "koraller": "coral reef", "rev": "reef", "korallrev": "coral reef",
    "anemon": "sea anemone", "clownfisk": "clownfish", "tång": "seaweed", "kelp": "kelp forest",
    "sand": "sandy seabed", "botten": "seabed", "sandbotten": "sandy seabed", "vrak": "shipwreck",
    "grotta": "cave", "dykare": "scuba diver", "dykaren": "scuba diver", "dykning": "scuba diving",
    "snorkling": "snorkeling", "bubblor": "air bubbles", "lampa": "dive light", "ficklampa": "dive torch",
    "båt": "boat", "båten": "boat", "båtdäck": "boat deck", "däck": "deck", "strand": "beach",
    "stranden": "beach", "hav": "sea", "havet": "ocean", "vågor": "waves", "solnedgång": "sunset",
    "soluppgång": "sunrise", "sol": "sun", "himmel": "sky", "moln": "clouds", "berg": "mountains",
    "skog": "forest", "palm": "palm tree", "palmer": "palm trees", "stad": "city", "gata": "street",
    "marknad": "market", "mat": "food", "middag": "dinner", "frukost": "breakfast", "hotell": "hotel",
    "pool": "swimming pool", "flygplan": "airplane", "flygplats": "airport", "bil": "car",
    "människa": "person", "människor": "people", "person": "person", "folk": "people", "barn": "child",
    "ansikte": "face", "leende": "smiling", "skratt": "laughing", "vänner": "friends", "grupp": "group of people",
    "selfie": "selfie", "hund": "dog", "katt": "cat", "fågel": "bird", "fåglar": "birds",
    "natt": "night", "nattdyk": "night dive", "mörker": "darkness", "ljus": "light", "blå": "blue",
    "blått": "blue water", "grön": "green", "röd": "red", "gul": "yellow", "orange": "orange",
    "lila": "purple", "svart": "black", "vit": "white", "närbild": "close-up", "makro": "macro close-up",
    "översikt": "wide shot", "kamera": "camera", "utrustning": "diving equipment", "logga": "logo",
    "bakom": "behind", "kulisserna": "the scenes", "inspelning": "film set", "studio": "studio",
    "kontor": "office", "möte": "meeting", "produkt": "product", "skylt": "sign", "text": "text",
    "simmar": "swimming", "äter": "eating", "gömmer": "hiding", "jagar": "hunting", "springer": "running",
    "dansar": "dancing", "hoppar": "jumping", "och": "and", "på": "on", "i": "in", "med": "with",
    "under": "under", "vid": "at", "en": "a", "ett": "a", "som": "that", "vattnet": "water", "vatten": "water",
    "undervatten": "underwater", "liten": "small", "stor": "big", "små": "small", "stora": "big",
}


def to_english(text):
    words = re.findall(r"[\wåäöÅÄÖéü-]+", text.lower())
    if not words:
        return text
    out = [SV_EN.get(w, w) for w in words]
    return " ".join(out)


class TextEncoder:
    def __init__(self, model_path, tok_path):
        import onnxruntime as ort
        self.tok = Tokenizer(tok_path)
        self.sess = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
        self.inputs = [i.name for i in self.sess.get_inputs()]
        outs = [o.name for o in self.sess.get_outputs()]
        self.out = "text_embeds" if "text_embeds" in outs else outs[0]

    @lru_cache(maxsize=256)
    def embed(self, text):
        ids = self.tok.encode(text)
        feed = {}
        for n in self.inputs:
            if "input_ids" in n:
                feed[n] = np.array([ids], dtype=np.int64)
            elif "attention" in n:
                feed[n] = np.ones((1, len(ids)), dtype=np.int64)
        v = self.sess.run([self.out], feed)[0]
        v = v.reshape(v.shape[0], -1)[0] if v.ndim > 2 else v[0]
        return (v / (np.linalg.norm(v) + 1e-9)).astype(np.float32)

    def query(self, text):
        """Inbäddning för ett sökord: engelsk översättning + fotofras, medelvärde."""
        en = to_english(text)
        vs = [self.embed(f"a photo of {en}"), self.embed(en)]
        v = np.mean(vs, axis=0)
        return v / (np.linalg.norm(v) + 1e-9)


_enc = None
_lock = threading.Lock()


def get():
    """Textkodaren, eller None om modellfilerna saknas."""
    global _enc
    with _lock:
        if _enc is None:
            _enc = False
            for d in ai.model_dirs():
                if (d / "clip_text.onnx").exists() and (d / "clip_tokenizer.json").exists():
                    try:
                        _enc = TextEncoder(d / "clip_text.onnx", d / "clip_tokenizer.json")
                    except Exception as exc:  # noqa: BLE001
                        print("Textsökning kunde inte laddas:", exc)
                    break
        return _enc or None


def available():
    return get() is not None
