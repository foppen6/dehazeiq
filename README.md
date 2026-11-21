# DeHazeIQ – AI-powered video editing, without the hassle (v0.9)

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
  web/          gränssnittet (HTML/CSS/JS, logga)
```

## Nästa steg (enligt spec)

- Milstolpe 4–6: granskningsvy (byt/korta/flytta klipp), titlar och artnamn, speed ramps,
  zoom, fler effekter, plattformsprofiler och FCPXML.
