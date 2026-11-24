"""Texter i filmerna på flera språk.

Fasta texter (djurgrupper, berättelsernas namn, kapitel, pratbubblor, datum, dykdata) översätts
med inbyggda tabeller. Fri text (egna titlar, pratbubblor från djupanalysen) översätts av
Qwen3-VL när djupanalysen finns (Mac), annars behålls originalet – den kan alltid rättas i
redigeringen per språk. Artnamn: svenskt namn på svenska, annars engelskt namn; det latinska
namnet är detsamma på alla språk."""

import json
import re
from datetime import datetime

LANGS = {"sv": "Svenska", "en": "English", "de": "Deutsch", "es": "Español", "fr": "Français",
         "it": "Italiano", "nl": "Nederlands", "no": "Norsk", "da": "Dansk", "fi": "Suomi"}
ORDER = ["en", "de", "es", "fr", "it", "nl", "no", "da", "fi"]

_T = {
    # djurgrupper och miljöer
    "Sköldpadda": "Sea turtle|Meeresschildkröte|Tortuga marina|Tortue marine|Tartaruga marina|Zeeschildpad|Havskilpadde|Havskildpadde|Merikilpikonna",
    "Dykare": "Divers|Taucher|Buceadores|Plongeurs|Subacquei|Duikers|Dykkere|Dykkere|Sukeltajat",
    "Rev och koraller": "Reef and corals|Riff und Korallen|Arrecife y corales|Récif et coraux|Barriera e coralli|Rif en koralen|Rev og koraller|Rev og koraller|Riutta ja korallit",
    "Fiskstim": "School of fish|Fischschwarm|Banco de peces|Banc de poissons|Banco di pesci|Scholen vis|Fiskestim|Fiskestime|Kalaparvi",
    "Fisk": "Fish|Fisch|Pez|Poisson|Pesce|Vis|Fisk|Fisk|Kala",
    "Haj": "Shark|Hai|Tiburón|Requin|Squalo|Haai|Hai|Haj|Hai",
    "Rocka": "Ray|Rochen|Raya|Raie|Razza|Rog|Rokke|Rokke|Rausku",
    "Bläckfisk": "Cephalopod|Kopffüßer|Cefalópodo|Céphalopode|Cefalopode|Inktvis|Blekksprut|Blæksprutte|Mustekala",
    "Manet": "Jellyfish|Qualle|Medusa|Méduse|Medusa|Kwal|Manet|Vandmand|Meduusa",
    "Muräna": "Moray eel|Muräne|Morena|Murène|Murena|Murene|Murene|Muræne|Mureena",
    "Nakensnäcka": "Nudibranch|Nacktkiemer|Nudibranquio|Nudibranche|Nudibranco|Zeenaaktslak|Nakensnegl|Nøgensnegl|Nudibranki",
    "Krabba och hummer": "Crabs and lobsters|Krabben und Hummer|Cangrejos y langostas|Crabes et homards|Granchi e astici|Krabben en kreeften|Krabber og hummer|Krabber og hummere|Ravut ja hummerit",
    "Sjöhäst": "Seahorse|Seepferdchen|Caballito de mar|Hippocampe|Cavalluccio marino|Zeepaardje|Sjøhest|Søhest|Merihevonen",
    "Säl och delfin": "Seals and dolphins|Robben und Delfine|Focas y delfines|Phoques et dauphins|Foche e delfini|Zeehonden en dolfijnen|Seler og delfiner|Sæler og delfiner|Hylkeet ja delfiinit",
    "Kammanet": "Comb jelly|Rippenqualle|Ctenóforo|Cténophore|Ctenoforo|Ribkwal|Kammanet|Ribbegople|Kampamaneetti",
    "Bottenfisk": "Bottom fish|Bodenfisch|Pez de fondo|Poisson de fond|Pesce di fondo|Bodemvis|Bunnfisk|Bundfisk|Pohjakala",
    "Plattfisk": "Flatfish|Plattfisch|Pez plano|Poisson plat|Pesce piatto|Platvis|Flatfisk|Fladfisk|Kampela",
    "Sjöstjärna": "Starfish|Seestern|Estrella de mar|Étoile de mer|Stella marina|Zeester|Sjøstjerne|Søstjerne|Meritähti",
    "Räka": "Shrimp|Garnele|Gamba|Crevette|Gamberetto|Garnaal|Reke|Reje|Katkarapu",
    "Snäcka och mussla": "Snails and shells|Schnecken und Muscheln|Caracoles y conchas|Escargots et coquillages|Lumache e conchiglie|Slakken en schelpen|Snegler og skjell|Snegle og muslinger|Kotilot ja simpukat",
    "Vrak": "Wreck|Wrack|Pecio|Épave|Relitto|Wrak|Vrak|Vrag|Hylky",
    "Grotta": "Cave|Höhle|Cueva|Grotte|Grotta|Grot|Grotte|Grotte|Luola",
    "Kelp och tång": "Kelp and seaweed|Kelp und Tang|Kelp y algas|Varech et algues|Kelp e alghe|Kelp en zeewier|Tare og tang|Tang og tare|Levät",
    "Ytan underifrån": "The surface from below|Die Oberfläche von unten|La superficie desde abajo|La surface vue d'en bas|La superficie da sotto|Het oppervlak van onderen|Overflaten nedenfra|Overfladen nedefra|Pinta alhaalta",
    "Båt": "Boat|Boot|Barco|Bateau|Barca|Boot|Båt|Båd|Vene",
    "Strand": "Beach|Strand|Playa|Plage|Spiaggia|Strand|Strand|Strand|Ranta",
    "Solnedgång": "Sunset|Sonnenuntergang|Atardecer|Coucher de soleil|Tramonto|Zonsondergang|Solnedgang|Solnedgang|Auringonlasku",
    "Berg": "Mountains|Berge|Montañas|Montagnes|Montagne|Bergen|Fjell|Bjerge|Vuoret",
    "Stad": "City|Stadt|Ciudad|Ville|Città|Stad|By|By|Kaupunki",
    "Människor": "People|Menschen|Gente|Personnes|Persone|Mensen|Mennesker|Mennesker|Ihmiset",
    "Landskap": "Landscape|Landschaft|Paisaje|Paysage|Paesaggio|Landschap|Landskap|Landskab|Maisema",
    "Undervatten": "Underwater|Unterwasser|Bajo el agua|Sous l'eau|Sott'acqua|Onderwater|Under vann|Under vand|Veden alla",
    # berättelser
    "Dykets höjdpunkter": "Dive highlights|Tauch-Highlights|Lo mejor de la inmersión|Les temps forts de la plongée|Lo meglio dell'immersione|Hoogtepunten van de duik|Dykkets høydepunkter|Dykkets højdepunkter|Sukelluksen kohokohdat",
    "Resans höjdpunkter": "Trip highlights|Highlights der Reise|Lo mejor del viaje|Les temps forts du voyage|Lo meglio del viaggio|Hoogtepunten van de reis|Turens høydepunkter|Rejsens højdepunkter|Matkan kohokohdat",
    "Roliga ögonblick": "Funny moments|Lustige Momente|Momentos divertidos|Moments amusants|Momenti divertenti|Grappige momenten|Morsomme øyeblikk|Sjove øjeblikke|Hauskoja hetkiä",
    "Lugna stunder": "Calm moments|Ruhige Momente|Momentos de calma|Moments calmes|Momenti di calma|Rustige momenten|Rolige øyeblikk|Rolige øjeblikke|Rauhallisia hetkiä",
    "I rörelse": "In motion|In Bewegung|En movimiento|En mouvement|In movimento|In beweging|I bevegelse|I bevægelse|Liikkeessä",
    "Detaljer och färger": "Details and colours|Details und Farben|Detalles y colores|Détails et couleurs|Dettagli e colori|Details en kleuren|Detaljer og farger|Detaljer og farver|Yksityiskohdat ja värit",
    "Det stora blå": "The big blue|Das große Blau|El gran azul|Le grand bleu|Il grande blu|Het grote blauw|Det store blå|Det store blå|Suuri sininen",
    "Miljöerna": "The surroundings|Die Umgebung|El entorno|Les paysages|I luoghi|De omgeving|Omgivelsene|Omgivelserne|Ympäristöt",
    "Dyket i tidsordning": "The dive from start to finish|Der Tauchgang von Anfang bis Ende|La inmersión de principio a fin|La plongée du début à la fin|L'immersione dall'inizio alla fine|De duik van begin tot eind|Dykket fra start til slutt|Dykket fra start til slut|Sukellus alusta loppuun",
    # pratbubblor
    "Vem där?": "Who's there?|Wer ist da?|¿Quién anda ahí?|Qui est là ?|Chi è là?|Wie is daar?|Hvem der?|Hvem der?|Kuka siellä?",
    "Hallå där!": "Hello there!|Hallo du!|¡Hola!|Coucou !|Ciao!|Hallo daar!|Hallo der!|Hej med dig!|Hei siellä!",
    "Kolla in mig!": "Check me out!|Schau mich an!|¡Mírame!|Regarde-moi !|Guardami!|Kijk mij eens!|Se på meg!|Se mig!|Katso minua!",
    "Ojdå!": "Oops!|Hoppla!|¡Uy!|Oups !|Ops!|Oeps!|Oisann!|Ups!|Hups!",
    "Smygläge": "Stealth mode|Tarnmodus|Modo sigilo|Mode furtif|Modalità furtiva|Sluipmodus|Snikemodus|Snigetilstand|Hiippailutila",
    "Här bor jag": "I live here|Hier wohne ich|Aquí vivo yo|J'habite ici|Abito qui|Hier woon ik|Her bor jeg|Her bor jeg|Täällä asun",
    "Hej då!": "Bye!|Tschüss!|¡Adiós!|Salut !|Ciao ciao!|Doei!|Ha det!|Farvel!|Heippa!",
    "Inte nu …": "Not now …|Nicht jetzt …|Ahora no …|Pas maintenant …|Non ora …|Niet nu …|Ikke nå …|Ikke nu …|Ei nyt …",
    "Titta här!": "Look here!|Schau mal!|¡Mira aquí!|Regarde !|Guarda qui!|Kijk hier!|Se her!|Se her!|Katso tänne!",
    "Wow!": "Wow!|Wow!|¡Guau!|Waouh !|Wow!|Wauw!|Wow!|Wow!|Vau!",
}
_WORD = {"Dyk": "Dive|Tauchgang|Inmersión|Plongée|Immersione|Duik|Dykk|Dyk|Sukellus",
         "Dag": "Day|Tag|Día|Jour|Giorno|Dag|Dag|Dag|Päivä"}
_MONTHS = {
    "sv": ["januari", "februari", "mars", "april", "maj", "juni", "juli", "augusti", "september", "oktober",
           "november", "december"],
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
           "November", "December"],
}
# bestämd form (titlar) → grupp
_TITLE_TO_LABEL = {}


def _row(sv, lang):
    if lang == "sv":
        return sv
    vals = _T.get(sv)
    if not vals:
        return None
    return vals.split("|")[ORDER.index(lang)]


def register_titles(portrait_title):
    for label, title in portrait_title.items():
        _TITLE_TO_LABEL[title] = label


def fixed(text, lang):
    """Översättning från tabellerna, eller None."""
    if not text or lang == "sv" or lang not in ORDER:
        return text if lang == "sv" else None
    t = _row(text, lang)
    if t:
        return t
    if text in _TITLE_TO_LABEL:
        return _row(_TITLE_TO_LABEL[text], lang)
    m = re.fullmatch(r"(Dyk|Dag) (\d+)(.*)", text)
    if m:
        return f"{_WORD[m.group(1)].split('|')[ORDER.index(lang)]} {m.group(2)}{m.group(3)}"
    return None


def date(ts, lang):
    d = datetime.fromtimestamp(ts)
    if lang in _MONTHS:
        return f"{d.day} {_MONTHS[lang][d.month - 1]} {d.year}"
    sep = "/" if lang in ("es", "fr", "it") else "-" if lang == "nl" else "."
    return f"{d.day:02d}{sep}{d.month:02d}{sep}{d.year}"


def number(x, lang, decimals=1):
    s = f"{x:.{decimals}f}"
    return s if lang == "en" else s.replace(".", ",")


def dive_text(depth, temp, lang, units="metric"):
    if units == "imperial":
        d = f"{number(depth * 3.28084, lang, 0)} ft"
        t = f"{number(temp * 9 / 5 + 32, lang, 0)} °F" if temp is not None else ""
    else:
        d = f"{number(depth, lang, 1)} m"
        t = f"{number(temp, lang, 0)} °C" if temp is not None else ""
    return f"{d} · {t}" if t else d


def species_name(sp_row, lang):
    """sp_row: [sv, sv_bestämd, latin, engelska, grupp]"""
    if not sp_row:
        return None
    return sp_row[0] if lang == "sv" else sp_row[3][:1].upper() + sp_row[3][1:]


# ---------- fri text: djupanalysens modell översätter ----------

def translate_free(texts, lang, server=None):
    """Översätt fri text med Qwen3-VL (om den körs). Returnerar {text: översättning}."""
    texts = [t for t in dict.fromkeys(texts) if t]
    if not texts or lang == "sv":
        return {t: t for t in texts}
    from . import vlm
    own = None
    try:
        if server is None:
            if not vlm.ready():
                return {}
            own = server = vlm.Server(ctx=4096)
        prompt = (f"Translate these short Swedish video captions to {LANGS[lang]}. Keep them short, natural and "
                  "playful where they are playful. Reply with ONLY a JSON object mapping each Swedish text to "
                  "its translation.\n" + json.dumps(texts, ensure_ascii=False))
        out = server.chat(prompt, max_tokens=60 + 40 * len(texts))
        m = re.search(r"\{.*\}", out, re.S)
        data = json.loads(m.group(0)) if m else {}
        return {k: str(v).strip()[:80] for k, v in data.items() if k in texts and str(v).strip()}
    except Exception as e:  # noqa: BLE001
        print("Översättningen misslyckades:", e)
        return {}
    finally:
        if own:
            own.close()


def localize(proposal, lang, clips_species=None, free=None):
    """Texterna i ett förslag på valt språk: {"title","subtitle", "shots": [text-dict eller None]}.
    Ordning: användarens egna översättningar (i18n) → tabeller → modellens översättning → original."""
    free = free or {}
    eff = proposal.get("effects") or {}
    over = (proposal.get("i18n") or {}).get(lang, {})

    def tr(text):
        if not text:
            return text
        if lang == "sv":
            return text
        return fixed(text, lang) or free.get(text) or text

    title = over.get("title") or tr(eff.get("title") or "")
    sub = eff.get("subtitle") or ""
    if sub and lang != "sv" and proposal.get("shots"):
        ts = [s.get("time") for s in proposal["shots"] if s.get("time")]
        sub = date(min(ts), lang) if ts else sub
    shots = []
    for i, s in enumerate(proposal.get("shots", [])):
        t = s.get("text")
        o = (over.get("shots") or {}).get(str(i))
        if not t:
            shots.append(None)
            continue
        t = dict(t)
        if o:
            t["text"], t["sub"] = o.get("text", t["text"]), o.get("sub", t.get("sub", ""))
        elif lang != "sv":
            sp = (clips_species or {}).get(t["text"])
            t["text"] = species_name(sp, lang) if sp else tr(t["text"])
        shots.append(t)
    # reklamtexter (krok, säljpunkter, uppmaning) och sångtext: användarens egna, översatta om möjligt
    pr = dict(proposal.get("promo") or {})
    po = over.get("promo") or {}
    promo = {
        "hook": po.get("hook") or tr(pr.get("hook") or ""),
        "points": po.get("points") or [tr(x) for x in (pr.get("points") or []) if x],
        "cta": po.get("cta") or tr(pr.get("cta") or ""),
        "url": pr.get("url") or "",
        "logo": pr.get("logo") or "",
        "endcard": pr.get("endcard", True),
    }
    lyrics = over.get("lyrics") or (proposal.get("lyrics") or {}).get("lines") or []
    oo = over.get("overlays") or {}
    overlays = {it["id"]: {"text": (oo.get(it["id"]) or {}).get("text") or tr(it.get("text") or ""),
                           "sub": (oo.get(it["id"]) or {}).get("sub") or tr(it.get("sub") or "")}
                for it in proposal.get("overlays") or []}
    return {"title": title, "subtitle": sub, "shots": shots, "promo": promo, "lyrics": lyrics, "overlays": overlays}


def free_texts(proposal, lang):
    """Texter som inte finns i tabellerna (behöver modellen)."""
    if lang == "sv":
        return []
    eff = proposal.get("effects") or {}
    out = []
    pr = proposal.get("promo") or {}
    cands = ([eff.get("title")] + [(s.get("text") or {}).get("text") for s in proposal.get("shots", [])]
             + [pr.get("hook"), pr.get("cta")] + list(pr.get("points") or [])
             + [x for it in proposal.get("overlays") or [] for x in (it.get("text"), it.get("sub"))])
    for t in cands:
        if t and not fixed(t, lang):
            out.append(t)
    return out
