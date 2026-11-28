/* DeHazeIQ – snabbare arbetsflöde: direktexport, favoriter, mallar och notiser.
   Delar globaler med app.js och studio.js. */
"use strict";

/* ================= exportval som kommer ihåg sig ================= */
function exportPrefs() {
  let pr = null;
  try { pr = JSON.parse(localStorage.getItem("tv.exportPrefs") || "null"); } catch (_) { /* privat läge */ }
  const pfs = platforms();
  pr = pr && typeof pr === "object" ? pr : {};
  return {
    platforms: (pr.platforms || []).filter((k) => pfs[k]),
    resolution: ["720p", "1080p", "4k"].includes(pr.resolution) ? pr.resolution : "1080p",
    langs: (pr.langs && pr.langs.length ? pr.langs : ["sv"]),
  };
}
function saveExportPrefs(pr) {
  try { localStorage.setItem("tv.exportPrefs", JSON.stringify(pr)); } catch (_) { /* */ }
}
function defaultPlatFor(p) {
  const pfs = platforms();
  return p.platform && pfs[p.platform] ? p.platform : Object.keys(pfs).find((k) => pfs[k].format === p.format);
}

/* ================= exportruta (från kortet, redigeraren och favoriter) ================= */
function openExportModal(ids) {
  const props = ids.map(propById).filter(Boolean);
  if (!props.length) return;
  const pr = exportPrefs();
  const plats = pr.platforms.length ? pr.platforms : [defaultPlatFor(props[0])].filter(Boolean);
  state.xm = { ids: props.map((p) => p.id), platforms: plats, resolution: pr.resolution, langs: pr.langs };
  drawExportModal();
}
function drawExportModal() {
  const xm = state.xm;
  if (!xm) return;
  const props = xm.ids.map(propById).filter(Boolean);
  const pfs = platforms();
  const langs = (state.info && state.info.languages) || { sv: "Svenska" };
  const n = props.length * xm.platforms.length * xm.langs.length;
  const title = props.length === 1 ? `Exportera "${esc(props[0].title || props[0].style_label)}"` : `Exportera ${props.length} favoriter`;
  const m = $("#modal");
  m.innerHTML = `<div class="modal-card xmodal" role="dialog" aria-modal="true" aria-labelledby="xmTitle">
    <h2 id="xmTitle" style="font-size:18px">${title}</h2>
    ${props.length > 1 ? `<div class="xmlist">${props.map((p) => `<span class="tag">${esc(p.title || p.style_label)} · ${fmtDur(p.length)}</span>`).join("")}</div>` : ""}
    <div class="stack" style="gap:8px"><b style="font-size:14px">Plattformar</b>
      <div class="chips">${Object.entries(pfs).map(([k, pf]) => `<button class="chip" data-xmplat="${k}" aria-pressed="${xm.platforms.includes(k)}">${esc(pf.label)} <span class="muted">· ${pf.format}</span></button>`).join("")}</div></div>
    <div class="stack" style="gap:8px"><b style="font-size:14px">Upplösning</b>
      <div class="seg" role="group" aria-label="Upplösning" style="grid-template-columns:repeat(3,minmax(0,1fr));max-width:360px">${[["720p", "720p"], ["1080p", "1080p"], ["4k", "4K"]].map(([k, l]) => `<button data-xmres="${k}" aria-pressed="${xm.resolution === k}">${l}</button>`).join("")}</div></div>
    <details ${xm.langs.length > 1 || xm.langs[0] !== "sv" ? "open" : ""}><summary style="cursor:pointer;font-size:14px;font-weight:600">Språk för texterna (${xm.langs.length})</summary>
      <div class="chips" style="margin-top:8px">${Object.entries(langs).map(([k, l]) => `<button class="chip" data-xmlang="${k}" aria-pressed="${xm.langs.includes(k)}">${esc(l)}</button>`).join("")}</div></details>
    <p class="muted" style="margin:0;font-size:13px">Valen sparas till nästa gång. Exporterna körs i bakgrunden – du kan fortsätta arbeta.</p>
    <div class="row" style="justify-content:flex-end;flex-wrap:wrap">
      ${props.length === 1 ? `<button class="btn" data-xmmore="${props[0].id}">Fler exportval</button>` : ""}
      <button class="btn" data-act="modal-close">Avbryt</button>
      <button class="btn primary" data-xmgo ${n ? "" : "disabled"}>${n > 1 ? `Lägg ${n} exporter i kön` : "Lägg i kön"}</button></div></div>`;
  m.hidden = false;
}
async function exportModalGo() {
  const xm = state.xm;
  if (!xm) return;
  saveExportPrefs({ platforms: xm.platforms, resolution: xm.resolution, langs: xm.langs });
  try {
    const r = xm.ids.length === 1
      ? await api("POST", `/api/p/${state.pid}/proposal/${xm.ids[0]}/export`, { platforms: xm.platforms, resolution: xm.resolution, langs: xm.langs })
      : await api("POST", `/api/p/${state.pid}/exportmany`, { ids: xm.ids, platforms: xm.platforms, resolution: xm.resolution, langs: xm.langs });
    $("#modal").hidden = true;
    state.xm = null;
    askNotify();
    toast(`${r.queued} export${r.queued === 1 ? "" : "er"} i kön. Du får en notis när de är klara.`, true);
    loadQueue();
  } catch (e) { fail(e); }
}
document.addEventListener("click", (ev) => {
  const t = ev.target.closest("[data-xmplat], [data-xmres], [data-xmlang], [data-xmgo], [data-xmmore], [data-qexport], [data-favexport], [data-edexport]");
  if (!t) return;
  const d = t.dataset, xm = state.xm;
  ev.preventDefault(); ev.stopPropagation();
  if (d.qexport) return openExportModal([d.qexport]);
  if (d.edexport !== undefined) return openExportModal([state.ed.prop]);
  if (d.favexport !== undefined) return openExportModal((P().proposals || []).filter((p) => p.favorite).map((p) => p.id));
  if (!xm) return undefined;
  const toggle = (arr, k) => (arr.includes(k) ? arr.filter((x) => x !== k) : [...arr, k]);
  if (d.xmplat) xm.platforms = toggle(xm.platforms, d.xmplat);
  else if (d.xmlang) { xm.langs = toggle(xm.langs, d.xmlang); if (!xm.langs.length) xm.langs = ["sv"]; }
  else if (d.xmres) xm.resolution = d.xmres;
  else if (d.xmgo !== undefined) return exportModalGo();
  else if (d.xmmore) {
    saveExportPrefs({ platforms: xm.platforms, resolution: xm.resolution, langs: xm.langs });
    $("#modal").hidden = true; state.xm = null;
    state.exportProp = d.xmmore; state.exportPlats = null; state.view = "export";
    return render();
  }
  return drawExportModal();
}, true);

/* ================= notiser när långa jobb blir klara ================= */
let notifyAsked = false;
function askNotify() {
  if (notifyAsked || remote() || !("Notification" in window)) return;
  notifyAsked = true;
  if (Notification.permission === "default") Notification.requestPermission().catch(() => {});
}
document.addEventListener("click", (ev) => {  // fråga om lov vid första långa jobbet
  if (ev.target.closest && ev.target.closest('[data-act="auto"], [data-act="setup-go"], [data-act="export-queue"], [data-act="generate"], [data-tplrun], [data-act="analyze"]')) askNotify();
}, true);

function chime() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    [[660, 0], [880, 0.16]].forEach(([f, at]) => {
      const o = ctx.createOscillator(), g = ctx.createGain();
      o.frequency.value = f; o.type = "sine";
      g.gain.setValueAtTime(0.0001, ctx.currentTime + at);
      g.gain.exponentialRampToValueAtTime(0.18, ctx.currentTime + at + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + at + 0.5);
      o.connect(g); g.connect(ctx.destination); o.start(ctx.currentTime + at); o.stop(ctx.currentTime + at + 0.55);
    });
    setTimeout(() => ctx.close(), 1200);
  } catch (_) { /* inget ljud */ }
}
let seenActive = null, notifyBatch = [], notifyTimer = null, baseTitle = document.title;
function watchFinished(q) {
  const active = new Set((q.tasks || []).map((t) => t.id));
  if (seenActive) {
    const finished = (q.done || []).filter((t) => seenActive.has(t.id) && !active.has(t.id) && t.kind !== "render:preview" && !String(t.kind).startsWith("render:preview"));
    finished.forEach((t) => notifyBatch.push(t));
    if (finished.length && !notifyTimer) notifyTimer = setTimeout(flushNotify, 1500);  // samla ihop flera exporter
  }
  seenActive = active;
}
function flushNotify() {
  notifyTimer = null;
  const list = notifyBatch.splice(0);
  if (!list.length) return;
  const errs = list.filter((t) => t.state === "error");
  const ok = list.filter((t) => t.state === "done");
  const exports = ok.filter((t) => String(t.kind).startsWith("render:"));
  let title, body;
  if (errs.length) { title = "Något gick fel"; body = `${errs[0].label}: ${errs[0].message || ""}`; }
  else if (exports.length && exports.length === ok.length) { title = `${exports.length} export${exports.length === 1 ? "" : "er"} klar${exports.length === 1 ? "" : "a"}`; body = exports.map((t) => t.label.replace(/^Export /, "")).slice(0, 3).join("\n"); }
  else if (ok.length) { title = ok.length === 1 ? `${ok[0].label} är klart` : `${ok.length} jobb är klara`; body = ok.map((t) => t.project).filter((v, i, a) => a.indexOf(v) === i).join(", "); }
  else return;
  if (!state.mute) chime();
  if (document.hidden) {
    document.title = `✓ ${title} – DeHazeIQ`;
    if ("Notification" in window && Notification.permission === "granted") {
      try { const n = new Notification(`DeHazeIQ: ${title}`, { body, tag: "dehazeiq-job", silent: true }); n.onclick = () => { window.focus(); n.close(); }; } catch (_) { /* */ }
    }
  } else if (exports.length) {
    toast(`${title}. Filerna finns under Exportera.`, true);
  }
}
document.addEventListener("visibilitychange", () => { if (!document.hidden) document.title = baseTitle; });

/* ================= mallar ================= */
state.templates = null;
async function loadTemplates() {
  try { state.templates = (await api("GET", "/api/templates")).templates || []; } catch (_) { state.templates = []; }
  return state.templates;
}
function templatesBar(where) {
  if (remote()) return "";
  if (state.templates === null) { loadTemplates().then(() => render()); return ""; }
  const ts = state.templates;
  const rows = ts.map((t) => `<div class="tplrow"><span class="grow"><b>${esc(t.name)}</b><small class="muted">${esc(t.text || "")}</small></span>
      <button class="btn small primary" data-tplrun="${esc(t.id)}" title="${where === "new" ? "Importera och kör med mallens inställningar" : "Kör hela flödet med mallens inställningar"}">${icon("play", 13)}Kör</button>
      <button class="btn icon small" data-tpldel="${esc(t.id)}" aria-label="Ta bort mallen ${esc(t.name)}" title="Ta bort mallen">${svgi(ICO.x, 14)}</button></div>`).join("");
  return `<section class="box stack tplbox" style="gap:10px">
    <div class="spread"><b>Mina mallar</b><button class="btn small" data-tplsave="${where}">Spara valen som mall</button></div>
    ${rows || '<p class="muted" style="margin:0;font-size:13px">Spara dina vanliga val (filmtyper, plattformar, längd och export) som en mall – sedan räcker ett klick: import, analys, förslag och export i ett svep.</p>'}
  </section>`;
}
function openTemplateSave(where) {
  const pr = exportPrefs();
  const pfs = platforms();
  state.tpl = { where, auto: !!pr.platforms.length, which: "best", platforms: pr.platforms.length ? pr.platforms : ["reels"].filter((k) => pfs[k]), resolution: pr.resolution, langs: pr.langs };
  drawTemplateSave();
}
function drawTemplateSave() {
  const tp = state.tpl, pfs = platforms();
  const m = $("#modal");
  const nameVal = (document.getElementById("tplName") || {}).value || tp.name || "";
  m.innerHTML = `<form class="modal-card xmodal" id="tplForm" role="dialog" aria-modal="true" aria-labelledby="tplTitle">
    <h2 id="tplTitle" style="font-size:18px">Spara som mall</h2>
    <p class="muted" style="margin:0;font-size:13px">${tp.where === "project" ? "Projektets filmtyper, format, längd och effekter sparas." : "Filmtyperna du valt på sidan sparas."}</p>
    <label class="stack" style="gap:6px;font-size:13px;color:var(--text-2)">Namn<input class="field" id="tplName" maxlength="60" value="${esc(nameVal)}" placeholder="T.ex. Mitt dykreel" required></label>
    <label class="row" style="gap:10px"><input type="checkbox" id="tplAuto" ${tp.auto ? "checked" : ""} style="width:18px;height:18px;accent-color:var(--accent)">Exportera automatiskt när förslagen är klara</label>
    ${tp.auto ? `<div class="stack" style="gap:8px;padding-left:28px">
      <div class="seg" role="group" aria-label="Vilka förslag" style="grid-template-columns:repeat(2,minmax(0,1fr));max-width:360px">
        <button type="button" data-tplwhich="best" aria-pressed="${tp.which === "best"}">Bästa förslaget</button><button type="button" data-tplwhich="all" aria-pressed="${tp.which === "all"}">Alla förslag</button></div>
      <div class="chips">${Object.entries(pfs).map(([k, pf]) => `<button type="button" class="chip" data-tplplat="${k}" aria-pressed="${tp.platforms.includes(k)}">${esc(pf.label)}</button>`).join("")}</div>
      <div class="seg" role="group" aria-label="Upplösning" style="grid-template-columns:repeat(3,minmax(0,1fr));max-width:300px">${[["720p", "720p"], ["1080p", "1080p"], ["4k", "4K"]].map(([k, l]) => `<button type="button" data-tplres="${k}" aria-pressed="${tp.resolution === k}">${l}</button>`).join("")}</div></div>` : ""}
    <div class="row" style="justify-content:flex-end"><button class="btn" type="button" data-act="modal-close">Avbryt</button><button class="btn primary" type="submit">Spara mallen</button></div></form>`;
  m.hidden = false;
  const inp = document.getElementById("tplName");
  if (inp && !nameVal) inp.focus();
}
async function saveTemplate() {
  const tp = state.tpl;
  const name = (document.getElementById("tplName") || {}).value || "";
  const exp = { auto: tp.auto, which: tp.which, platforms: tp.platforms, resolution: tp.resolution, langs: tp.langs };
  const body = { name, export: exp };
  if (tp.where === "project") body.pid = state.pid;
  else body.settings = { plans: setupPlans(), previews: $("#setupPrev") ? $("#setupPrev").checked : true };
  try {
    const r = await api("POST", "/api/templates", body);
    state.templates = r.templates; state.tpl = null;
    $("#modal").hidden = true;
    toast(`Mallen "${r.template.name}" är sparad.`, true);
    render();
  } catch (e) { fail(e); }
}
async function runTemplate(id) {
  const t = (state.templates || []).find((x) => x.id === id);
  if (!t) return;
  askNotify();
  try {
    if (state.view === "setup" && state.setup && state.setup.mode === "new") {
      const name = $("#setupName") ? $("#setupName").value.trim() : "";
      const p = await api("POST", "/api/import", { paths: state.setup.paths, name, template: id });
      state.expectJob = true;
      await loadProjects(); await loadProject(p.id);
    } else {
      await api("POST", `/api/p/${state.pid}/template`, { id });
      state.expectJob = true;
      await loadProject(state.pid);
    }
    toast(`Kör med mallen "${t.name}"${(t.export || {}).auto ? " – exporterna läggs i kön när förslagen är klara" : ""}.`, true);
    state.view = "proposals";
    await pollJob();
    render();
  } catch (e) { fail(e); }
}
document.addEventListener("click", async (ev) => {
  const t = ev.target.closest("[data-tplrun], [data-tpldel], [data-tplsave], [data-tplwhich], [data-tplplat], [data-tplres]");
  if (!t) return;
  ev.preventDefault();
  const d = t.dataset;
  if (d.tplrun) return runTemplate(d.tplrun);
  if (d.tplsave) return openTemplateSave(d.tplsave);
  if (d.tpldel) {
    if (state.tplDelAsk !== d.tpldel) { state.tplDelAsk = d.tpldel; t.classList.add("danger"); t.title = "Tryck igen för att ta bort"; setTimeout(() => { state.tplDelAsk = null; }, 2500); return undefined; }
    state.templates = (await api("POST", `/api/templates/${d.tpldel}/delete`, {})).templates;
    return render();
  }
  const tp = state.tpl;
  if (!tp) return undefined;
  if (d.tplwhich) tp.which = d.tplwhich;
  if (d.tplplat) tp.platforms = tp.platforms.includes(d.tplplat) ? tp.platforms.filter((x) => x !== d.tplplat) : [...tp.platforms, d.tplplat];
  if (d.tplres) tp.resolution = d.tplres;
  return drawTemplateSave();
});
document.addEventListener("change", (ev) => {
  if (ev.target.id === "tplAuto" && state.tpl) { state.tpl.auto = ev.target.checked; drawTemplateSave(); }
});
document.addEventListener("submit", (ev) => {
  if (ev.target.id === "tplForm") { ev.preventDefault(); saveTemplate(); }
});

/* ================= minneskort och kameror ================= */
state.cards = [];
async function pollCards() {
  if (remote() || document.hidden) return;
  try { state.cards = (await api("GET", "/api/cards")).cards || []; } catch (_) { state.cards = []; }
  drawCardBar();
}
setInterval(pollCards, 6000);
setTimeout(pollCards, 2500);
function drawCardBar() {
  let bar = document.getElementById("cardbar");
  const c = (state.cards || []).find((x) => x.new > 0 && !(state.cardsHidden || []).includes(x.path));
  if (!c) { if (bar) bar.remove(); return; }
  if (!bar) { bar = document.createElement("div"); bar.id = "cardbar"; bar.className = "cardbar"; bar.setAttribute("role", "status"); document.body.appendChild(bar); }
  const key = `${c.path}|${c.new}|${(state.templates || []).length}|${state.pid}`;
  if (bar.dataset.key === key) return;
  bar.dataset.key = key;
  const tpls = (state.templates || []).map((t) => `<option value="${esc(t.id)}">Med mallen ${esc(t.name)}</option>`).join("");
  bar.innerHTML = `<span class="cbico">${svgi('<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 3v4M12 3v4M15 3v4"/>', 20)}</span>
    <span class="grow"><b>${esc(c.name)}</b> är inkopplat – <b>${c.new}</b> nya klipp${c.new_gb ? ` (${String(c.new_gb).replace(".", ",")} GB)` : ""}${c.files > c.new ? `, ${c.files - c.new} finns redan` : ""}.</span>
    ${tpls ? `<select class="selfield" id="cardTpl" aria-label="Mall"><option value="">Utan mall</option>${tpls}</select>` : ""}
    <button class="btn small primary" data-cardimp="new">Nytt projekt</button>
    ${P() ? `<button class="btn small" data-cardimp="${esc(state.pid)}">Lägg till i ${esc(P().name)}</button>` : ""}
    <button class="btn small" data-cardignore title="Fråga inte om det här kortet igen förrän programmet startas om">Inte nu</button>`;
}
document.addEventListener("click", async (ev) => {
  const t = ev.target.closest("[data-cardimp], [data-cardignore]");
  if (!t) return;
  const c = (state.cards || []).find((x) => x.new > 0 && !(state.cardsHidden || []).includes(x.path));
  if (!c) return;
  if (t.dataset.cardignore !== undefined) {
    state.cardsHidden = [...(state.cardsHidden || []), c.path];
    api("POST", "/api/cards/ignore", { path: c.path }).catch(() => {});
    return drawCardBar();
  }
  const tpl = ($("#cardTpl") || {}).value || "";
  askNotify();
  try {
    t.disabled = true;
    const p = await api("POST", "/api/cards/import", { path: c.path, to: t.dataset.cardimp, template: tpl });
    state.cardsHidden = [...(state.cardsHidden || []), c.path];
    drawCardBar();
    state.expectJob = true;
    await loadProjects();
    await loadProject(p.id || state.pid);
    state.view = "import";
    toast(`Importerar ${c.new} nya klipp från ${c.name}. Analys och förslag följer automatiskt.`, true);
    await pollJob();
    render();
  } catch (e) { t.disabled = false; fail(e); }
});

/* ================= snabbare analysvy: tangenter, flera klipp åt gången, kompakt ================= */
try { state.anCompact = localStorage.getItem("tv.anCompact") === "1"; } catch (_) { /* */ }
state.anSel = [];
function analysisTools(list) {
  state.anList = list.map((c) => c.id);
  return `<div class="row" style="gap:6px">
    <button class="btn small" data-anall title="Markera alla klipp som visas">Markera alla</button>
    <button class="btn small" data-ancompact aria-pressed="${!!state.anCompact}" title="Mindre kort – fler klipp på skärmen">${state.anCompact ? "Stora kort" : "Kompakt"}</button>
    <button class="btn small icon" data-ankeys title="Kortkommandon" aria-label="Kortkommandon">?</button></div>`;
}
function analysisBulkBar() {
  const n = (state.anSel || []).length;
  if (!n) return "";
  return `<div class="bulkbar" role="toolbar" aria-label="Markerade klipp"><b>${n} markerade</b>
    <button class="btn small" data-anbulk="favorite">${icon("star", 14)}Måste med</button>
    <button class="btn small" data-anbulk="excluded">${icon("eyeoff", 14)}Välj bort</button>
    <button class="btn small" data-anbulk="reset">Låt AI avgöra</button>
    <select class="selfield" data-anphase aria-label="Del av dyket" style="width:auto;height:32px"><option value="-">Del av dyket …</option><option value="">AI avgör</option><option value="start">Början</option><option value="mid">Under dyket</option><option value="end">Slutet</option></select>
    <span class="grow"></span><button class="btn small primary" data-fromclips title="AI:n klipper ihop de markerade klippen till färdiga filmer">${icon("spark", 14)}Gör film av ${n === 1 ? "klippet" : `de ${n} klippen`}</button>
    <button class="btn small" data-annone>Avmarkera</button></div>`;
}
async function setClips(ids, patch) {
  const cs = clips();
  for (let k = 0; k < ids.length; k += 8) {
    await Promise.all(ids.slice(k, k + 8).map(async (cid) => {
      try {
        const r = await api("POST", `/api/p/${state.pid}/clip/${cid}`, patch);
        const c = cs.find((x) => x.id === cid);
        if (c) Object.assign(c, r);
      } catch (_) { /* ett klipp som inte gick: fortsätt med resten */ }
    }));
  }
}
async function bulk(field, ids) {
  ids = ids && ids.length ? ids : state.anSel;
  if (!ids.length) return;
  const cs = clips().filter((c) => ids.includes(c.id));
  if (field === "reset") await setClips(ids, { favorite: false, excluded: false });
  else {
    const val = !cs.every((c) => c[field]);  // alla redan på → stäng av
    const patch = { [field]: val };
    if (val) patch[field === "favorite" ? "excluded" : "favorite"] = false;
    await setClips(ids, patch);
  }
  render();
  toast(`${ids.length} klipp ändrade.`, true);
}
function anFocused() {
  const el = document.activeElement && document.activeElement.closest && document.activeElement.closest(".ccard[data-cid]");
  return (el && el.dataset.cid) || state.anHover || null;
}
document.addEventListener("mouseover", (ev) => {
  if (state.view !== "analyze") return;
  const c = ev.target.closest && ev.target.closest(".ccard[data-cid]");
  state.anHover = c ? c.dataset.cid : state.anHover;
});
document.addEventListener("click", async (ev) => {
  const t = ev.target.closest("[data-csel], [data-anall], [data-annone], [data-ancompact], [data-anbulk], [data-ankeys]");
  if (!t || state.view !== "analyze") return;
  ev.preventDefault();
  const d = t.dataset;
  if (d.csel) {
    const list = state.anList || [];
    let sel = new Set(state.anSel);
    if (ev.shiftKey && state.anLast && list.includes(state.anLast)) {
      const a = list.indexOf(state.anLast), b = list.indexOf(d.csel);
      list.slice(Math.min(a, b), Math.max(a, b) + 1).forEach((id) => sel.add(id));
    } else if (sel.has(d.csel)) sel.delete(d.csel); else sel.add(d.csel);
    state.anSel = [...sel]; state.anLast = d.csel;
    return render();
  }
  if (d.anall !== undefined) { state.anSel = [...(state.anList || [])]; return render(); }
  if (d.annone !== undefined) { state.anSel = []; return render(); }
  if (d.ancompact !== undefined) { state.anCompact = !state.anCompact; try { localStorage.setItem("tv.anCompact", state.anCompact ? "1" : "0"); } catch (_) { /* */ } return render(); }
  if (d.anbulk) return bulk(d.anbulk);
  if (d.ankeys !== undefined) {
    const rows = [["F", "Måste med (av/på)"], ["X", "Välj bort (av/på)"], ["A", "Låt AI avgöra"], ["Mellanslag", "Markera klippet"], ["Skift-klick", "Markera flera i rad"], ["⌘A / Ctrl+A", "Markera alla"], ["← → ↑ ↓", "Gå mellan klippen"], ["Esc", "Avmarkera"]];
    const m = $("#modal");
    m.innerHTML = `<div class="modal-card" role="dialog" aria-modal="true" style="max-width:440px"><h2 style="font-size:18px">Kortkommandon i analysen</h2>
      <p class="muted" style="margin:0;font-size:13px">Gäller klippet du pekar på – eller alla markerade.</p>
      <dl class="kbd">${rows.map(([k, v]) => `<dt><kbd>${esc(k)}</kbd></dt><dd>${esc(v)}</dd>`).join("")}</dl>
      <div class="row" style="justify-content:flex-end"><button class="btn primary" data-act="modal-close">Stäng</button></div></div>`;
    m.hidden = false;
  }
  return undefined;
}, true);
document.addEventListener("change", async (ev) => {
  const t = ev.target;
  if (!t.matches || !t.matches("[data-anphase]") || t.value === "-") return;
  const ids = [...state.anSel];
  for (let k = 0; k < ids.length; k += 8) {
    await Promise.all(ids.slice(k, k + 8).map((cid) => api("POST", `/api/p/${state.pid}/clip/${cid}`, { phase: t.value || null }).then((r) => { const c = clips().find((x) => x.id === cid); if (c) c.phase_manual = r.phase_manual; }).catch(() => {})));
  }
  toast(`${ids.length} klipp: ${t.selectedOptions[0].textContent}.`, true);
  render();
});
document.addEventListener("keydown", (ev) => {
  if (state.view !== "analyze" || ev.target.closest("input, textarea, select") || ev.altKey) return;
  const k = ev.key.toLowerCase();
  if ((ev.metaKey || ev.ctrlKey) && k === "a") { ev.preventDefault(); state.anSel = [...(state.anList || [])]; return render(); }
  if (ev.metaKey || ev.ctrlKey) return undefined;
  if (k === "escape" && state.anSel.length) { state.anSel = []; return render(); }
  const cur = anFocused();
  const target = state.anSel.length ? state.anSel : (cur ? [cur] : []);
  if (k === "f" && target.length) { ev.preventDefault(); return bulk("favorite", target); }
  if (k === "x" && target.length) { ev.preventDefault(); return bulk("excluded", target); }
  if (k === "a" && target.length) { ev.preventDefault(); return bulk("reset", target); }
  if ((k === " " || ev.code === "Space") && cur && ev.target.closest(".ccard")) {
    ev.preventDefault();
    const sel = new Set(state.anSel);
    if (sel.has(cur)) sel.delete(cur); else sel.add(cur);
    state.anSel = [...sel]; state.anLast = cur; render();
    const el = document.querySelector(`.ccard[data-cid="${cur}"]`); if (el) el.focus();
    return undefined;
  }
  if (["arrowleft", "arrowright", "arrowup", "arrowdown"].includes(k) && ev.target.closest(".ccard, body")) {
    const cardsEl = [...document.querySelectorAll(".grid .ccard[data-cid]")];
    if (!cardsEl.length) return undefined;
    const idx = Math.max(0, cardsEl.findIndex((c) => c.dataset.cid === cur));
    const cols = Math.max(1, Math.round(cardsEl[0].parentElement.clientWidth / (cardsEl[0].getBoundingClientRect().width + 16)));
    const step = { arrowleft: -1, arrowright: 1, arrowup: -cols, arrowdown: cols }[k];
    const next = cardsEl[Math.max(0, Math.min(cardsEl.length - 1, idx + step))];
    ev.preventDefault();
    next.focus(); next.scrollIntoView({ block: "nearest" }); state.anHover = next.dataset.cid;
  }
  return undefined;
});

/* ================= förslag: kompakt lista och jämförelse ================= */
try { state.propCompact = localStorage.getItem("tv.propCompact") === "1"; } catch (_) { /* */ }
state.cmp = [];
function propRow(p) {
  const s0 = p.shots[0];
  const prev = p.renders && p.renders.preview;
  const fresh = state.fresh && state.fresh.has(p.id);
  return `<div class="prow ${p.favorite ? "fav" : ""}">
    <img alt="" loading="lazy" src="${s0 ? frameUrl(s0.clip_id, s0.src_start + s0.duration / 2, 160) : ""}">
    <span class="prinfo"><b>${esc(p.title || p.style_label)}${fresh ? ' <span class="newtag">Ny</span>' : ""}</b>
      <small class="muted">${esc(p.style_label)} · ${esc(p.format)} · ${fmtDur(p.length)} · ${p.n_shots} klipp${p.music_name ? ` · ${esc(p.music_name)}` : ""}</small></span>
    <span class="row practs">
      <button class="btn small icon favbtn" data-propfav="${p.id}" aria-pressed="${!!p.favorite}" aria-label="Favorit" title="Favorit">${icon("star", 15)}</button>
      <button class="btn small icon cmpbtn" data-cmp="${p.id}" aria-pressed="${state.cmp.includes(p.id)}" aria-label="Jämför" title="Jämför">${svgi('<rect x="3" y="4" width="8" height="16" rx="1.5"/><rect x="13" y="4" width="8" height="16" rx="1.5"/>', 15)}</button>
      ${prev ? `<button class="btn small" data-rowplay="${p.id}">${icon("play", 12)}Spela</button>` : `<button class="btn small" data-preview="${p.id}">Förhandsvisa</button>`}
      <button class="btn small" data-edit="${p.id}">Redigera</button>
      <button class="btn small" data-qexport="${p.id}">Exportera</button></span></div>`;
}
function compareBar() {
  const ids = (state.cmp || []).filter((id) => propById(id));
  state.cmp = ids;
  if (!ids.length) return "";
  return `<div class="bulkbar cmpbar"><b>Jämför:</b>${ids.map((id) => `<span class="tag">${esc(propById(id).title || propById(id).style_label)}</span>`).join("")}
    <span class="muted" style="font-size:13px">${ids.length < 2 ? "Välj ett förslag till" : ""}</span><span class="grow"></span>
    <button class="btn small primary" data-cmpopen ${ids.length === 2 ? "" : "disabled"}>Jämför sida vid sida</button><button class="btn small" data-cmpclear>Avbryt</button></div>`;
}
async function openCompare() {
  const ps = state.cmp.map(propById).filter(Boolean);
  if (ps.length !== 2) return;
  const missing = ps.filter((p) => !(p.renders && p.renders.preview));
  const m = $("#modal");
  const vid = (p) => (p.renders && p.renders.preview
    ? `<video class="cmpvid" playsinline preload="auto" src="${mediaUrl("renders", p.renders.preview)}?v=${p.renders.v || 0}"></video>`
    : `<div class="cmpwait"><div class="spinner"></div><span>Gör förhandsvisning …</span></div>`);
  m.innerHTML = `<div class="modal-card cmpmodal" role="dialog" aria-modal="true" aria-label="Jämför förslag">
    <div class="cmpgrid">${ps.map((p) => `<div class="cmpcol"><div class="cmpframe" style="aspect-ratio:${(p.format || "9:16").replace(":", "/")}">${vid(p)}</div>
      <b>${esc(p.title || p.style_label)}</b><small class="muted">${esc(p.style_label)} · ${fmtDur(p.length)} · ${p.n_shots} klipp${p.music_name ? ` · ${esc(p.music_name)}` : ""}</small>
      <div class="row" style="gap:6px;flex-wrap:wrap"><button class="btn small favbtn" data-propfav="${p.id}" aria-pressed="${!!p.favorite}">${icon("star", 14)}${p.favorite ? "Favorit" : "Gör till favorit"}</button>
        <button class="btn small" data-cmpedit="${p.id}">Redigera</button><button class="btn small" data-qexport="${p.id}">Exportera</button></div></div>`).join("")}</div>
    <div class="row" style="justify-content:center;gap:8px"><button class="btn primary" data-cmpplay>${icon("play", 13)}Spela båda</button>
      <label class="row" style="gap:6px;font-size:13px"><input type="checkbox" id="cmpMuteB" checked style="accent-color:var(--accent)">Ljud bara från vänster</label>
      <button class="btn" data-act="modal-close">Stäng</button></div></div>`;
  m.hidden = false;
  state.cmpOpen = true;
  if (missing.length) {  // gör förhandsvisningarna som saknas, i kön
    for (const p of missing) { try { await api("POST", `/api/p/${state.pid}/proposal/${p.id}/render`, { resolution: "preview" }); } catch (_) { /* */ } }
    state.cmpWait = setInterval(async () => {
      await loadProject(state.pid);
      if (state.cmp.every((id) => (propById(id) || {}).renders && propById(id).renders.preview)) { clearInterval(state.cmpWait); if (state.cmpOpen && !$("#modal").hidden) openCompare(); }
    }, 2500);
  }
}
function cmpVideos() { return [...document.querySelectorAll(".cmpvid")]; }
function cmpToggle() {
  const vs = cmpVideos();
  if (!vs.length) return;
  const btn = document.querySelector("[data-cmpplay]");
  const playing = vs.some((v) => !v.paused);
  const muteB = ($("#cmpMuteB") || {}).checked !== false;
  vs.forEach((v, k) => { v.muted = muteB && k === 1; });
  if (playing) { vs.forEach((v) => v.pause()); if (btn) btn.innerHTML = `${icon("play", 13)}Spela båda`; }
  else {
    if (vs.every((v) => v.ended || v.currentTime >= (v.duration || 1) - 0.05)) vs.forEach((v) => { v.currentTime = 0; });
    vs.forEach((v) => v.play().catch(() => {}));
    if (btn) btn.innerHTML = `${svgi(ICO.pause, 13)}Pausa`;
  }
}
document.addEventListener("click", async (ev) => {
  const t = ev.target.closest("[data-cmp], [data-cmpopen], [data-cmpclear], [data-cmpplay], [data-cmpedit], [data-propcompact], [data-rowplay]");
  if (!t) return;
  ev.preventDefault(); ev.stopPropagation();
  const d = t.dataset;
  if (d.cmp) {
    const set = state.cmp.filter((x) => x !== d.cmp);
    if (set.length === state.cmp.length) { set.push(d.cmp); if (set.length > 2) set.shift(); }
    state.cmp = set;
    render();
    if (state.cmp.length === 2) openCompare();
    return;
  }
  if (d.cmpopen !== undefined) return openCompare();
  if (d.cmpclear !== undefined) { state.cmp = []; return render(); }
  if (d.cmpplay !== undefined) return cmpToggle();
  if (d.cmpedit) { $("#modal").hidden = true; state.cmpOpen = false; return openEditor(d.cmpedit); }
  if (d.propcompact !== undefined) { state.propCompact = !state.propCompact; try { localStorage.setItem("tv.propCompact", state.propCompact ? "1" : "0"); } catch (_) { /* */ } return render(); }
  if (d.rowplay) {
    const p = propById(d.rowplay);
    if (!p || !p.renders || !p.renders.preview) return;
    const m = $("#modal");
    m.innerHTML = `<div class="modal-card cmpmodal" role="dialog" aria-modal="true" style="max-width:560px"><div class="cmpframe" style="aspect-ratio:${(p.format || "9:16").replace(":", "/")};height:min(72vh,720px)">
      <video controls autoplay playsinline src="${mediaUrl("renders", p.renders.preview)}?v=${p.renders.v || 0}"></video></div>
      <div class="row" style="justify-content:flex-end"><button class="btn" data-act="modal-close">Stäng</button></div></div>`;
    m.hidden = false;
  }
}, true);
document.addEventListener("ended", (ev) => {
  if (!ev.target.classList || !ev.target.classList.contains("cmpvid")) return;
  if (cmpVideos().every((v) => v.ended || v.paused)) { const b = document.querySelector("[data-cmpplay]"); if (b) b.innerHTML = `${icon("play", 13)}Spela båda`; }
}, true);
document.addEventListener("keydown", (ev) => {
  if ($("#modal").hidden || !document.querySelector(".cmpmodal") || !(ev.code === "Space" || ev.key === " ")) return;
  if (ev.target.closest("input, textarea, select")) return;
  ev.preventDefault(); cmpToggle();
}, true);

// stäng rutan: stoppa videor och väntan på förhandsvisningar
document.addEventListener("click", (ev) => {
  if (!ev.target.closest || !ev.target.closest('[data-act="modal-close"]')) return;
  document.querySelectorAll("#modal video").forEach((v) => v.pause());
  if (state.cmpWait) { clearInterval(state.cmpWait); state.cmpWait = null; }
  state.cmpOpen = false;
}, true);

/* ================= gör film av markerade klipp ================= */
function openFromClips() {
  const n = state.anSel.length;
  if (!n) return;
  const st = (P().settings || {});
  state.fc = state.fc || { length: "", style: "auto", format: st.format || "9:16", count: 3 };
  const fc = state.fc;
  const FL = { "9:16": "Stående 9:16 (Reels, TikTok, Shorts)", "16:9": "Liggande 16:9 (YouTube)", "1:1": "Kvadrat 1:1", "4:5": "Porträtt 4:5 (Instagram-flöde)" };
  const fmts = Object.fromEntries(((state.info && state.info.formats) || Object.keys(FL)).map((k) => [k, FL[k] || k]));
  const styles = (state.info && state.info.styles) || {};
  const m = $("#modal");
  m.innerHTML = `<div class="modal-card xmodal" role="dialog" aria-modal="true" aria-labelledby="fcTitle">
    <h2 id="fcTitle" style="font-size:18px">Gör film av ${n} markerade klipp</h2>
    <p class="muted" style="margin:0;font-size:13px">AI:n väljer de bästa delarna av varje klipp, ordningen, klipplängderna i takt med musiken, låten och texterna. Bara dina klipp används.</p>
    <div class="stack" style="gap:8px"><b style="font-size:14px">Längd</b>
      <div class="seg" role="group" aria-label="Längd" style="grid-template-columns:repeat(5,minmax(0,1fr))">${[["", "Lagom"], ["15", "15 s"], ["30", "30 s"], ["60", "60 s"], ["90", "90 s"]].map(([k, l]) => `<button data-fclen="${k}" aria-pressed="${fc.length === k}">${l}</button>`).join("")}</div>
      <small class="muted">Lagom = ungefär tre sekunder per klipp (${Math.round(Math.max(8, Math.min(60, n * 3.2)))} s). Med få klipp och snabb stil kan filmen bli kortare än vald längd – hellre det än upprepningar.</small></div>
    <label class="stack" style="gap:6px"><b style="font-size:14px">Format</b><select class="selfield" id="fcFmt">${Object.entries(fmts).map(([k, l]) => `<option value="${k}" ${fc.format === k ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>
    <div class="stack" style="gap:8px"><b style="font-size:14px">Stil</b>
      <div class="chips">${[["auto", "AI väljer"], ...Object.entries(styles).map(([k, v]) => [k, v.label || k])].map(([k, l]) => `<button class="chip" data-fcstyle="${k}" aria-pressed="${fc.style === k}">${esc(l)}</button>`).join("")}</div></div>
    <div class="stack" style="gap:8px"><b style="font-size:14px">Hur många?</b>
      <div class="seg" role="group" aria-label="Antal" style="grid-template-columns:repeat(2,minmax(0,1fr));max-width:420px">
        <button data-fccount="1" aria-pressed="${fc.count === 1}">En film</button><button data-fccount="3" aria-pressed="${fc.count !== 1}">Tre förslag att välja mellan</button></div>
      <small class="muted">${fc.style === "auto" ? (fc.count === 1 ? "En film – AI:n väljer stil (filmisk)." : "Tre olika stilar: filmisk, action och dokumentär.") : (fc.count === 1 ? "En film i vald stil." : "Tre varianter i vald stil.")}</small></div>
    <div class="row" style="justify-content:flex-end"><button class="btn" data-act="modal-close">Avbryt</button><button class="btn primary" data-fcgo>${icon("spark", 15)}Klipp ihop</button></div></div>`;
  m.hidden = false;
}
document.addEventListener("click", async (ev) => {
  const t = ev.target.closest("[data-fromclips], [data-fclen], [data-fcgo], [data-fcstyle], [data-fccount]");
  if (!t) return;
  ev.preventDefault(); ev.stopPropagation();
  const d = t.dataset;
  if (d.fromclips !== undefined) return openFromClips();
  if (d.fclen !== undefined || d.fcstyle || d.fccount) {
    if (d.fclen !== undefined) state.fc.length = d.fclen;
    if (d.fcstyle) state.fc.style = d.fcstyle;
    if (d.fccount) state.fc.count = Number(d.fccount);
    state.fc.format = $("#fcFmt").value;
    return openFromClips();
  }
  if (d.fcgo !== undefined) {
    const fc = state.fc;
    fc.format = $("#fcFmt").value;
    askNotify();
    try {
      await api("POST", `/api/p/${state.pid}/fromclips`, { clip_ids: state.anSel, length: fc.length ? Number(fc.length) : null, style: fc.style, format: fc.format, count: fc.count || 3 });
      $("#modal").hidden = true;
      state.anSel = [];
      state.planTab = "fromclips";
      state.expectJob = true;
      state.view = "proposals";
      toast(`AI:n klipper ihop dina klipp – ${fc.count === 1 ? "filmen dyker" : "förslagen dyker"} upp här.`, true);
      render();
      state.planTab = "all";
      await pollJob();
    } catch (e) { fail(e); }
  }
  return undefined;
}, true);

/* ================= förhandsgranska klippen i analysen ================= */
// dra musen över bilden: spola genom klippet (stillbilder, senaste vinner)
let hoverScrub = { el: null, busy: false, want: null };
document.addEventListener("mousemove", (ev) => {
  if (state.view !== "analyze") return;
  const box = ev.target.closest && ev.target.closest("[data-cprev]");
  if (!box || ev.target.closest(".ccsel")) return;
  const c = clips().find((x) => x.id === box.dataset.cprev);
  if (!c || !c.duration) return;
  const r = box.getBoundingClientRect();
  const f = Math.max(0, Math.min(1, (ev.clientX - r.left) / r.width));
  const t = Math.round(f * (c.duration - 0.1) * 4) / 4;  // kvartssekunder: färre förfrågningar
  box.style.setProperty("--scrub", `${(f * 100).toFixed(1)}%`);
  box.classList.add("scrubbing");
  const img = box.querySelector("img");
  const url = frameUrl(c.id, t, 480);
  if (img.dataset.cur === url) return;
  hoverScrub.want = { img, url };
  if (hoverScrub.busy) return;
  const load = () => {
    const w = hoverScrub.want;
    if (!w) return;
    hoverScrub.want = null; hoverScrub.busy = true;
    const im = new Image();
    im.onload = im.onerror = () => { hoverScrub.busy = false; if (im.naturalWidth && w.img.isConnected) { w.img.src = w.url; w.img.dataset.cur = w.url; } load(); };
    im.src = w.url;
  };
  load();
});
document.addEventListener("mouseout", (ev) => {
  const box = ev.target.closest && ev.target.closest("[data-cprev]");
  if (!box || (ev.relatedTarget && box.contains(ev.relatedTarget))) return;
  box.classList.remove("scrubbing");
  const c = clips().find((x) => x.id === box.dataset.cprev), img = box.querySelector("img");
  if (c && img && img.dataset.mid) { const u = frameUrl(c.id, Number(img.dataset.mid), 480); img.src = u; img.dataset.cur = u; }
  hoverScrub.want = null;
});

// klick: spela klippet i en ruta – bästa sekvensen markerad, pilar för nästa/föregående, F/X
function openClipPreview(cid) {
  const list = state.anList && state.anList.includes(cid) ? state.anList : clips().map((c) => c.id);
  const c = clips().find((x) => x.id === cid);
  if (!c) return;
  state.cpv = { cid, list };
  const a = c.analysis || {}, best = a.best || [0, c.duration || 0];
  const k = list.indexOf(cid);
  const dur = c.duration || 1;
  const segs = [];
  const tags = (a.tags || []).slice(0, 6).map((t) => `<span class="tag">${esc(t)}</span>`).join("");
  const whats = ((c.vlm && c.vlm.frames) || []).map((f) => f.what).filter(Boolean);
  const desc = [...new Set(whats)].slice(0, 3).join(" … ");
  const why = c.auto_excluded && !c.favorite && (c.reasons || []).length ? `AI:n valde bort klippet: ${(c.reasons || []).join(", ")}.` : "";
  const speech = c.speech && c.speech.segments && c.speech.segments.length ? c.speech.segments.map((s) => s.text || s[2] || "").join(" ").slice(0, 220) : "";
  const m = $("#modal");
  m.innerHTML = `<div class="modal-card cpvmodal" role="dialog" aria-modal="true" aria-labelledby="cpvTitle">
    <div class="spread" style="gap:10px"><h2 id="cpvTitle" style="font-size:17px;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(c.name)}</h2>
      <span class="muted num" style="font-size:13px;flex:none">${k + 1} av ${list.length}</span></div>
    <div class="cpvframe">${c.proxy
      ? `<video id="cpvVid" src="${mediaUrl("proxies", c.proxy)}" playsinline controls autoplay muted></video>`
      : `<img id="cpvImg" alt="" src="${frameUrl(c.id, (best[0] + best[1]) / 2, 960)}">`}</div>
    <div class="cpvbar" id="cpvBar" title="Klicka för att hoppa – markerat = bästa sekvensen">
      ${segs.map((s) => `<span class="cpvseg" style="left:${(s[0] / dur * 100).toFixed(2)}%;width:${((s[1] - s[0]) / dur * 100).toFixed(2)}%"></span>`).join("")}
      <span class="cpvbest" style="left:${(best[0] / dur * 100).toFixed(2)}%;width:${(Math.max(0.1, best[1] - best[0]) / dur * 100).toFixed(2)}%"></span>
      <span class="cpvhead" id="cpvHead"></span></div>
    <div class="row" style="gap:8px;flex-wrap:wrap;font-size:13px">
      <span class="muted">Bästa sekvens <b class="num" style="color:var(--text)">${fmtDur(best[0])}–${fmtDur(best[1])}</b> · ${fmtDur(dur)} · ${esc(c.source || "")}</span>${tags}</div>
    ${desc ? `<p style="margin:0;font-size:14px">${esc(desc)}</p>` : ""}
    ${why ? `<p style="margin:0;font-size:13px;color:var(--warn)">${esc(why)}</p>` : ""}
    ${speech ? `<p class="muted" style="margin:0;font-size:13px">Sägs: "${esc(speech)}"</p>` : ""}
    <div class="row" style="gap:8px;flex-wrap:wrap">
      <button class="btn small" data-cpvnav="-1" ${k <= 0 ? "disabled" : ""} aria-label="Föregående klipp">←</button>
      <button class="btn small" data-cpvnav="1" ${k >= list.length - 1 ? "disabled" : ""} aria-label="Nästa klipp">→</button>
      <button class="btn small" data-cpvbest>${icon("play", 12)}Spela bästa sekvensen</button>
      <button class="btn small" data-cpvsound>${c.proxy ? "Ljud på" : ""}</button>
      <span class="grow"></span>
      <button class="btn small toggle ${c.favorite ? "on" : ""}" data-cpvset="favorite" aria-pressed="${!!c.favorite}">${icon("star", 14)}Måste med <kbd>F</kbd></button>
      <button class="btn small toggle ${c.excluded ? "on" : ""}" data-cpvset="excluded" aria-pressed="${!!c.excluded}">${icon("eyeoff", 14)}Välj bort <kbd>X</kbd></button>
      <button class="btn small" data-cpvsel aria-pressed="${state.anSel.includes(c.id)}">${state.anSel.includes(c.id) ? "Markerad ✓" : "Markera"}</button>
      <button class="btn small primary" data-act="modal-close">Stäng</button></div></div>`;
  m.hidden = false;
  const v = document.getElementById("cpvVid");
  if (!c.proxy) { const sb = m.querySelector("[data-cpvsound]"); if (sb) sb.remove(); }
  if (v) {
    v.addEventListener("loadedmetadata", () => { try { v.currentTime = best[0]; } catch (_) { /* */ } }, { once: true });
    v.addEventListener("timeupdate", () => { const h = document.getElementById("cpvHead"); if (h) h.style.left = `${(v.currentTime / dur * 100).toFixed(2)}%`; });
  }
}
function cpvSeek(t) {
  const v = document.getElementById("cpvVid"), c = clips().find((x) => state.cpv && x.id === state.cpv.cid);
  if (v) { v.currentTime = t; v.play().catch(() => {}); }
  else if (c) { const im = document.getElementById("cpvImg"); if (im) im.src = frameUrl(c.id, t, 960); const h = document.getElementById("cpvHead"); if (h) h.style.left = `${(t / (c.duration || 1) * 100).toFixed(2)}%`; }
}
function cpvNav(step) {
  const s = state.cpv;
  if (!s) return;
  const k = s.list.indexOf(s.cid) + step;
  if (k >= 0 && k < s.list.length) openClipPreview(s.list[k]);
}
async function cpvSet(field) {
  const s = state.cpv;
  if (!s) return;
  await bulk(field, [s.cid]);
  openClipPreview(s.cid);
}
document.addEventListener("click", (ev) => {
  const t = ev.target.closest("[data-cprev], [data-cpvnav], [data-cpvbest], [data-cpvset], [data-cpvsel], [data-cpvsound], #cpvBar");
  if (!t) return;
  if (t.matches("[data-cprev]")) {
    if (ev.target.closest(".ccsel") || state.view !== "analyze") return;
    ev.preventDefault();
    return openClipPreview(t.dataset.cprev);
  }
  ev.preventDefault();
  const d = t.dataset, c = clips().find((x) => state.cpv && x.id === state.cpv.cid);
  if (!c) return;
  if (t.id === "cpvBar") { const r = t.getBoundingClientRect(); return cpvSeek(Math.max(0, Math.min(1, (ev.clientX - r.left) / r.width)) * (c.duration || 0)); }
  if (d.cpvnav) return cpvNav(Number(d.cpvnav));
  if (d.cpvbest !== undefined) return cpvSeek((c.analysis || {}).best ? c.analysis.best[0] : 0);
  if (d.cpvsound !== undefined) { const v = document.getElementById("cpvVid"); if (v) { v.muted = !v.muted; t.textContent = v.muted ? "Ljud på" : "Ljud av"; } return; }
  if (d.cpvset) return cpvSet(d.cpvset);
  if (d.cpvsel !== undefined) {
    const sel = new Set(state.anSel);
    if (sel.has(c.id)) sel.delete(c.id); else sel.add(c.id);
    state.anSel = [...sel];
    render();
    return openClipPreview(c.id);
  }
});
document.addEventListener("keydown", (ev) => {
  if ($("#modal").hidden || !document.querySelector(".cpvmodal") || ev.target.closest("input, textarea, select")) return;
  const k = ev.key.toLowerCase();
  if (k === "arrowright" || k === "arrowleft") { ev.preventDefault(); ev.stopPropagation(); cpvNav(k === "arrowright" ? 1 : -1); }
  else if (k === "f" || k === "x") { ev.preventDefault(); ev.stopPropagation(); cpvSet(k === "f" ? "favorite" : "excluded"); }
  else if (k === " " || ev.code === "Space") {
    ev.preventDefault(); ev.stopPropagation();
    const v = document.getElementById("cpvVid"); if (v) { if (v.paused) v.play().catch(() => {}); else v.pause(); }
  } else if (k === "escape") { document.querySelectorAll("#modal video").forEach((v) => v.pause()); $("#modal").hidden = true; }
}, true);
// Enter på ett fokuserat kort öppnar förhandsvisningen
document.addEventListener("keydown", (ev) => {
  if (state.view !== "analyze" || ev.key !== "Enter" || !$("#modal").hidden) return;
  const card = ev.target.closest && ev.target.closest(".ccard[data-cid]");
  if (card && ev.target === card) { ev.preventDefault(); openClipPreview(card.dataset.cid); }
});
