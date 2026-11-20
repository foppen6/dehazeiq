# DeHazeIQ – AI-powered video editing, without the hassle (v0.3)

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

- Skapa ett projekt och klicka **Välj mapp**. Analysen startar automatiskt efter importen.
- Välj format (9:16, 16:9, 1:1, 4:5), längd, stil och musik i högerpanelen.
- I analysvyn kan du markera klipp som **Måste med** (favoriter) eller **Välj bort**.
- **Skapa 3 filmförslag** ger tre versioner. Varje klick på "Generera nya förslag" eller
  ↻ på ett kort ger ett nytt urval – materialet behöver inte analyseras om.
- **Förhandsvisa** renderar snabbt från proxyfilerna.
- **Exportera** renderar från originalfilerna i 720p, 1080p eller 4K och skapar samtidigt en `.otio`-tidslinje.
  I DaVinci Resolve: *Arkiv › Importera › Tidslinje …* och välj `.otio`-filen.

Projekten sparas i `~/DeHazeIQ/projects/` – på Windows `C:\Users\<namn>\DeHazeIQ\projects` (ändra med miljövariabeln `DEHAZEIQ_HOME`).

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
