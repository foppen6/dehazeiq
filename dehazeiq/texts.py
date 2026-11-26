"""Fria texter i filmen: lägg till hur många som helst, i olika stilar, och låt AI föreslå.

En text hör till ett klipp (shot_uid) och startar en bit in i det (offset) och syns i dur sekunder
– den följer alltså med när klipp flyttas, och tas bort om klippet tas bort.

Textstilar: dokumentär (namnskylt), humor (pratbubbla), rubrik, undertext, plats (reseskylt),
meme, minimal och kapitel. AI föreslår texter i en ton: dokumentär, humor, reseberättare, poetisk
eller kort och käck – med Qwen när djupanalysen finns (Mac), annars med inbyggda mallar.
"""

import json
import random
import re
import uuid

TEXT_STYLES = {
    "doc": "Dokumentär – namnskylt",
    "fun": "Humor – pratbubbla",
    "title": "Rubrik",
    "caption": "Undertext",
    "place": "Plats – reseskylt",
    "meme": "Meme",
    "minimal": "Minimal",
    "chapter": "Kapitel",
    "tiktok": "TikTok – vit ruta",
    "hook": "Krok – stor och fet",
    "pov": "POV",
    "highlight": "Överstruken",
    "neon": "Neon",
    "number": "Nummer (topplista)",
    "quote": "Citat",
}
ANIM_KEYS = ("fade", "typewriter", "words", "pop", "slide_up", "slide_left", "zoom", "glitch", "highlight",
             "bounce", "karaoke")
FONT_KEYS = ("sans", "impact", "bebas", "black", "marker", "script", "comic", "serif")
TONES = {
    "doc": "Dokumentär",
    "fun": "Humor",
    "travel": "Reseberättare",
    "poetic": "Poetisk",
    "short": "Kort och käck",
    "social": "Sociala medier – krok och POV",
}
TONE_STYLE = {"doc": "doc", "fun": "fun", "travel": "place", "poetic": "caption", "short": "meme", "social": "tiktok"}
HOOKS = ["Vänta tills slutet", "Det här hade jag inte väntat mig", "Ingen tror mig när jag berättar",
         "Därför dyker jag", "Kolla vad som gömmer sig här"]


def ensure_uids(prop):
    for s in prop.get("shots", []):
        if not s.get("uid"):
            s["uid"] = uuid.uuid4().hex[:8]
    return prop


def new_item(shot_uid, text, style="caption", sub="", offset=0.3, dur=2.6, **extra):
    it = {"id": uuid.uuid4().hex[:8], "shot_uid": shot_uid, "text": str(text).strip()[:160],
          "sub": str(sub or "").strip()[:120], "style": style if style in TEXT_STYLES else "caption",
          "offset": max(0.0, float(offset)), "dur": max(0.6, min(15.0, float(dur)))}
    clean_look(it, extra)
    return it


def clean_look(it, args):
    """Utseende och animation för en text: anim, x, y (0..1, None = stilens plats), size, color, font, box."""
    if "anim" in args:
        a = args.get("anim")
        if a in ANIM_KEYS:
            it["anim"] = a
        else:
            it.pop("anim", None)  # stilens egen
    for k in ("x", "y"):
        if k in args:
            if args[k] is None or args[k] == "":
                it.pop(k, None)
            else:
                it[k] = round(max(0.0, min(1.0, float(args[k]))), 3)
    if "size" in args and args["size"] is not None:
        it["size"] = round(max(0.4, min(2.5, float(args["size"]))), 2)
    if "font" in args:
        if args["font"] in FONT_KEYS:
            it["font"] = args["font"]
        else:
            it.pop("font", None)
    for k in ("color", "box"):
        if k in args:
            v = str(args[k] or "").strip()
            if v == "none" and k == "box":
                it[k] = "none"
            elif re.fullmatch(r"#?[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?", v):
                it[k] = "#" + v.lstrip("#")
            else:
                it.pop(k, None)
    return it


AUTO_STYLE = {"label": "doc", "chapter": "chapter", "pop": "fun"}


def materialize(prop):
    """Gör om de automatiska klipptexterna (artnamn, kapitel, pratbubblor) till vanliga texter som
    går att ändra, flytta, ge effekter och ta bort som alla andra. Returnerar antal omgjorda."""
    ensure_uids(prop)
    ov = prop.setdefault("overlays", [])
    n = 0
    for s in prop.get("shots", []):
        t = s.pop("text", None)
        if not t or not t.get("text"):
            continue
        kind = t.get("kind", "label")
        d = float(s.get("duration", 3.0))
        if kind == "pop":
            off, dur = max(0.0, d - 1.7), 1.6
        elif kind == "chapter":
            off, dur = 0.2, min(2.6, max(1.0, d - 0.3))
        else:
            off, dur = 0.4, min(3.6, max(1.0, d - 0.5))
        it = new_item(s["uid"], t["text"], AUTO_STYLE.get(kind, "doc"), t.get("sub", ""), off, dur)
        it["auto"] = kind
        ov.append(it)
        n += 1
    return n


def timeline(prop):
    """Texterna med absoluta tider i filmen: [(start, slut, item)]."""
    by = {s.get("uid"): s for s in prop.get("shots", [])}
    out = []
    for it in prop.get("overlays") or []:
        s = by.get(it.get("shot_uid"))
        if not s or not it.get("text"):
            continue
        a = float(s.get("at", 0)) + float(it.get("offset", 0))
        out.append((a, a + float(it.get("dur", 2.5)), it))
    return sorted(out, key=lambda x: x[0])


# ---------- AI-förslag ----------

FUN = {
    "Bläckfisk": ["Smygläge: på", "Ser du mig? Trodde inte det", "Åtta armar, noll stress", "Jag var här först"],
    "Sepia": ["Färgbyte på två sekunder", "Ingen fara, bara jag", "Kamouflage-mästare"],
    "Krabba": ["Sidledes är också framåt", "Klipp-klipp!", "Det här är MIN sten"],
    "Fisk": ["Fortsätt simma", "Någon som sett min familj?", "Bara förbi"],
    "Hummer": ["Ser stor ut, är snäll", "Klor redo"],
    "Haj": ["Lugn, jag är vegetarian", "Vem bjöd in dykarna?"],
    "Rocka": ["Flyger under vatten", "Pannkaka med vingar"],
    "Sköldpadda": ["Ingen brådska", "Långsamt men stilfullt"],
    "Dykare": ["Luft kvar? Absolut", "Bästa kontoret", "Flyter som en proffs"],
    "": ["Vänta lite …", "Vad var det där?!", "Plot twist", "Okej, det där var coolt", "Någon måste se det här"],
}
POETIC = ["Där ljuset slutar börjar tystnaden", "Ett andetag i taget", "Havet minns allt", "Långsamt, som tidvattnet",
          "Under ytan gäller andra regler", "Blått så långt ögat når"]
SHORT = ["Så här såg dagen ut", "Spoiler: det var magiskt", "Nästa nivå", "Inte illa!", "Tio av tio", "Mer av det här"]


def _label(s):
    lab = s.get("label") if s.get("label") not in (None, "Undervatten") else ""
    return s.get("species") if (s.get("species") and s.get("species_p", 0) >= 0.6) else (lab or "")


def suggest_rules(prop, tone, rng=None):
    rng = rng or random.Random()
    shots = prop.get("shots", [])
    pass
    items, seen = [], set()
    import datetime
    t_first = min([s["time"] for s in shots if s.get("time")] or [0])
    for i, s in enumerate(shots):
        lab = _label(s)
        if tone == "doc":
            if lab and lab not in seen and s["duration"] >= 2.0:
                seen.add(lab)
                sure = s.get("species") and s.get("species_p", 0) >= 0.6
                items.append(new_item(s["uid"], lab, "doc", (s.get("species_sci") or "") if sure else "", 0.4,
                                      min(3.5, s["duration"] - 0.4)))
            elif i == 0 and s.get("time"):
                d = datetime.datetime.fromtimestamp(s["time"])
                items.append(new_item(s["uid"], f"Dyk {int(s.get('session') or 0) + 1}", "chapter",
                                      d.strftime("%Y-%m-%d"), 0.3, 2.4))
        elif tone == "fun":
            if (i % 2 == 1 or (s.get("fx") or {}).get("freeze")) and s["duration"] >= 1.4:
                pool = FUN.get(s.get("label") or "", None) or FUN[""]
                t = s.get("caption") or rng.choice([x for x in pool if x not in seen] or pool)
                seen.add(t)
                items.append(new_item(s["uid"], t, "fun", "", 0.3, min(2.6, s["duration"] - 0.2)))
        elif tone == "travel":
            if i == 0 or (s.get("time") and shots[i - 1].get("time")
                          and datetime.date.fromtimestamp(s["time"]) != datetime.date.fromtimestamp(shots[i - 1]["time"])):
                day = ((datetime.date.fromtimestamp(s["time"]) - datetime.date.fromtimestamp(t_first)).days + 1
                       if s.get("time") and t_first else 1)
                d = datetime.datetime.fromtimestamp(s["time"]) if s.get("time") else None
                mon = ["jan", "feb", "mar", "apr", "maj", "jun", "jul", "aug", "sep", "okt", "nov", "dec"]
                items.append(new_item(s["uid"], f"Dag {day}", "place", f"{d.day} {mon[d.month - 1]}" if d else "",
                                      0.3, 2.6))
            elif lab and lab not in seen and s["duration"] >= 2.0 and len(items) < 4:
                seen.add(lab)
                items.append(new_item(s["uid"], f"Dagens möte: {lab.lower()}", "caption", "", 0.4, 2.6))
        elif tone == "poetic":
            if i in (0, len(shots) // 2, len(shots) - 1) and s["duration"] >= 1.6:
                items.append(new_item(s["uid"], POETIC[(i + rng.randrange(6)) % len(POETIC)], "caption", "", 0.4,
                                      min(3.4, s["duration"])))
        elif tone == "social":
            if i == 0:
                lab0 = _label(s)
                hook = (f"POV: {lab0.lower()} framför masken" if lab0 and rng.random() < 0.5 else rng.choice(HOOKS))
                items.append(new_item(s["uid"], hook, "hook" if not hook.startswith("POV") else "pov", "", 0.1,
                                      min(2.8, s["duration"])))
            elif lab and lab not in seen and s["duration"] >= 1.4 and len(items) < 5:
                seen.add(lab)
                items.append(new_item(s["uid"], rng.choice([f"{lab} 😍", f"Hej {lab.lower()}!", f"{lab} på riktigt",
                                                            f"Titta: {lab.lower()}"]), "tiktok", "", 0.25,
                                      min(2.4, s["duration"] - 0.2)))
            elif i == len(shots) - 1 and s["duration"] >= 1.2:
                items.append(new_item(s["uid"], rng.choice(["Följ för mer under ytan 🌊", "Vilken var din favorit?",
                                                            "Spara till nästa dyk"]), "tiktok", "", 0.2,
                                      min(2.6, s["duration"])))
        elif tone == "short":
            if i in (0, len(shots) - 1) and s["duration"] >= 1.2:
                items.append(new_item(s["uid"], rng.choice(SHORT), "meme", "", 0.2, min(2.4, s["duration"])))
    return items


def suggest_llm(prop, tone, server):
    """Qwen skriver en text per klipp utifrån AI-beskrivningarna (desc). None om det inte går."""
    shots = prop.get("shots", [])
    lines = []
    for i, s in enumerate(shots):
        lines.append(f"{i + 1}. {s.get('desc') or _label(s) or 'undervattensbild'} ({s['duration']:.1f} s)")
    how = {"doc": "saklig dokumentär, artnamn och korta fakta", "fun": "rolig, humoristisk, gärna djurets 'tankar'",
           "travel": "personlig reseberättare i jag-form", "poetic": "poetisk och stämningsfull",
           "short": "kort, käck och slagkraftig som i sociala medier",
           "social": "som en virala reel på Instagram/TikTok: första texten är en krok eller POV, sedan korta "
                     "rader med emoji, sista en uppmaning"}[tone]
    ask = ("Du skriver texter som visas i en kort film. Ton: " + how + ".\nKlippen i ordning:\n" + "\n".join(lines) +
           "\nSkriv texter på SVENSKA till ungefär vart annat klipp (inte alla), max 6 ord per text. "
           "Svara ENDAST med JSON: [{\"klipp\": nummer, \"text\": \"...\", \"undertext\": \"...\"}]")
    try:
        out = server.chat(ask, (), max_tokens=500)
        m = re.search(r"\[.*\]", out, re.S)
        data = json.loads(m.group(0)) if m else None
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(data, list):
        return None
    items = []
    for d in data:
        try:
            k = int(d.get("klipp")) - 1
        except (TypeError, ValueError, AttributeError):
            continue
        if 0 <= k < len(shots) and str(d.get("text") or "").strip():
            s = shots[k]
            st = ("pov" if str(d["text"]).upper().startswith("POV") else "hook") if (tone == "social" and not items) \
                else TONE_STYLE.get(tone, "caption")
            items.append(new_item(s["uid"], d["text"], st, d.get("undertext") or "",
                                  0.3, min(3.2, max(1.2, s["duration"] - 0.2))))
    return items or None


def suggest(prop, tone, use_llm=True):
    ensure_uids(prop)
    if tone not in TONES:
        tone = "doc"
    if use_llm:
        try:
            from . import vlm
            if vlm.ready():
                with vlm.Server(ctx=4096) as srv:
                    got = suggest_llm(prop, tone, srv)
                if got:
                    return got, "Qwen"
        except Exception:  # noqa: BLE001
            pass
    return suggest_rules(prop, tone), "mallar"
