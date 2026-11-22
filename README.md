# DeHazeIQ – AI-powered video editing, without the hassle (v0.12)

Lokalt AI-videoredigeringsprogram för dyk-, natur- och resefilm. Fungerar på **Mac och Windows**,
och kan styras från **mobil och surfplatta** via wifi.

1. **Importera** – välj en mapp med filmklipp. Metadata läses och lätta proxyfiler skapas.
2. **Analys** – skärpa, exponering, stabilitet, rörelse, scenbyten, färgbalans och bästa sekvens per klipp.
3. **Filmförslag** – tre olika filmer av samma material (cinematisk, action, lugn natur) med musik i takt,
   förhandsvisning och export till MP4 + tidslinje (.otio) för DaVinci Resolve.

Allt körs lokalt. Inga filer laddas upp någonstans.

## Installera (enklast)

Ladda ner från **Releases** på GitHub-sidan:

- **Mac (Apple Silicon):** `DeHazeIQ-mac.dmg` – öppna och dra DeHazeIQ till Program.
  Första gången: Systeminställningar › Integritet och säkerhet › **Öppna ändå**.
- **Windows:** `DeHazeIQ-Setup.exe` – kör och klicka igenom.
  Varnar SmartScreen: **Mer information** › **Kör ändå**.

Inget annat behövs – Python och FFmpeg är inbyggda. DeHazeIQ öppnas i ett eget fönster.

Installationsfilerna byggs automatiskt av GitHub Actions (`.github/workflows/build.yml`) vid varje
push till `main`. En tagg som `v0.3.0` skapar en ny Release.

## Köra från källkoden (för utveckling)

### Mac

1. Installera FFmpeg och Python (en gång): `brew install ffmpeg python`
2. Packa upp mappen och dubbelklicka på **Starta DeHazeIQ.command**.
   Första gången skapas en `.venv` och paketen installeras (cirka en minut).
   Varning om okänd utvecklare: högerklicka på filen › Öppna.
3. Webbläsaren öppnas på `http://127.0.0.1:8765`.

### Windows

1. Öppna Terminal (eller PowerShell) och installera (en gång):
   ```
   winget install ffmpeg
   winget install Python.Python.3.12
   ```
   Logga ut och in igen så att FFmpeg hittas.
2. Packa upp mappen och dubbelklicka på **Starta DeHazeIQ.bat**.
   Varnar SmartScreen: klicka på "Mer information" › "Kör ändå".
3. Webbläsaren öppnas på `http://127.0.0.1:8765`.

Videokodningen använder grafikkortet automatiskt om det går: Apple VideoToolbox (Mac),
Nvidia NVENC, Intel Quick Sync eller AMD AMF (Windows). Annars används x264. Vilken som används
syns uppe till höger. Stäng av hårdvarukodning med miljövariabeln `DEHAZEIQ_NO_HW=1`.

## Mobil och surfplatta (via wifi)

1. Klicka på **Mobil** uppe till höger på datorn och sedan **Slå på**.
2. Öppna adressen som visas (till exempel `http://192.168.1.20:8766`) i mobilens webbläsare.
   Mobilen måste vara på samma wifi.
3. Ange den sexteckenkod som visas på datorn.

På mobilen kan du granska analysen, markera favoriter, skapa förslag, förhandsvisa, exportera och
spara färdiga filmer på enheten. Import och musik väljs på datorn. Allt tungt arbete görs av datorn.
Första gången kan brandväggen (macOS eller Windows) fråga om tillåtelse – svara Tillåt.
Starta direkt med wifi påslaget: `python -m dehazeiq --lan`.

## Arbetsflöde

1. Klicka **Välj mapp med filmklipp** (eller **Ny import** i sidomenyn). Projektet får mappens namn
   – byt namn eller ta bort projekt med pennan/papperskorgen i sidomenyn.
2. Resten sker automatiskt: inläsning → analys → **bortval av svaga klipp** → tre filmförslag →
   förhandsvisningar. Du behöver inte gå igenom klippen.
3. Titta på förslagen, tryck ↻ för ett nytt urval eller **Exportera**.

Automatiskt urval:
- Klipp vars bästa del är **suddig, skakig eller felexponerad**, eller klart svagare än resten,
  väljs bort med en förklaring (fliken *Bortvalda* i analysvyn). "Ta med ändå" tvingar in ett klipp.
- Även i godkända klipp används bara sekvenser där **skärpan håller hela vägen** (inget fokusletande).
- Finns det för lite skarpt material blir filmen hellre kortare än sämre.
- Vid beskärning (t.ex. **9:16 reels ur liggande video**) hittas motivet i varje bildruta och
  beskärningen följer det mjukt, så att motivet hamnar i bild och inte klipps bort.

Format, längd, stil och musik ställs in under **Importera** och gäller även nästa import.

## Berättelser

Filmerna byggs kring ett tema i stället för att bara samla de bästa klippen:

- **Djurporträtt** – en film om ett motiv (t.ex. sköldpaddan), helst från ett och samma dyk:
  öppningsbild (yta/nedstigning) → översikt och halvbild → närbilder → höjdpunkt → avsked.
- **Ett dyk** – ett dyk i tidsordning, från ytan till uppstigningen.
- **Resans/dykets höjdpunkter** – kapitel per dyk, samma motiv samlat, i tidsordning.
- **Detaljer och färger** – närbilderna, lugnt klippta.
- **Det stora blå / Miljöerna** – översikter, ytan och nedstigningen.
- **I rörelse** – klippen med mest rörelse, stegrat mot det mest intensiva.
- **Roliga ögonblick** – nyfikna djur som tittar in i kameran och oväntade ögonblick (stilen Lekfull).
- **Lugna stunder** – djur som vilar och långsamma tagningar.

I en film om ett djur jämför AI:n hur djuret ser ut i varje klipp och tar bara med samma sorts
djur, även när den inte är säker på artnamnet (en knot eller ett kammanet blandas inte in i en
film om bläckfisken).

Teman hittas automatiskt: AI:n bestämmer motiv och bildutsnitt (närbild/halvbild/översikt) för
varje sekvens, och klippens tidsstämplar delar materialet i dyk (mer än 40 minuter mellan klipp
= nytt dyk). Med *AI väljer berättelser* blir de tre förslagen tre olika teman; väljer du ett tema
blir det tre versioner av samma berättelse. Varje ny generering väljer helst teman som inte
användes de senaste gångerna, så att du får variation.

## Filmtyper, plattformar och kö

- **Välj filmtyp från start:** dykfilm, resefilm, reels och shorts, djurporträtt, reklamfilm,
  musikvideo, trailer eller "Låt AI välja",
  en eller flera, med plattform, längd och antal förslag för varje.
- **Plattform per förslag:** Instagram Reels, TikTok, YouTube Shorts, YouTube, Instagram-flöde,
  Facebook eller kvadrat. Format, längd och beskärning anpassas automatiskt. En film kan exporteras
  till flera plattformar på en gång.
- **Jobbkö:** import, analys, förslag, förhandsvisningar och exporter körs ett i taget i bakgrunden,
  även från flera projekt. Ordningen kan ändras, jobb kan avbrytas och kön pausas.

## Redigera i programmet

Tidslinje med alla klipp. För valt klipp: längd (fäster på takten), slowmotion, snabbspolning,
frysbild, långsam zoom, zoomryck, flytta utsnittet genom att klicka i originalbilden, byta mot en
liknande sekvens som AI:n föreslår, flytta och ta bort. Fliken **Färg** har utseenden (bland annat
svartvitt, sepia, film, varm, kall och livlig) med styrka, samt exponering, kontrast, mättnad,
temperatur, nyans, skärpa och vinjett – för hela filmen eller ett klipp, med före/efter. Fliken
**Text** ändrar titeln, reklamtexter, logga och sångtext. Allt kan ångras.

## Stilar och övergångar

- **Dokumentär:** översikt → djuret → detaljer → beteende, långa tagningar, raka klipp och toning
  via svart vid nytt dyk, artnamn som textskylt (artnamn bara när artmodellen är säker, annars
  djurgruppen), datum under titeln och originalljud.
- **Lekfull:** lekfulla övergångar (cirkel, zoom, pixlar, skjut i rörelsens riktning), frysbild med
  pratbubbla (skriven av djupanalysen på Mac, annars en kort mall), snabbspolning, zoomryck och
  ljudeffekter (svisch och pling, genereras av programmet).
- **Övergångar:** AI:n väljer per klippbyte – raka klipp när motivet står still på samma plats
  (matchklipp), svep i rörelsens riktning, toning via svart vid nytt dyk och aldrig för många
  effektövergångar i rad. I redigeringen kan varje byte ändras (ett 20-tal övergångar).

## Fler stilar

Filmisk bredbild (svarta kanter, dämpade färger), Vintage Super 8 (varmt, filmkorn, glöd, fladder),
Musikvideo (klipp på takten, zoomryck, blixt), Ambient (långa tagningar, bara naturljud, ingen
text), Vlogg (tidsordning med "Dag 1"-skyltar) och Minimal (inga effekter).

## Bilder i filmerna

Foton importeras tillsammans med filmerna (JPG, PNG, TIFF, WebP, HEIC och RAW som NEF, ARW, CR2,
CR3, DNG, RAF, ORF och RW2 – från RAW används kamerans inbäddade förhandsbild). Bilden vänds rätt
efter EXIF och får tiden när den togs. Varje foto blir ett kort stillbildsklipp som analyseras som
video och får en långsam rörelse mot motivet (Ken Burns, in eller ut – kan ändras i redigeringen).
Finns samma bild som JPG och RAW används JPG:en.

## Beskriv filmen med egna ord

Skriv till exempel *"jag har bakom kulisserna-klipp, gör en snygg video om det"* eller
*"reklamfilm för TikTok, 15 sek, tre varianter, premium"*. Texten blir en filmplan (filmtyp,
plattform, längd, antal varianter, stil och vad filmen ska handla om) som visas innan den körs.
På Mac tolkar Qwen texten när djupanalysen är nedladdad, annars används inbyggda regler.

## Sök i materialet

I analysvyn går det att söka med egna ord (*bläckfisk*, *dykare med lampa*, *solnedgång*) –
CLIP jämför orden med bilderna som analysen redan har sparat, så det går på någon sekund.
"Gör film av träffarna" gör tre förslag av det som matchar.

## Reklamfilm, trailer och musikvideo

- **Reklamfilm:** fyra varianter – energi, premium, information och upplevelse. Krok i början,
  säljpunkter som textskyltar och en slutbild med logga, uppmaning och webbadress. Texterna och
  loggan läggs in i efterhand under Redigera › Text (alla är valfria), kan användas i alla
  reklamförslag på en gång och fyllas i från senast använda – samma film kan alltså användas för
  olika erbjudanden. Tänk på att musiken behöver vara licensierad för kommersiellt bruk.
- **Trailer:** lugn start med toningar via svart, valfria textskyltar, allt kortare klipp mot ett
  klimax och titeln (eller egen text) som slutbild.
- **Musikvideo:** fyra varianter – i takt, ballad (byten på halvtakt, glöd), glitch (färgglitch,
  blixtar) och med egen sångtext (en rad i taget i takt med låten). Musikens energi läses av: kortare
  klipp där den är intensiv, och filmens starkaste klipp börjar exakt på refrängen eller dropen.

## Dykets början och slut

Klipp som hör till dykets början (båt, i vattnet vid ytan, nedstigning) eller slut (boj/SMB,
säkerhetsstopp, uppstigning, ovan ytan efter dyket) känns igen på bildinnehållet och på var i dyket
de är tagna. I filmer om dyket hamnar de först respektive sist, och i filmer om ett djur, detaljer
eller rörelse tas de inte med. I analysvyn kan man själv ange "Del av dyket" för ett klipp.

## 360-film (Insta360 X4 m.fl.)

360-filmer importeras som allt annat: .insv direkt från kameran (beta – programmet syr ihop
linserna själv) eller en ihopsydd 360-MP4 från Insta360 Studio (bäst: stabiliserad och med
osynlig selfiepinne). AI:n tittar åt 24 håll varje sekund, hittar motivet och gör en mjuk
kamerabana. Av varje 360-film blir det två vanliga klipp: en **AI-vy** som följer motivet och en
**delad bild** (motivet överst, andra hållet nedtill – ofta dykaren) som används i stående format.

I redigeringen (Klipp › 360-kamera) kan varje 360-klipp bli **liten planet**, **kristallkula**,
**360-svep** (kameran vrider sig ett halvt varv) eller få egen riktning och bildvinkel, och alla
klipp kan få en **barrel roll**. I livliga stilar lägger AI:n själv in en liten planet som intro,
ett 360-svep och en barrel roll (slås av under Effekter › 360-effekter).

## Musik

AI:n väljer en låt ur **musikbiblioteket** som passar varje film (tempo, intensitet och längd) när
projektet inte har en vald låt. Biblioteket är en eller flera mappar på datorn – egen musik eller
nedladdat från valfri tjänst (Epidemic Sound, Artlist, Pixabay, YouTube Audio Library …).
Första gången programmet startar hämtas ett **gratis startpaket** (ett tiotal låtar, lugna till
energiska, CC0 och CC BY – får användas även i reklam) så att AI:n har musik att välja direkt.
Under **Musik** går det också att söka och hämta gratis musik med öppen licens via Openverse
(Jamendo, Freesound, Wikimedia Commons m.fl.), med filter för musik som får användas i reklam.

Varje låt har en licens (egen/köpt, fri även för reklam, Creative Commons, bara privat).
När licensen kräver det namnges upphovspersonen i slutet av filmen och i en textfil vid export,
och reklamfilmer väljer aldrig musik som bara får användas privat. Andra tjänster med eget API kan
läggas till med en JSON-fil i `music_sources/` i datamappen (se exempelfilen där).

## Texter på flera språk

Svenska, engelska, tyska, spanska, franska, italienska, nederländska, norska, danska och finska.
Djurgrupper, berättelsernas namn, kapitel, pratbubblor, datum och dykdata översätts med inbyggda
tabeller. Egna texter översätts av djupanalysens modell på Mac och kan rättas per språk under
Redigera › Text. Vid export väljs ett eller flera språk; varje version blir ett jobb i kön och får
en undertextfil (.srt).

## Bildförbättring

- **Ta bort dis:** lyfter bort dis-slöjan per färgkanal och ökar den lokala kontrasten.
- **Partiklar:** tidsfilter som dämpar svävande partiklar från lampan.
- **Stabilisering:** skakiga klipp lugnas (FFmpeg deshake).

AI:n slår på dis- och partikelreducering för undervattensklipp och stabilisering för skakiga klipp;
allt kan justeras per film eller klipp under Redigera › Färg.

## Dykdata

Importera dykloggen (Subsurface-XML, UDDF, Suunto DM5/SML eller CSV) i analysvyn. Klippen kopplas
till dyken via tidsstämplarna; klockskillnaden räknas fram automatiskt (även tidszoner) och kan
justeras. Djup och temperatur visas i filmen (m/°C eller ft/°F).

## Effekter

AI:n lägger till effekter där de passar, och de kan slås av och på under *Effekter* (utan att
generera om):

- **Mjuka övergångar** – korta toningar mellan klippen i Cinematisk och Lugn natur (Action har raka klipp).
  Klippbytena ligger kvar på takten.
- **Slowmotion** – bara när källan är filmad i minst 48 bilder/s (t.ex. 4K60/120).
- **Långsam zoom** – lugn inzoomning på stillsamma översikter och halvbilder.
- **Titel** – berättelsens namn tonas in i början.
- **Vinjett** – mörkare hörn i Cinematisk.
- **Snabbspolning** – en lugn tagning spelas i dubbel fart (Lekfull och Action).
- **Frysbild** – det roligaste ögonblicket fryses med en snabb inzoomning (Lekfull).
- **Zoomryck** – en kort zoom på klippet, i takt (Lekfull och Action).

## Artigenkänning (BioCLIP)

Utsnittet med djuret körs också genom BioCLIP (MIT-licens), en CLIP-modell tränad på miljontals
bilder av organismer med artnamn. Den skiljer t.ex. bläckfisk, knot och maneter åt, och arterna
grupperas så att en djurfilm bara innehåller samma sorts djur. Artlistan finns i
`packaging/bio_species.json` och kan byggas ut.

## Djupanalys med Qwen3-VL (Mac med Apple-chip)

På en Mac med M-chip kan DeHazeIQ låta en språk- och bildmodell titta på klippen och beskriva vad
som händer: vilket djur, vad det gör, hur roligt och vackert ögonblicket är och om motivet är
skarpt. Det används till urval, dramaturgi (lugn början → handling → höjdpunkt) och berättartext.
Modellen körs lokalt med llama.cpp och väljs efter datorns minne (30B vid 32 GB eller mer, annars
8B eller 4B). Den laddas ner med en knapp i analysvyn första gången och körs sedan automatiskt.

## Djuret i mitten

Analysen (version 2) delar varannan sekund in bilden i 15 överlappande utsnitt och låter AI:n avgöra
i vilket djuret syns. Beskärningen till 9:16, 4:5 och 1:1 följer den positionen. Projekt som
analyserades med en äldre version får en knapp: *Uppdatera analysen*.

## Inbyggd AI

Appen har en inbyggd bildförståelsemodell (CLIP ViT-B/32 från OpenAI, MIT-licens, körs lokalt
via onnxruntime – inget laddas upp). Den används för att:
- känna igen motiv (sköldpadda, dykare, rev, fiskstim, haj, rocka …),
- bedöma hur **sevärd** (finns det ett motiv, eller bara tomt vatten/sand?) och **snygg** varje bild är,
- välja **bara höjdpunkterna** – filmen blir hellre kortare än utfylld,
- hitta i vilket utsnitt motivet syns när bilden beskärs till 9:16.

Skärpan mäts brusokänsligt (partiklar och sensorbrus räknas inte som skärpa) och jämförs både
mellan klipp och inom varje klipp, så att fokusletande och suddiga ögonblick hoppas över.

**Analysrapport:** knappen *Exportera analysrapport* i analysvyn sparar en liten zip (inga filmer)
med analysvärden och en bild per klipp – bra underlag för att justera gränserna.

Modellpaketet byggs av `.github/workflows/models.yml` (prompterna finns i `packaging/ai_prompts.json`).

## Insta360

Exportera platta (reframade) MP4-filer från Insta360 Studio och importera dem.
Råa `.insv`-filer känns igen och märks "360 – exportera platt", men används inte i v0.1.

## Motivigenkänning (valfritt)

Utan extra paket hittar programmet liknande klipp med färg och bildinnehåll och märker
klipp som "Undervatten" eller "Ovan ytan". För att känna igen motiv som sköldpadda,
rev, dykare och fiskstim:
```
source .venv/bin/activate          # Windows: .venv\\Scripts\\activate
pip install -r requirements-ai.txt
```
Starta om och välj **Analysera om allt**. Modellen (CLIP, cirka 600 MB) laddas ner första gången
och körs lokalt på Apple Silicon (MPS) eller Nvidia-grafikkort (CUDA). För CUDA på Windows: installera torch enligt pytorch.org.

## Hur AI:n väljer klipp

- Varje klipp provas cirka 4 gånger per sekund. Kvalitet = skärpa (45 %), exponering (30 %), stabilitet (25 %).
- Varje stil har egna vikter (`dehazeiq/config.py`): klipplängd, hur ofta klipp läggs på taktslag,
  syn på rörelse, variation och slump.
- Urvalet sker med sannolikheter som belönar kvalitet och straffar likhet med redan valda klipp.
- Ordningen följer intro → uppbyggnad → höjdpunkt (cirka 70 %) → avslut.
- Musikens tempo hittas med spektralanalys; klippen läggs ibland – inte alltid – på taktslagen.
- Undervattensklipp får automatisk vitbalans (förstärkt rött) och 9:16 beskärs mot bildens detaljer.

## Test

```
python tests/smoke_test.py
```
Skapar syntetiska klipp och kör hela kedjan: import → analys → musik → förslag → förhandsvisning → export.

## Struktur

```
dehazeiq/
  app.py        lokal webbserver, API, filväljare och wifi-läge
  pipeline.py   bakgrundsjobb (import, analys, rendering)
  media.py      FFmpeg/ffprobe, proxyfiler, hårdvarukodning (Mac och Windows)
  analysis.py   bildanalys per klipp
  tagging.py    valfri CLIP-motivigenkänning
  music.py      tempo och taktslag
  generator.py  urval, ordning och klipplängder
  render.py     rendering med FFmpeg
  timeline.py   export till OpenTimelineIO
  photo.py      foton (JPG, HEIC, RAW) som stillbildsklipp
  cliptext.py   CLIP:s textdel och tokeniserare (sökning med egna ord)
  search.py     sökning i materialet
  prompt.py     beskrivning med egna ord → filmplan
  pano.py       360-film: AI-kamerabana, vyer, liten planet, kristallkula, 360-svep
  musiclib.py   musikbibliotek, Openverse, egna tjänster och licenser
  web/          gränssnittet (HTML/CSS/JS, logga)
```

## Nästa steg (enligt spec)

- Milstolpe 4–6: granskningsvy (byt/korta/flytta klipp), titlar och artnamn, speed ramps,
  zoom, fler effekter, plattformsprofiler och FCPXML.
