"""Texter med effekter: ritas med Pillow till ett genomskinligt lager (en bild per bildruta) som
läggs ovanpå klippet. Ger typsnitt, konturer, rundade rutor, skuggor, glöd och animationer som
FFmpegs drawtext inte klarar: skrivmaskin, ord för ord, pop, glid in, zoom, glitch, överstrykning
och karaoke (ordet som sägs lyser upp).

Lagret byggs per klipp. Bildrutor som ser likadana ut som den förra återanvänds, så en text som
står stilla kostar nästan inget.
"""

import math
import os
import re
import sys
from functools import lru_cache
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    PIL_OK = True
except Exception:  # noqa: BLE001
    PIL_OK = False

ANIMS = {
    "fade": "Tona in",
    "typewriter": "Skrivmaskin",
    "words": "Ord för ord",
    "pop": "Pop",
    "slide_up": "Glid upp",
    "slide_left": "Glid in från sidan",
    "zoom": "Zooma in",
    "glitch": "Glitch",
    "highlight": "Överstrykning",
    "bounce": "Gungar",
    "karaoke": "Karaoke",
}

# Typsnitt: fria (SIL OFL) typsnitt som följer med appen, annars datorns egna
FONTS = {
    "sans": ("Fet", None),
    "impact": ("Anton", "Anton-Regular.ttf"),
    "bebas": ("Bebas Neue", "BebasNeue-Regular.ttf"),
    "black": ("Archivo Black", "ArchivoBlack-Regular.ttf"),
    "marker": ("Tuschpenna", "PermanentMarker-Regular.ttf"),
    "script": ("Skrivstil", "Pacifico-Regular.ttf"),
    "comic": ("Serietidning", "Bangers-Regular.ttf"),
    "serif": ("Elegant", "DMSerifDisplay-Regular.ttf"),
}

# Stilarnas utseende. pos = textblockets mitt (0..1), size = andel av bildens kortsida.
LOOKS = {
    "doc": dict(font="sans", size=0.055, color="#FFFFFF", sub="#D6E4EA", pos=(0.34, 0.8), align="left",
                bar=True, shadow=True, anim="slide_left"),
    "fun": dict(font="sans", size=0.062, color="#111111", box="#FFD84A", radius=0.35, pos=(0.5, 0.2),
                anim="pop"),
    "title": dict(font="sans", size=0.1, color="#FFFFFF", sub="#E6EEF3", pos=(0.5, 0.45), shadow=True,
                  anim="zoom"),
    "caption": dict(font="sans", size=0.05, color="#FFFFFF", box="#000000B0", radius=0.3, pos=(0.5, 0.74),
                    anim="fade"),
    "place": dict(font="bebas", size=0.085, color="#FFFFFF", sub="#9FE7F0", pos=(0.3, 0.13), align="left",
                  upper=True, shadow=True, anim="slide_up"),
    "meme": dict(font="impact", size=0.085, color="#FFFFFF", stroke="#000000", pos=(0.5, 0.17), upper=True,
                 anim="pop"),
    "minimal": dict(font="sans", size=0.04, color="#FFFFFFE6", pos=(0.5, 0.76), anim="fade"),
    "chapter": dict(font="serif", size=0.075, color="#FFFFFF", sub="#CFE3EA", pos=(0.5, 0.45), lines=True,
                    shadow=True, anim="fade"),
    # sociala medier
    "tiktok": dict(font="sans", size=0.058, color="#111111", box="#FFFFFF", radius=0.3, per_line=True,
                   pos=(0.5, 0.3), anim="pop"),
    "hook": dict(font="bebas", size=0.12, color="#FFFFFF", accent="#FFE14D", stroke="#000000", upper=True,
                 pos=(0.5, 0.3), anim="words"),
    "pov": dict(font="black", size=0.058, color="#FFFFFF", stroke="#000000", pos=(0.5, 0.2), anim="typewriter"),
    "highlight": dict(font="black", size=0.062, color="#111111", marker="#FFE14D", pos=(0.5, 0.62),
                      anim="highlight"),
    "neon": dict(font="marker", size=0.075, color="#FFFFFF", glow="#2EE6FF", pos=(0.5, 0.35), anim="glitch"),
    "number": dict(font="impact", size=0.2, color="#FFE14D", stroke="#000000", sub="#FFFFFF", pos=(0.5, 0.3),
                   anim="pop"),
    "quote": dict(font="serif", size=0.068, color="#FFFFFF", sub="#CFE3EA", shadow=True, pos=(0.5, 0.5),
                  anim="fade"),
    "speech": dict(font="sans", size=0.048, color="#FFF6D5", accent="#FFE14D", box="#0000008C", radius=0.25,
                   pos=(0.5, 0.86), anim="fade"),
}

# Var plattformarnas knappar och texter ligger (andel av bilden): text hamnar inte där
SAFE = {"9:16": (0.12, 0.79, 0.06, 0.86), "4:5": (0.07, 0.86, 0.05, 0.95), "1:1": (0.06, 0.9, 0.05, 0.95)}

_ROOT = Path(__file__).resolve().parent


def font_dirs():
    out = []
    base = getattr(sys, "_MEIPASS", None)
    if base:
        out.append(Path(base) / "fonts")
    out += [_ROOT.parent / "packaging" / "fonts", _ROOT / "fonts"]
    return out


@lru_cache(maxsize=None)
def font_path(key):
    from .effects import title_font
    name = (FONTS.get(key) or FONTS["sans"])[1]
    if name:
        for d in font_dirs():
            if (d / name).is_file():
                return str(d / name)
    p = title_font()
    return str(p) if p else None


def fonts_available():
    return {k: v[0] for k, v in FONTS.items() if k == "sans" or font_path(k) != font_path("sans")}


@lru_cache(maxsize=256)
def _font(path, size):
    try:
        return ImageFont.truetype(path, size) if path else ImageFont.load_default(size)
    except Exception:  # noqa: BLE001
        return ImageFont.load_default()


def _rgba(c, default=(255, 255, 255, 255)):
    if not c:
        return default
    c = str(c).lstrip("#")
    if c.startswith("0x"):
        c = c[2:]
    try:
        if len(c) == 6:
            return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4)) + (255,)
        if len(c) == 8:
            return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4, 6))
    except ValueError:
        pass
    return default


def _ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def _back(x):
    x = max(0.0, min(1.0, x))
    c1 = 1.9
    return 1 + (c1 + 1) * (x - 1) ** 3 + c1 * (x - 1) ** 2


EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]+")


@lru_cache(maxsize=1)
def _emoji_font():
    cands = {"darwin": ["/System/Library/Fonts/Apple Color Emoji.ttc"],
             "win32": [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "seguiemj.ttf")]}
    cands = cands.get(sys.platform, []) + ["/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
                                          "/usr/share/fonts/noto/NotoColorEmoji.ttf"]
    for p in cands:
        if os.path.isfile(p):
            for sz in (160, 137, 109, 96, 64):  # färgemojier finns bara i vissa storlekar
                try:
                    return ImageFont.truetype(p, sz), sz
                except OSError:
                    continue
    return None


def look_of(item):
    lk = dict(LOOKS.get(item.get("style") or "caption", LOOKS["caption"]))
    for k in ("color", "box", "font", "stroke", "accent"):
        if item.get(k):
            lk[k] = item[k]
    if item.get("box") == "none":
        lk.pop("box", None)
    return lk


class Block:
    """En text färdig att rita: radbrytning och mått beräknas en gång."""

    def __init__(self, item, W, H):
        self.item, self.W, self.H = item, W, H
        lk = self.look = look_of(item)
        m = min(W, H)
        scale = float(item.get("size") or 1.0)
        self.fs = max(10, int(m * lk["size"] * scale))
        self.font = _font(font_path(lk["font"]), self.fs)
        self.sfs = max(9, int(self.fs * 0.55))
        self.sfont = _font(font_path("sans" if lk["font"] in ("impact", "bebas", "comic") else lk["font"]), self.sfs)
        text = str(item.get("text") or "")
        sub = str(item.get("sub") or "")
        if lk.get("upper"):
            text = text.upper()
        self.pad = int(self.fs * (0.45 if lk.get("box") or lk.get("marker") else 0.25)) + int(self.fs * 0.12)
        maxw = W * (0.78 if lk.get("align") != "left" else 0.7) - 2 * self.pad  # ryms inom säker zon
        self.lines = self._wrap(text, self.font, maxw)
        # ett långt ord eller för många rader: krymp texten tills den ryms
        for _ in range(6):
            widest = max(self._measure(x, self.font) for x in self.lines)
            tall = len(self.lines) * self.fs * 1.18 > H * 0.5
            if widest <= maxw * 1.001 and not tall:
                break
            k = min(maxw / max(1.0, widest), 0.85 if tall else 1.0)
            self.fs = max(10, int(self.fs * min(0.95, k)))
            self.font = _font(font_path(lk["font"]), self.fs)
            self.sfs = max(9, min(self.sfs, int(self.fs * 0.8)))
            self.sfont = _font(font_path("sans" if lk["font"] in ("impact", "bebas", "comic") else lk["font"]), self.sfs)
            self.pad = int(self.fs * (0.45 if lk.get("box") or lk.get("marker") else 0.25)) + int(self.fs * 0.12)
            self.lines = self._wrap(text, self.font, maxw)
        self.sublines = self._wrap(sub, self.sfont, maxw) if sub else []
        self.lh = int(self.fs * 1.18)
        self.slh = int(self.sfs * 1.25)
        self.words = [w for ln in self.lines for w in ln.split(" ") if w]

    def _measure(self, s, font):
        if not s:
            return 0
        n = len(EMOJI.findall(s))
        return font.getlength(EMOJI.sub("", s)) + n * font.size * 1.15

    def _wrap(self, text, font, maxw):
        out = []
        for para in text.split("\n"):
            cur = ""
            for w in para.split(" "):
                t = (cur + " " + w).strip()
                if cur and self._measure(t, font) > maxw:
                    out.append(cur)
                    cur = w
                else:
                    cur = t
            out.append(cur)
        return [x for x in out if x.strip()] or [""]

    def size(self):
        tw = max([self._measure(x, self.font) for x in self.lines] + [self._measure(x, self.sfont) for x in self.sublines])
        th = self.lh * len(self.lines) + (self.slh * len(self.sublines) + int(self.fs * 0.15) if self.sublines else 0)
        return int(tw) + 2 * self.pad, int(th) + 2 * self.pad

    def render(self, chars=None, words=None, hi=None, mark=1.0):
        """Textblocket som bild. chars: antal synliga tecken (skrivmaskin); words: antal synliga ord;
        hi: index för ordet som lyser (karaoke/krok); mark: hur långt överstrykningen har kommit."""
        lk = self.look
        bw, bh = self.size()
        im = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        color, accent = _rgba(lk["color"]), _rgba(lk.get("accent"), _rgba("#FFE14D"))
        stroke = _rgba(lk["stroke"]) if lk.get("stroke") else None
        sw = max(2, self.fs // 11) if stroke else 0
        left = lk.get("align") == "left"
        if lk.get("box") and not lk.get("per_line"):
            r = int(self.fs * lk.get("radius", 0.3))
            d.rounded_rectangle((0, 0, bw - 1, bh - 1), r, fill=_rgba(lk["box"]))
        y = self.pad
        shown_c, shown_w, wi = 0, 0, 0
        line_boxes = []
        for ln in self.lines:
            lw = self._measure(ln, self.font)
            x = self.pad if left else (bw - lw) / 2
            line_boxes.append((x, y, lw))
            if lk.get("per_line") and lk.get("box"):
                p = int(self.fs * 0.22)
                d.rounded_rectangle((x - p, y - p * 0.6, x + lw + p, y + self.lh - p * 0.2),
                                    int(self.fs * lk.get("radius", 0.3)), fill=_rgba(lk["box"]))
            if lk.get("marker"):
                mw = lw * max(0.0, min(1.0, mark))
                if mw > 1:
                    d.rounded_rectangle((x - self.fs * 0.15, y + self.lh * 0.12, x + mw + self.fs * 0.15, y + self.lh * 0.98),
                                        int(self.fs * 0.12), fill=_rgba(lk["marker"]))
            cx = x
            for k, w in enumerate(ln.split(" ")):
                if not w:
                    continue
                seg = w if k == 0 else " " + w
                if words is not None and wi >= words:
                    break
                txt = seg
                if chars is not None:
                    left_c = chars - shown_c
                    if left_c <= 0:
                        break
                    txt = seg[:left_c]
                col = accent if (hi is not None and wi == hi) else color
                self._draw_text(im, d, cx, y, txt, self.font, col, stroke, sw)
                cx += self._measure(seg, self.font)
                shown_c += len(seg)
                wi += 1
                shown_w += 1
            y += self.lh
        if self.sublines and (chars is None or shown_c >= sum(len(x) for x in self.lines)):
            y += int(self.fs * 0.15)
            for ln in self.sublines:
                lw = self._measure(ln, self.sfont)
                x = self.pad if left else (bw - lw) / 2
                self._draw_text(im, d, x, y, ln, self.sfont, _rgba(lk.get("sub"), color), stroke, max(1, sw // 2))
                y += self.slh
        if lk.get("bar") and line_boxes:  # namnskylt: tunn linje till vänster
            x0 = max(0, self.pad - int(self.fs * 0.35))
            d.rectangle((x0, self.pad, x0 + max(3, self.fs // 9), y), fill=_rgba("#FFFFFFE6"))
        if lk.get("lines") and line_boxes:  # kapitel: linjer över och under
            lw = max(b[2] for b in line_boxes)
            x0 = (bw - lw) / 2
            for yy in (2, bh - 4):
                d.rectangle((x0, yy, x0 + lw, yy + max(2, self.fs // 18)), fill=_rgba("#FFFFFFCC"))
        if lk.get("shadow") or lk.get("glow"):
            im = self._halo(im, lk)
        return im

    def _draw_text(self, im, d, x, y, s, font, col, stroke, sw):
        parts = re.split(f"({EMOJI.pattern})", s) if EMOJI.search(s) else [s]
        for part in parts:
            if not part:
                continue
            if EMOJI.fullmatch(part):
                x += self._emoji(im, x, y, part, font)
                continue
            kw = dict(font=font, fill=col)
            if stroke:
                kw.update(stroke_width=sw, stroke_fill=stroke)
            d.text((x, y), part, **kw)
            x += font.getlength(part)

    def _emoji(self, im, x, y, s, font):
        size = int(font.size * 1.05)
        ef = _emoji_font()
        if not ef:
            return font.size * 1.15
        f, base = ef
        try:
            tile = Image.new("RGBA", (int(base * 1.3 * len(s)), int(base * 1.3)), (0, 0, 0, 0))
            ImageDraw.Draw(tile).text((0, 0), s, font=f, embedded_color=True)
            bb = tile.getbbox()
            if not bb:
                return font.size * 1.15
            tile = tile.crop(bb)
            w = max(1, int(tile.width * size / tile.height))
            tile = tile.resize((w, size), Image.LANCZOS)
            adv = font.size * 1.15
            _paste(im, tile, int(x + (adv - w) / 2), int(y + font.size * 0.08))
            return adv
        except Exception:  # noqa: BLE001
            return font.size * 1.15

    def _halo(self, im, lk):
        a = im.getchannel("A")
        if lk.get("glow"):
            g = Image.new("RGBA", im.size, _rgba(lk["glow"])[:3] + (0,))
            g.putalpha(a.filter(ImageFilter.GaussianBlur(self.fs * 0.18)).point(lambda v: min(255, v * 2)))
            g.alpha_composite(im)
            return g
        sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
        sh.putalpha(a.filter(ImageFilter.GaussianBlur(max(2, self.fs // 14))).point(lambda v: int(v * 0.7)))
        out = Image.new("RGBA", im.size, (0, 0, 0, 0))
        off = max(2, self.fs // 22)
        out.alpha_composite(sh, (off, off))
        out.alpha_composite(im)
        return out


def _anim_state(item, t, dur, block):
    """Hur texten ser ut vid tiden t (sekunder sedan den började). Returnerar ett hashbart tillstånd."""
    anim = item.get("anim") or block.look.get("anim") or "fade"
    left = dur - t
    alpha = min(1.0, t / 0.22, max(0.0, left) / 0.2)
    dx = dy = 0
    scale = 1.0
    chars = words = hi = None
    mark = 1.0
    glitch = 0
    W, H = block.W, block.H
    if anim == "pop":
        scale = 0.35 + 0.65 * _back(t / 0.38)
        alpha = min(1.0, t / 0.12, max(0.0, left) / 0.18)
    elif anim == "slide_up":
        dy = int((1 - _ease(t / 0.45)) * H * 0.06)
    elif anim == "slide_left":
        dx = int((1 - _ease(t / 0.5)) * W * 0.35)
        alpha = min(1.0, t / 0.3, max(0.0, left) / 0.2)
    elif anim == "zoom":
        scale = 1.0 + 0.6 * (1 - _ease(t / 0.55))
        alpha = min(1.0, t / 0.35, max(0.0, left) / 0.25)
    elif anim == "typewriter":
        n = sum(len(x) for x in block.lines)
        speed = max(14.0, n / min(1.4, dur * 0.5))
        chars = min(n, int(t * speed) + 1)
        alpha = min(1.0, max(0.0, left) / 0.2)
    elif anim == "words":
        n = len(block.words)
        step = min(0.32, dur * 0.55 / max(1, n))
        words = min(n, int(t / step) + 1)
        scale = 1.0 + 0.06 * max(0.0, 1 - (t - (words - 1) * step) / 0.15) if words < n else 1.0
        hi = words - 1 if block.look.get("accent") and words <= n else None
        alpha = min(1.0, max(0.0, left) / 0.2)
    elif anim == "karaoke":
        n = len(block.words)
        hi = min(n - 1, int(t / max(0.01, dur / max(1, n))))
    elif anim == "highlight":
        mark = _ease((t - 0.1) / 0.5)
    elif anim == "glitch":
        k = int(t * 30)
        if t < 0.45 or (k % 41) in (0, 1):
            glitch = 1 + (k * 7919) % 5
    elif anim == "bounce":
        dy = int(math.sin(t * 2 * math.pi * 0.9) * H * 0.006)
    return (round(alpha, 2), dx, dy, round(scale, 3), chars, words, hi, round(mark, 2), glitch)


def place(item, block, W, H, fmt=None):
    """Textblockets mittpunkt i pixlar, inom plattformens säkra zon."""
    x, y = item.get("x"), item.get("y")
    lx, ly = block.look["pos"]
    x = lx if x is None else float(x)
    y = ly if y is None else float(y)
    bw, bh = block.size()
    if block.look.get("align") == "left" and item.get("x") is None:
        x = 0.07 + bw / 2 / W
    if fmt in SAFE and item.get("safe", True):
        top, bot, lft, rgt = SAFE[fmt]
        y = (top + bot) / 2 if bh / H > bot - top else min(max(y, top + bh / 2 / H), bot - bh / 2 / H)
        x = (lft + rgt) / 2 if bw / W > rgt - lft else min(max(x, lft + bw / 2 / W), rgt - bw / 2 / W)
    x = 0.5 if bw > W else min(max(x, bw / 2 / W), 1 - bw / 2 / W)  # aldrig utanför bilden
    return int(x * W), int(y * H)


def frame_state(cues, t, W, H):
    st = []
    for k, c in enumerate(cues):
        if c["start"] <= t < c["end"]:
            st.append((k, _anim_state(c["item"], t - c["start"], c["end"] - c["start"], c["block"])))
    return tuple(st)


def layer(cues, W, H, dur, fps, outdir, fmt=None):
    """Ritar texternas lager för ett klipp som PNG-bilder (en per bildruta).
    cues: [{"start", "end", "item"}] i klippets tid. Returnerar mönstret för FFmpeg eller None."""
    if not PIL_OK or not cues:
        return None
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    cues = [dict(c, block=Block(c["item"], W, H)) for c in cues if c["end"] > 0 and c["start"] < dur]
    if not cues:
        return None
    for c in cues:
        c["center"] = place(c["item"], c["block"], W, H, fmt)
    n = int(math.ceil(dur * fps)) + 2
    sprites, prev_key, prev_bytes = {}, None, None
    blank = None
    import io
    for f in range(n):
        t = f / fps
        key = frame_state(cues, t, W, H)
        if key == prev_key:
            data = prev_bytes
        elif not key:
            if blank is None:
                b = io.BytesIO()
                Image.new("RGBA", (W, H), (0, 0, 0, 0)).save(b, "PNG", compress_level=1)
                blank = b.getvalue()
            data = blank
        else:
            canvas = _compose(cues, key, sprites, W, H)
            b = io.BytesIO()
            canvas.save(b, "PNG", compress_level=1)
            data = b.getvalue()
        (outdir / f"f{f:05d}.png").write_bytes(data)
        prev_key, prev_bytes = key, data
    return str(outdir / "f%05d.png")


def _compose(cues, key, sprites, W, H):
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for k, (alpha, dx, dy, scale, chars, words, hi, mark, glitch) in key:
        c = cues[k]
        sk = (k, chars, words, hi, mark)
        spr = sprites.get(sk)
        if spr is None:
            spr = sprites[sk] = c["block"].render(chars, words, hi, mark)
        im = spr
        if abs(scale - 1.0) > 1e-3:
            im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.BILINEAR)
        if alpha < 0.999:
            a = im.getchannel("A").point(lambda v, al=alpha: int(v * al))
            im = im.copy()
            im.putalpha(a)
        cx, cy = c["center"]
        x0, y0 = int(cx - im.width / 2 + dx), int(cy - im.height / 2 + dy)
        if glitch:
            off = max(3, c["block"].fs // 10) * (1 if glitch % 2 else -1)
            r, g, b, a = im.split()
            zero = Image.new("L", im.size, 0)
            red = Image.merge("RGBA", (r, zero, zero, a.point(lambda v: int(v * 0.7))))
            cyan = Image.merge("RGBA", (zero, g, b, a.point(lambda v: int(v * 0.7))))
            _paste(canvas, red, x0 + off, y0)
            _paste(canvas, cyan, x0 - off, y0 + off // 2)
            if glitch in (2, 4):
                x0 += off // 2
        _paste(canvas, im, x0, y0)
    return canvas


def frame_image(cues, t, W, H, fmt=None, settled=False):
    """Texterna vid tiden t som en genomskinlig bild (för stillbilden i redigeringen).
    settled: visa texterna färdiga (utan inanimering) så att man ser hur de blir."""
    if not PIL_OK:
        return None
    cues = [dict(c, block=Block(c["item"], W, H)) for c in cues]
    for c in cues:
        c["center"] = place(c["item"], c["block"], W, H, fmt)
    if settled:
        key = tuple((k, (1.0, 0, 0, 1.0, None, None, None, 1.0, 0)) for k, c in enumerate(cues)
                    if c["start"] - 0.01 <= t < c["end"])
    else:
        key = frame_state(cues, t, W, H)
    return _compose(cues, key, {}, W, H) if key else None


def _paste(canvas, im, x, y):
    """alpha_composite som tål att bilden hamnar delvis utanför."""
    W, H = canvas.size
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + im.width), min(H, y + im.height)
    if x1 <= x0 or y1 <= y0:
        return
    canvas.alpha_composite(im.crop((x0 - x, y0 - y, x1 - x, y1 - y)), (x0, y0))


def preview_png(item, fmt_w, fmt_h, t=None):
    """En bild av texten (för knappar i redigeringen): PNG-bytes."""
    import io
    b = Block(item, fmt_w, fmt_h)
    im = b.render()
    out = io.BytesIO()
    im.save(out, "PNG")
    return out.getvalue()
