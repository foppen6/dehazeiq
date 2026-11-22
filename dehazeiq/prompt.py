"""Beskriv filmen med egna ord: "jag har bakom kulisserna-klipp, gör en snygg video om det".

Texten blir en filmplan (filmtyp, plattform, längd, antal varianter, stilar och vad filmen
ska handla om). På Mac tolkar Qwen texten när djupanalysen är nedladdad; annars används
regler som klarar de vanligaste formuleringarna. Planen visas för användaren innan den körs.
"""

import json
import re

from .config import FILM_TYPES, MV_STYLES, PLATFORMS, PROMO_STYLES, STYLES

NUM = {"en": 1, "ett": 1, "två": 2, "tre": 3, "fyra": 4, "fem": 5, "sex": 6, "sju": 7, "åtta": 8,
       "nio": 9, "tio": 10, "ett par": 2, "några": 3, "flera": 4}

TYPE_WORDS = [
    ("promo", r"reklam|promo|promotion|annons|marknadsf|kampanj|sälj|företag"),
    ("trailer", r"trailer|teaser"),
    ("musicvideo", r"musikvideo|music ?video|till låten|till musiken"),
    ("animal", r"djurporträtt|porträtt av"),
    ("trip", r"resefilm|resvideo|från resan|semesterfilm"),
    ("dive", r"dykfilm|från dyket|dykvideo"),
    ("reels", r"\breels\b|kortfilmer|flera korta"),
]

PLATFORM_WORDS = [
    ("tiktok", r"tiktok"), ("shorts", r"shorts"), ("youtube", r"youtube|liggande|16:9|bredformat"),
    ("facebook", r"facebook"), ("square", r"kvadrat|1:1"), ("feed", r"flöde|4:5|instagraminlägg"),
    ("reels", r"reels|instagram|stående|9:16|story|stories"),
]

STYLE_WORDS = [
    ("promo_premium", r"premium|exklusiv|lyx|elegant"), ("promo_energy", r"energi|energisk|peppig"),
    ("promo_info", r"informativ|information|förklar"), ("promo_experience", r"upplevelse|känsla"),
    ("mv_ballad", r"ballad|långsam låt"), ("mv_glitch", r"glitch|techno|elektronisk"),
    ("mv_lyrics", r"sångtext|lyrics|med text till"),
    ("cinematic", r"snygg|cinematisk|filmisk|episk|vacker|proffsig"), ("documentary", r"dokumentär|seriös"),
    ("calm", r"lugn|stilla|avslappn|rofylld"), ("action", r"action|fart|häftig|tempo|snabb"),
    ("playful", r"rolig|lekfull|skojig|kul|humor"), ("vintage", r"vintage|retro|super ?8|gammaldags"),
    ("widescreen", r"bredbild|biokänsla"), ("minimal", r"minimal|enkel|ren"), ("vlog", r"vlogg|vlog|dagbok"),
    ("ambient", r"ambient|utan musik|naturljud"),
]

STOP = set("""jag du vi ni han hon den det de dom man har hade ha en ett min mitt mina din ditt dina vår
vårt våra kan kunde ska skulle vill ville göra gör gjort gjorde skapa skapar fixa fixar klipp klippa
klippen film filmen filmer filmerna video videon videor bild bilden bilder bilderna foto fotot foton
material materialet om av med för till från på i och eller som så att det här där den här snygg snyggt
snygga fin fint fina bra lite mycket några någon något några varianter variant versioner version
förslag gärna tack please hej kort korta lång långa sekunder sek s minut minuter min stycken st typ
liksom ungefär runt cirka ca handlar ska vara blir bli också även mer massa alla allt inte nu sen
då när också från ur låt låten låtar musik musiken musikvideo två tre fyra fem sex sju åtta nio tio par
olika vår våran vårt oss er""".split())


def _num(word):
    word = word.lower()
    if word.isdigit():
        return int(word)
    return NUM.get(word)


def parse_rules(text):
    t = " " + text.lower().strip() + " "
    plan = {"type": "prompt", "prompt": text.strip()}
    for key, pat in TYPE_WORDS:
        if re.search(rf"\b(?:{pat})\w{{0,6}}\b", t):
            plan["type"] = key
            break
    for key, pat in PLATFORM_WORDS:
        if re.search(rf"\b(?:{pat})\w{{0,6}}\b", t):
            plan["platform"] = key
            break
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(min|minut|minuter)\b", t)
    if m:
        plan["length"] = float(m.group(1).replace(",", ".")) * 60
    else:
        m = re.search(r"(\d+)\s*(s|sek|sekunder|sekunders)\b", t)
        if m:
            plan["length"] = float(m.group(1))
    m = re.search(r"\b(\d+|en|ett|två|tre|fyra|fem|sex|sju|åtta|nio|tio|ett par|några|flera)\s+"
                  r"(varianter|versioner|förslag|alternativ|filmer|olika)", t)
    if m and _num(m.group(1)):
        plan["count"] = max(1, min(8, _num(m.group(1))))
    styles = []
    for key, pat in STYLE_WORDS:
        if re.search(rf"\b(?:{pat})\w{{0,6}}\b", t):
            styles.append(key)
    if plan["type"] == "trailer":
        styles = []
    elif plan["type"] == "promo":
        styles = [s for s in styles if s in PROMO_STYLES] or []
    elif plan["type"] == "musicvideo":
        styles = [s for s in styles if s in MV_STYLES] or []
    else:
        styles = [s for s in styles if s not in PROMO_STYLES and s not in MV_STYLES]
    if styles:
        plan["styles"] = styles
    # Vad handlar filmen om? Det som blir kvar när instruktionsorden är borta
    words = re.findall(r"[a-zåäöéü0-9-]+", t)
    kill = set()
    for _, pat in TYPE_WORDS + PLATFORM_WORDS + STYLE_WORDS:
        for w in words:
            if re.fullmatch(rf"(?:{pat})\w{{0,6}}", w):
                kill.add(w)
    rest = [w for w in words if w not in STOP and w not in kill and not w.isdigit()]
    # "bakom kulisserna" ska stå kvar som fras: behåll ordningen
    if rest:
        q = " ".join(rest[:6])
        plan["query"] = q
        plan["title"] = q[:1].upper() + q[1:]
    return plan


def parse_llm(text, server):
    """Qwen tolkar beskrivningen till JSON. Returnerar None om svaret inte går att använda."""
    types = ", ".join(f"{k} ({v['label']})" for k, v in FILM_TYPES.items())
    plats = ", ".join(PLATFORMS)
    styles = ", ".join(STYLES)
    ask = (
        "Du gör filmplaner för ett videoredigeringsprogram. Användaren beskriver vilken film hen vill ha.\n"
        f"Filmtyper: {types}.\nPlattformar: {plats}.\nStilar: {styles}.\n"
        "Svara ENDAST med JSON: {\"type\":..., \"platform\":..., \"length\": sekunder eller null, "
        "\"count\": antal varianter eller null, \"styles\": [...], \"query\": vad filmen ska visa "
        "(några ord på svenska, sådant som syns i bild, eller \"\"), \"title\": kort titel på svenska}.\n"
        f"Beskrivning: {text}"
    )
    try:
        out = server.chat(ask, (), max_tokens=220)
        m = re.search(r"\{.*\}", out, re.S)
        if not m:
            return None
        data = json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return None
    plan = {"type": data.get("type") if data.get("type") in FILM_TYPES else "prompt", "prompt": text.strip()}
    if data.get("platform") in PLATFORMS:
        plan["platform"] = data["platform"]
    for k in ("length", "count"):
        try:
            if data.get(k):
                plan[k] = float(data[k]) if k == "length" else int(data[k])
        except (TypeError, ValueError):
            pass
    st = [s for s in (data.get("styles") or []) if s in STYLES]
    if st:
        plan["styles"] = st
    if isinstance(data.get("query"), str) and data["query"].strip():
        plan["query"] = data["query"].strip()[:80]
    if isinstance(data.get("title"), str) and data["title"].strip():
        plan["title"] = data["title"].strip()[:60]
    return plan


def parse(text, use_llm=True):
    """Filmplan ur en beskrivning, plus en mening som förklarar hur den tolkades."""
    text = (text or "").strip()
    if not text:
        raise ValueError("Skriv vad du vill ha för film")
    plan, how = None, "regler"
    if use_llm:
        try:
            from . import vlm
            if vlm.ready():
                with vlm.Server(ctx=4096) as srv:
                    plan = parse_llm(text, srv)
                    how = "Qwen"
        except Exception:  # noqa: BLE001
            plan = None
    if not plan:
        plan, how = parse_rules(text), "regler"
    # komplettera med regelverkets fynd där modellen inte sa något
    rules = parse_rules(text)
    for k in ("platform", "length", "count", "styles", "query", "title"):
        if k not in plan and k in rules:
            plan[k] = rules[k]
    ft = FILM_TYPES.get(plan["type"], FILM_TYPES["prompt"])
    plan.setdefault("platform", ft["platform"])
    plan.setdefault("count", ft["count"])
    plan.setdefault("length", ft.get("length") or PLATFORMS[plan["platform"]]["length"])
    return {"plan": plan, "explain": explain(plan), "how": how}


def explain(plan):
    ft = FILM_TYPES.get(plan["type"], FILM_TYPES["prompt"])
    pf = PLATFORMS.get(plan.get("platform"), PLATFORMS["reels"])
    parts = [f"{ft['label']}", f"{int(plan.get('count') or ft['count'])} varianter",
             f"{pf['label']} ({pf['format']})", f"{int(round(float(plan.get('length') or pf['length'])))} s"]
    if plan.get("styles"):
        parts.append("stil: " + ", ".join(STYLES[s]["label"].lower() for s in plan["styles"]))
    s = " · ".join(parts)
    if plan.get("query"):
        s += f" · handlar om: ”{plan['query']}”"
    return s
