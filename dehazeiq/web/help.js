/* DeHazeIQ – hjälp: hur appen fungerar och alla kortkommandon. Öppnas med Hjälp-knappen eller ?/F1. */
"use strict";

const HELP = [
  { id: "start", title: "Kom igång", icon: "spark", body: `
    <p>DeHazeIQ gör färdiga filmer av dina dyk- och resklipp. Allt körs på din dator – inget laddas upp.</p>
    <ol class="hsteps">
      <li><b>Importera</b> – dra in en mapp eller filer, eller sätt i minneskortet. Välj vad filmen ska användas till (Reels, YouTube …).</li>
      <li><b>Analys</b> – AI:n tittar på varje klipp: skärpa, ljus, stabilitet, vilka djur och vad som händer. Svaga klipp väljs bort automatiskt.</li>
      <li><b>Förslag</b> – du får flera färdiga filmer i olika stilar, med musik, texter och färg. Stjärnmärk de du gillar.</li>
      <li><b>Redigera</b> – justera det du vill: klipp, ordning, texter, färg, musik, beskärning.</li>
      <li><b>Exportera</b> – välj plattformar och upplösning. Filerna hamnar i projektmappen.</li>
    </ol>
    <p class="muted">Snabbast: spara dina vanliga val som en <b>mall</b> – sedan räcker ett klick från import till färdig export.</p>` },
  { id: "import", title: "Importera och minneskort", icon: "upload", body: `
    <ul>
      <li><b>Nytt projekt:</b> dra in en mapp eller filer, eller välj <i>+ Nytt projekt</i>. Varje projekt får en egen flik överst.</li>
      <li><b>Minneskort och kameror:</b> sätt i SD-kortet eller koppla in Insta360/GoPro – en rad längst ner visar hur många <i>nya</i> klipp som finns. Klipp som redan finns i något projekt hoppas över.</li>
      <li><b>360-film</b> (Insta360 X4): AI:n väljer vyer automatiskt och gör vanliga klipp av dem.</li>
      <li><b>Flyttade filer:</b> står det <i>Original saknas</i>, tryck <b>Hitta filen</b> – övriga filer i samma mapp hittas automatiskt.</li>
      <li><b>Dykdata:</b> lägg till dyklogg (Subsurface, UDDF, Suunto) för djup och temperatur i texterna.</li>
    </ul>` },
  { id: "analyze", title: "Analys och urval", icon: "search", body: `
    <ul>
      <li><b>Spola</b> genom ett klipp genom att dra musen över bilden. <b>Klicka</b> för att spela det – du ser bästa sekvensen, vad AI:n ser och varför ett klipp valts bort.</li>
      <li><b>Måste med</b> (F) – AI:n bygger filmen runt klippet. <b>Välj bort</b> (X) – används aldrig. <b>Låt AI avgöra</b> (A).</li>
      <li><b>Markera flera</b> med rutan i hörnet (Skift-klick för flera i rad) och ändra alla på en gång.</li>
      <li><b>Gör film av markerade klipp:</b> markera klippen och tryck <i>Gör film av klippen</i> – välj längd, format och stil, så klipper AI:n ihop dem.</li>
      <li><b>Sök</b> i materialet med egna ord: "bläckfisk", "dykare med lampa", "solnedgång".</li>
      <li><b>Kompakt</b> visar fler klipp per skärm.</li>
    </ul>` },
  { id: "proposals", title: "Förslag", icon: "film", body: `
    <ul>
      <li>Varje omgång förslag hamnar överst med märket <i>Ny</i>. Gamla omgångar ligger kvar längre ner.</li>
      <li><b>Förhandsvisa</b> spelar filmen. <b>Stjärnan</b> gör den till favorit, <b>papperskorgen</b> tar bort den.</li>
      <li><b>Jämför</b> (ikonen med två rutor) – välj två förslag och spela dem sida vid sida.</li>
      <li><b>Fler varianter</b> gör nya versioner av samma film. <b>Generera nya förslag</b> gör en ny omgång.</li>
      <li><b>Beskriv filmen</b> med egna ord: "en lugn film om bläckfiskarna, 30 sekunder".</li>
      <li><b>Börja om</b> tar bort alla förslag (välj om favoriterna ska behållas). <b>Kompakt lista</b> visar en rad per förslag.</li>
    </ul>` },
  { id: "edit", title: "Redigera", icon: "pen", body: `
    <ul>
      <li><b>Tidslinjen</b> ligger under bilden. Den röda markören visar var du är – dra i linjalen för att spola, mellanslag spelar.</li>
      <li><b>Dela och kapa vid markören:</b> S delar klippet, Q kapar början, W kapar slutet.</li>
      <li><b>Byt ordning</b> genom att dra klippen. <b>Klippbanken</b> under tidslinjen visar bra sekvenser som inte används – dra in dem.</li>
      <li><b>Texter:</b> alla texter finns på ett ställe under fliken Text. T lägger en ny text vid markören. Dra texten i tidslinjen för att flytta den.</li>
      <li><b>Färg:</b> färdiga looks, före/efter och <i>färgmatchning</i> så att alla klipp ser lika ut.</li>
      <li><b>Beskärning:</b> AI:n beskär tajt eller zoomar ut till formatet – justera per klipp.</li>
      <li><b>Musik:</b> välj låt i menyn eller <i>Annan låt (AI väljer)</i> – klippen flyttas till nya takten.</li>
      <li>Allt går att <b>ångra</b> (⌘Z / Ctrl+Z).</li>
    </ul>` },
  { id: "export", title: "Exportera", icon: "download", body: `
    <ul>
      <li><b>Exportera</b> på förslagskortet eller i redigeraren öppnar en ruta med plattformar, upplösning och språk. Valen sparas till nästa gång.</li>
      <li><b>Exportera favoriter</b> exporterar alla stjärnmärkta förslag på en gång.</li>
      <li>Exporterna körs i bakgrunden – du får ett ljud och en notis när de är klara.</li>
      <li>Texter kan exporteras på flera språk. Musikens upphovsrätt (CC BY) skrivs automatiskt i en textfil bredvid filmen.</li>
    </ul>` },
  { id: "templates", title: "Mallar", icon: "layers", body: `
    <ul>
      <li><b>Spara valen som mall</b> (på importsidan eller "Vad vill du göra?"): filmtyper, format, längd, effekter och – om du vill – automatisk export.</li>
      <li><b>Kör</b> på mallen gör import, analys, förslag och export i ett svep. Mallar går också att välja direkt när ett minneskort sätts i.</li>
    </ul>` },
  { id: "music", title: "Musik", icon: "music", body: `
    <ul>
      <li>AI:n väljer låt ur musikbiblioteket efter stil, tempo, energi och genre – och växlar så att filmerna inte låter likadant.</li>
      <li>Under <b>Musik</b> lägger du till egna mappar eller trycker <b>Fler genrer</b> för gratis musik (CC0/CC BY).</li>
      <li>Musiken sänks automatiskt när någon pratar i klippen.</li>
    </ul>` },
  { id: "queue", title: "Kö, mobil och uppdateringar", icon: "queue", body: `
    <ul>
      <li><b>Kö</b> visar allt som pågår i alla projekt. Jobb kan flyttas, avbrytas och köras igen om programmet stängdes mitt i.</li>
      <li><b>Mobil</b> – styr DeHazeIQ från mobilen eller surfplattan via wifi (granska, stjärnmärk, exportera).</li>
      <li>När en ny version finns visas en rad med länk.</li>
    </ul>` },
  { id: "tips", title: "Tips och felsökning", icon: "spark", body: `
    <ul>
      <li><b>Filmerna blir lika?</b> Lägg till fler låtar (Fler genrer), stjärnmärk olika klipp, eller beskriv filmen med egna ord.</li>
      <li><b>Ett bra klipp kommer inte med?</b> Tryck F (Måste med) på det i analysen.</li>
      <li><b>Analysen tar lång tid?</b> Det är AI-modellen som tittar på bilderna. Fortsätt arbeta – du får en notis.</li>
      <li><b>Konstiga färger under vattnet?</b> Prova en annan look under Färg, eller "Original" för att se hur det filmades.</li>
      <li>Loggfilen <code>dehazeiq.log</code> ligger i programmets mapp om något går fel.</li>
    </ul>` },
];

const SHORTCUTS = [
  { group: "Överallt", rows: [["? / F1", "Öppna hjälpen"], ["Esc", "Stäng rutor"]] },
  { group: "Analys", rows: [["F", "Måste med (av/på)"], ["X", "Välj bort (av/på)"], ["A", "Låt AI avgöra"], ["Enter / klick", "Spela klippet"], ["Mellanslag", "Markera klippet"], ["Skift-klick", "Markera flera i rad"], ["⌘A / Ctrl+A", "Markera alla"], ["← → ↑ ↓", "Gå mellan klippen"]] },
  { group: "Spela upp ett klipp (analys)", rows: [["← / →", "Föregående / nästa klipp"], ["Mellanslag", "Spela / pausa"], ["F / X", "Måste med / Välj bort"]] },
  { group: "Redigeraren – spela och spola", rows: [["Mellanslag / K", "Spela / pausa"], ["L", "Spela – igen för 2× och 4×"], ["J", "Två sekunder bakåt"], [", / .", "En bildruta bakåt / framåt"], ["Dra i linjalen", "Spola"]] },
  { group: "Redigeraren – klippa", rows: [["S", "Dela klippet vid markören"], ["Q", "Kapa början fram till markören"], ["W", "Kapa slutet från markören"], ["T", "Ny text vid markören"], ["← / →", "Föregående / nästa klipp"], ["Alt + ← / →", "Flytta klippet"], ["Delete ×2", "Ta bort klippet"], ["⌘Z / Ctrl+Z", "Ångra"]] },
  { group: "Jämför förslag", rows: [["Mellanslag", "Spela / pausa båda"]] },
];

function helpTabFor(view) {
  return { import: "import", setup: "import", analyze: "analyze", proposals: "proposals", edit: "edit", export: "export", music: "music", queue: "queue" }[view] || "start";
}

function openHelp(section) {
  state.help = { tab: section || state.help && state.help.tab || helpTabFor(state.view), q: "" };
  drawHelp();
}
function drawHelp() {
  const h = state.help;
  const m = $("#modal");
  const q = (h.q || "").trim().toLowerCase();
  const strip = (html) => html.replace(/<[^>]+>/g, " ").toLowerCase();
  const hits = q ? HELP.filter((s) => (s.title + strip(s.body)).toLowerCase().includes(q)) : null;
  const scHits = q ? SHORTCUTS.map((g) => ({ ...g, rows: g.rows.filter(([k, v]) => `${k} ${v} ${g.group}`.toLowerCase().includes(q)) })).filter((g) => g.rows.length) : null;
  const nav = [...HELP.map((s) => [s.id, s.title]), ["keys", "Kortkommandon"]].map(([id, t]) =>
    `<button class="hnav ${!q && h.tab === id ? "on" : ""}" data-helptab="${id}">${esc(t)}</button>`).join("");
  const shortcuts = (groups) => groups.map((g) => `<section class="hkgroup"><h4>${esc(g.group)}</h4><dl class="kbd">${g.rows.map(([k, v]) => `<dt><kbd>${esc(k)}</kbd></dt><dd>${esc(v)}</dd>`).join("")}</dl></section>`).join("");
  let content;
  if (q) {
    content = (hits.length || scHits.length)
      ? hits.map((s) => `<section class="hsec"><h3>${esc(s.title)}</h3>${s.body}</section>`).join("") + (scHits.length ? `<section class="hsec"><h3>Kortkommandon</h3><div class="hkgrid">${shortcuts(scHits)}</div></section>` : "")
      : `<p class="muted">Inget hittades för "${esc(h.q)}".</p>`;
  } else if (h.tab === "keys") {
    content = `<section class="hsec"><h3>Kortkommandon</h3><div class="hkgrid">${shortcuts(SHORTCUTS)}</div></section>`;
  } else {
    const s = HELP.find((x) => x.id === h.tab) || HELP[0];
    const k = HELP.indexOf(s);
    content = `<section class="hsec"><h3>${esc(s.title)}</h3>${s.body}</section>
      <div class="row" style="justify-content:space-between;margin-top:8px">
        ${k > 0 ? `<button class="btn small" data-helptab="${HELP[k - 1].id}">← ${esc(HELP[k - 1].title)}</button>` : "<span></span>"}
        ${k < HELP.length - 1 ? `<button class="btn small" data-helptab="${HELP[k + 1].id}">${esc(HELP[k + 1].title)} →</button>` : `<button class="btn small" data-helptab="keys">Kortkommandon →</button>`}</div>`;
  }
  const hadFocus = document.activeElement && document.activeElement.id === "helpQ";
  m.innerHTML = `<div class="modal-card helpmodal" role="dialog" aria-modal="true" aria-labelledby="helpTitle">
    <div class="row helphead" style="gap:12px;flex-wrap:nowrap"><h2 id="helpTitle" style="font-size:19px;flex:none">Hjälp</h2>
      <input class="field" id="helpQ" type="search" placeholder="Sök i hjälpen …" value="${esc(h.q || "")}" aria-label="Sök i hjälpen" style="flex:1 1 auto;min-width:0;max-width:340px;margin-left:auto">
      <button class="btn icon small" data-act="modal-close" aria-label="Stäng">${svgi(ICO.x, 16)}</button></div>
    <div class="helpbody"><nav class="helpnav" aria-label="Avsnitt">${nav}</nav><div class="helpcontent">${content}</div></div>
    <p class="muted" style="margin:0;font-size:12px">Tryck <kbd>?</kbd> eller <kbd>F1</kbd> var som helst för att öppna hjälpen. DeHazeIQ ${esc((state.info && state.info.version) || "")}</p></div>`;
  m.hidden = false;
  if (hadFocus) { const i = document.getElementById("helpQ"); i.focus(); i.setSelectionRange(i.value.length, i.value.length); }
  const on = m.querySelector(".hnav.on"); if (on) on.scrollIntoView({ block: "nearest", inline: "center" });
}
document.addEventListener("click", (ev) => {
  const t = ev.target.closest("[data-helptab], [data-act='help'], [data-helpopen]");
  if (!t) return;
  ev.preventDefault(); ev.stopPropagation();
  if (t.dataset.act === "help") return openHelp(helpTabFor(state.view));
  if (t.dataset.helpopen) return openHelp(t.dataset.helpopen);
  if (!state.help || !document.querySelector(".helpmodal")) return openHelp(t.dataset.helptab);
  state.help.tab = t.dataset.helptab; state.help.q = "";
  drawHelp();
  const c = document.querySelector(".helpcontent"); if (c) c.scrollTop = 0;
}, true);
document.addEventListener("input", (ev) => {
  if (ev.target.id === "helpQ" && state.help && !$("#modal").hidden) { state.help.q = ev.target.value; drawHelp(); }
});
// ? eller F1 öppnar hjälpen – utom där ? redan visar vyns egna kortkommandon (de pekar hit)
document.addEventListener("keydown", (ev) => {
  if (ev.target.closest && ev.target.closest("input, textarea, select, [contenteditable]")) return;
  if (ev.key === "F1" || (ev.key === "?" && !["edit", "analyze"].includes(state.view))) {
    if (!$("#modal").hidden && document.querySelector(".helpmodal")) return;
    ev.preventDefault(); ev.stopPropagation();
    openHelp(ev.key === "?" ? "keys" : undefined);
  }
}, true);
document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape" && !$("#modal").hidden && document.querySelector(".helpmodal")) { ev.preventDefault(); $("#modal").hidden = true; }
}, true);
