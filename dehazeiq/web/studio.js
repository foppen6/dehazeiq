/* DeHazeIQ – kö, filmtyper, plattformar och redigering. Delar globala hjälpare med app.js. */
"use strict";

const FT_ICON = {
  auto: '<path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1"/>',
  dive: '<path d="M2 14c2.5 0 2.5-3 5-3s2.5 3 5 3 2.5-3 5-3 2.5 3 5 3"/><path d="M2 19c2.5 0 2.5-3 5-3s2.5 3 5 3 2.5-3 5-3 2.5 3 5 3" opacity=".5"/>',
  trip: '<path d="M2 16l20-7-20-7 4 7-4 7z"/>',
  reels: '<rect x="7" y="2" width="10" height="20" rx="2"/><path d="M11 18h2"/>',
  animal: '<path d="M3 12c3-5 10-6 14-2l4-3v10l-4-3c-4 4-11 3-14-2z"/><path d="M8 11h.01"/>',
  promo: '<path d="M3 11v2a1 1 0 0 0 1 1h3l5 4V6L7 10H4a1 1 0 0 0-1 1z"/><path d="M16 8a5 5 0 0 1 0 8M19 5a9 9 0 0 1 0 14"/>',
  musicvideo: '<path d="M9 18V5l11-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="16" r="3"/>',
  trailer: '<rect x="3" y="6" width="18" height="12" rx="2"/><path d="m10 9 5 3-5 3z"/>',
  social: '<path d="M12 21s-7-4.4-9.3-9A5 5 0 0 1 12 6a5 5 0 0 1 9.3 6c-2.3 4.6-9.3 9-9.3 9z"/>',
};
const FT_DESC = {
  auto: "AI läser materialet och föreslår den mix av berättelser som passar bäst.",
  dive: "Ett dyk som en berättelse: nedstigning, möten och uppstigning.",
  trip: "Hela resan i kapitel per dag eller dyk, i tidsordning.",
  reels: "Korta, snabba filmer i takt till musik – flera olika varianter.",
  animal: "En film per djur: bläckfisken, krabban, sköldpaddan …",
  promo: "Fyra reklamvarianter. Krok, säljpunkter, logga och uppmaning läggs in efteråt – samma film kan användas för olika saker.",
  musicvideo: "Fyra varianter till din låt: i takt, ballad, glitch och med din sångtext. Bästa klippet hamnar på refrängen.",
  trailer: "Byggs upp som en filmtrailer: lugn start, textskyltar, allt snabbare klipp och titeln på slutet.",
  social: "Trender för Instagram och TikTok: hook-reel, POV, före/efter, topp 5, loop, fotodump och cinematic reel.",
};
const svgi = (p, s = 18) => `<svg aria-hidden="true" width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`;
const ICO = {
  list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
  up: '<path d="m6 15 6-6 6 6"/>', down: '<path d="m6 9 6 6 6-6"/>', x: '<path d="M6 6l12 12M18 6 6 18"/>',
  pause: '<path d="M8 5v14M16 5v14"/>', check: '<path d="m5 12 5 5L20 7"/>', undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-3"/>',
  left: '<path d="m15 6-6 6 6 6"/>', right: '<path d="m9 6 6 6-6 6"/>', swap: '<path d="M7 4 3 8l4 4"/><path d="M3 8h14"/><path d="m17 20 4-4-4-4"/><path d="M21 16H7"/>',
  scissors: '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M20 4 8.1 15.9M14.5 14.5 20 20M8.1 8.1 12 12"/>',
  target: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/>',
};
const platforms = () => (state.info && state.info.platforms) || {};
const filmTypes = () => (state.info && state.info.film_types) || {};
const LOOK_CSS = {
  none: "saturate(1.15) contrast(1.06)", original: "none", natural: "saturate(1.1) contrast(1.05)", underwater: "saturate(1.3) sepia(.12) brightness(1.05)",
  warm: "sepia(.3) saturate(1.2)", cold: "hue-rotate(12deg) saturate(1.05) brightness(1.02)", vivid: "saturate(1.6) contrast(1.1)",
  film: "contrast(1.15) saturate(.75) sepia(.15)", bw: "grayscale(1) contrast(1.15)", bw_soft: "grayscale(1) contrast(.9) brightness(1.06)",
  sepia: "sepia(.9)",
};
const platformLabel = (k) => (platforms()[k] || {}).label || k;

/* ================= kö ================= */
state.queue = { paused: false, tasks: [], done: [] };
async function loadQueue() {
  try {
    state.queue = await api("GET", "/api/queue");
    const n = state.queue.tasks.length + (state.queue.interrupted || []).length;
    if (!state.queueWarned && (state.queue.interrupted || []).length) {
      state.queueWarned = true;
      toast(`${state.queue.interrupted.length} jobb avbröts när programmet stängdes. Öppna Kö och tryck Kör igen.`);
    }
    const b = document.querySelector("[data-qbadge]");
    if (b) { b.textContent = n; b.hidden = !n; }
    if (state.view === "queue") $("#view").innerHTML = viewQueue();
  } catch (_) { /* tyst */ }
}
setInterval(loadQueue, 2500);

function queueButton() {
  const n = (state.queue.tasks || []).length + (state.queue.interrupted || []).length;
  return `<button class="btn small" data-act="queue" title="Jobbkö">${svgi(ICO.list, 15)}Kö<span class="qbadge num" data-qbadge ${n ? "" : "hidden"}>${n}</span></button>`;
}

function viewQueue() {
  const q = state.queue;
  const rows = (q.tasks || []).map((t, i) => {
    const run = t.state === "running";
    const pct = Math.round((t.progress || 0) * 100);
    return `<div class="qrow ${run ? "run" : ""}">
      <span class="qico">${run ? '<span class="spinner" style="width:18px;height:18px"></span>' : `<span class="num muted">${i + 1}</span>`}</span>
      <div class="stack" style="gap:5px;min-width:0"><b>${esc(t.label)}</b><span class="muted" style="font-size:13px">${esc(t.project)} · ${esc(run ? t.message || "" : (q.paused ? "Kön är pausad" : "Väntar"))}</span>
        ${run ? `<div class="bar"><div style="width:${pct}%"></div></div>` : ""}</div>
      <span class="num muted" style="font-size:13px">${run ? `${pct} %` : ""}</span>
      <span class="row" style="gap:6px;flex-wrap:nowrap">
        ${run ? "" : `<button class="btn icon small" data-qmove="${t.id}" data-dir="-1" aria-label="Flytta upp" ${i <= 1 && q.tasks[0].state === "running" && i === 1 ? "" : ""}>${svgi(ICO.up, 15)}</button>
        <button class="btn icon small" data-qmove="${t.id}" data-dir="1" aria-label="Flytta ned">${svgi(ICO.down, 15)}</button>`}
        <button class="btn icon small" data-qcancel="${t.id}" aria-label="${run ? "Avbryt" : "Ta bort ur kön"}" title="${run ? "Avbryt" : "Ta bort ur kön"}">${svgi(ICO.x, 15)}</button></span>
    </div>`;
  }).join("");
  const done = (q.done || []).map((t) => {
    const ok = t.state === "done";
    const when = t.finished ? new Date(t.finished * 1000).toLocaleTimeString("sv-SE", { hour: "2-digit", minute: "2-digit" }) : "";
    return `<div class="drow"><span style="color:${ok ? "var(--good)" : t.state === "cancelled" ? "var(--muted)" : "var(--bad)"}">${svgi(ok ? ICO.check : ICO.x, 16)}</span>
      <span class="grow"><b style="font-weight:600">${esc(t.label)}</b><span class="muted"> · ${esc(t.project)}</span>${!ok ? `<br><small class="muted">${esc(t.message || "")}</small>` : ""}</span>
      <span class="muted num" style="font-size:13px">${when}</span>${t.pid.startsWith("_") ? `<button class="btn small" data-act="music-view">Musik</button>` : `<button class="btn small" data-qopen="${esc(t.pid)}">Öppna</button>`}</div>`;
  }).join("");
  const stopped = (q.interrupted || []).map((t) => `<div class="drow"><span style="color:var(--warn)">${svgi(ICO.pause, 16)}</span>
      <span class="grow"><b style="font-weight:600">${esc(t.label)}</b><span class="muted"> · ${esc(t.project)}</span><br><small class="muted">${esc(t.message || "")}</small></span>
      <button class="btn small primary" data-qretry="${t.id}">Kör igen</button><button class="btn icon small" data-qdismiss="${t.id}" aria-label="Glöm jobbet" title="Glöm jobbet">${svgi(ICO.x, 15)}</button></div>`).join("");
  return `<main class="main wide" style="max-width:1000px">
    <div class="spread"><div class="head"><h1>Jobbkö</h1><p class="lead">Ett jobb i taget i bakgrunden – du kan stänga fönstret eller jobba med annat. Ordningen går att ändra.</p></div>
      <div class="row"><button class="btn" data-act="qpause">${svgi(q.paused ? '<path d="M8 5v14l11-7z"/>' : ICO.pause, 16)}${q.paused ? "Fortsätt kön" : "Pausa kön"}</button>
      ${P() ? `<button class="btn primary" data-act="setup-project">Nya filmer av ${esc(P().name)}</button>` : ""}</div></div>
    ${stopped ? `<section class="stack" style="gap:4px"><span class="eyebrow">Avbrutet vid avstängning</span>${stopped}</section>` : ""}
    <section class="stack" style="gap:10px"><span class="eyebrow">Pågår och väntar</span>${rows || '<div class="empty">Kön är tom.</div>'}</section>
    ${done ? `<section class="stack" style="gap:4px"><div class="spread"><span class="eyebrow">Klart</span><button class="btn small" data-act="qclear">Rensa listan</button></div>${done}</section>` : ""}
  </main>`;
}

/* ================= ny film: välj filmtyper ================= */
function defaultPlans() {
  return { auto: { on: true }, dive: { on: false }, trip: { on: false }, reels: { on: false }, animal: { on: false },
    promo: { on: false }, musicvideo: { on: false }, trailer: { on: false } };
}
function viewSetup() {
  const su = state.setup || (state.setup = { mode: "project", plans: defaultPlans() });
  const fts = Object.fromEntries(Object.entries(filmTypes()).filter(([k]) => k !== "prompt"));
  const pfs = platforms();
  const cards = Object.entries(fts).map(([k, ft]) => {
    const pl = su.plans[k] || (su.plans[k] = { on: false });
    const on = !!pl.on;
    return `<button class="ftcard" data-ft="${k}" aria-pressed="${on}">
      <span class="ftmark">${on ? svgi(ICO.check, 14) : ""}</span>
      <span class="ftico">${svgi(FT_ICON[k] || FT_ICON.auto, 22)}</span><b>${esc(ft.label)}</b><span class="muted">${esc(FT_DESC[k] || "")}</span></button>`;
  }).join("");
  const opts = Object.entries(fts).filter(([k]) => (su.plans[k] || {}).on).map(([k, ft]) => {
    const pl = su.plans[k];
    const plat = pl.platform || ft.platform;
    const len = pl.length || (pfs[plat] || {}).length || 30;
    const count = pl.count || ft.count;
    const lens = [7, 15, 30, 45, 60, 90, 180, 300].map((s) => `<option value="${s}" ${Number(len) === s ? "selected" : ""}>${s < 60 ? `${s} s` : `${s / 60} min`}</option>`).join("");
    return `<div class="ftopt"><b>${esc(ft.label)}</b>
      <label>Gör för<select data-ftplat="${k}">${Object.entries(pfs).map(([pk, pf]) => `<option value="${pk}" ${pk === plat ? "selected" : ""}>${esc(pf.label)} · ${pf.format}</option>`).join("")}</select></label>
      <label>Längd<select data-ftlen="${k}">${lens}</select></label>
      <label>Antal förslag<select data-ftcount="${k}">${[1, 2, 3, 4, 6, 8, 10].map((n) => `<option ${n === Number(count) ? "selected" : ""}>${n}</option>`).join("")}</select></label></div>`;
  }).join("");
  const isNew = su.mode === "new";
  const nOn = Object.values(su.plans).filter((p) => p.on).length;
  return `<main class="main wide" style="max-width:1200px">
    <div class="head"><h1>Vad vill du göra av materialet?</h1>
      <p class="lead">Välj en eller flera. AI:n ${isNew ? "analyserar först och " : ""}gör förslag av varje sort. Allt läggs i kön och körs i bakgrunden.</p></div>
    ${isNew ? "" : promptBar()}
    <div class="stack" style="gap:8px"><b>Hur ska förslagen skilja sig åt?</b>${varietyToggle("setup")}</div>
    <div class="ftgrid">${cards}</div>
    ${opts ? `<section class="box stack" style="gap:14px">${opts}</section>` : ""}
    <section class="box" style="flex-direction:row;flex-wrap:wrap;align-items:center;gap:16px">
      ${isNew ? `<label class="stack" style="gap:6px;flex:1 1 260px;font-size:13px;color:var(--text-2)">Projektnamn (kan ändras senare)<input class="field" id="setupName" value="${esc(su.name || "")}" placeholder="Namnges efter mappen"></label>
        <span class="muted" style="font-size:13px">${su.paths.length === 1 ? esc(su.paths[0]) : `${su.paths.length} filer/mappar`}</span>` : ""}
      <label class="row" style="gap:10px;color:var(--text-2)"><input type="checkbox" id="setupPrev" ${su.previews === false ? "" : "checked"} style="width:18px;height:18px;accent-color:var(--accent)">Gör förhandsvisningar direkt</label>
      <span class="grow"></span>
      <button class="btn" data-act="setup-cancel">Avbryt</button>
      <button class="btn primary big" data-act="setup-go" ${nOn ? "" : "disabled"}>${svgi(ICO.list, 17)}Lägg i kön och starta</button>
    </section>
  </main>`;
}

function setupPlans() {
  const su = state.setup;
  return Object.entries(su.plans).filter(([k, p]) => p.on && k !== "prompt").map(([k, p]) => ({
    type: k, platform: p.platform || filmTypes()[k].platform, length: p.length || null, count: p.count || null,
    ...(su.variety ? { variety: su.variety } : {}),
  }));
}

async function setupGo() {
  const su = state.setup;
  const plans = setupPlans();
  const previews = $("#setupPrev") ? $("#setupPrev").checked : true;
  try {
    if (su.mode === "new") {
      const name = $("#setupName") ? $("#setupName").value.trim() : "";
      const p = await api("POST", "/api/import", { paths: su.paths, plans, previews, name });
      state.expectJob = true;
      await loadProjects();
      await loadProject(p.id);
      state.view = "proposals";
      await pollJob();
    } else {
      await api("POST", `/api/p/${state.pid}/plans`, { plans, run: true, previews });
      state.expectJob = true;
      state.view = "proposals";
      await pollJob();
    }
    state.setup = null;
    toast("Lagt i kön. Du kan jobba med annat under tiden.", true);
    loadQueue();
    render();
  } catch (e) { fail(e); }
}

/* ================= förslag: filmtyp och plattform ================= */
function planTabs() {
  const props = (P() && P().proposals) || [];
  const plans = [];
  props.forEach((p) => { if (p.plan && !plans.includes(p.plan)) plans.push(p.plan); });
  if (!plans.length) return "";
  if (!state.planTab || (state.planTab !== "all" && !plans.includes(state.planTab))) state.planTab = "all";
  const n = (k) => props.filter((p) => p.plan === k).length;
  return `<div class="chips" role="tablist" aria-label="Filmtyp"><button class="chip" data-plantab="all" aria-pressed="${state.planTab === "all"}">Alla <span class="muted">· ${props.length}</span></button>
    ${plans.map((k) => `<button class="chip" role="tab" data-plantab="${k}" aria-pressed="${state.planTab === k}">${esc((filmTypes()[k] || {}).label || (k === "custom" ? "Egna förslag" : k))} <span class="muted">· ${n(k)}</span></button>`).join("")}
    <button class="chip" data-act="setup-project">+ Fler filmtyper</button></div>`;
}

function planProposals() {
  const props = (P() && P().proposals) || [];
  if (!props.some((p) => p.plan)) return null;
  const list = state.planTab === "all" ? props : props.filter((p) => p.plan === state.planTab);
  return list;
}

function lengthSelect(p) {
  const cur = Math.round(p.target_length || p.length || 30);
  const opts = [7, 15, 30, 60, 90];
  if (!opts.includes(cur)) opts.push(cur);
  return `<label class="platsel"><span class="sr">Längd</span><select data-proplen="${p.id}" title="Gör om filmen i en annan längd">
    ${opts.sort((a, b) => a - b).map((s) => `<option value="${s}" ${s === cur ? "selected" : ""}>${s} s</option>`).join("")}</select></label>`;
}

async function changeLength(propId, length) {
  const p = propById(propId);
  const pfs = platforms();
  const plat = p.platform || Object.keys(pfs).find((k) => pfs[k].format === p.format) || "reels";
  toast(`Gör om filmen till ${length} sekunder …`, true);
  try {
    const r = await api("POST", `/api/p/${state.pid}/proposal/${propId}/platform`, { platform: plat, length: Number(length) });
    const ps = P().proposals;
    const i = ps.findIndex((x) => x.id === propId);
    if (i >= 0) ps[i] = r.proposal;
    state.ed.shotPrev = {};
    state.ed.stamp = Date.now();
    render();
    requestShotPreview();
  } catch (e) { fail(e); }
}

function platformSelect(p) {
  const pfs = platforms();
  const cur = p.platform || Object.keys(pfs).find((k) => pfs[k].format === p.format) || "";
  return `<label class="platsel"><span class="sr">Gör för</span><select data-platform="${p.id}" ${running() ? "" : ""}>
    ${cur ? "" : `<option value="">${esc(p.format)}</option>`}
    ${Object.entries(pfs).map(([k, pf]) => `<option value="${k}" ${k === cur ? "selected" : ""}>${esc(pf.label)} · ${pf.format}</option>`).join("")}</select></label>`;
}

async function changePlatform(propId, platform) {
  if (!platform) return;
  toast(`Anpassar för ${platformLabel(platform)} …`, true);
  try {
    const r = await api("POST", `/api/p/${state.pid}/proposal/${propId}/platform`, { platform });
    const ps = P().proposals;
    const i = ps.findIndex((x) => x.id === propId);
    if (i >= 0) ps[i] = r.proposal;
    toast(`Klart: ${platformLabel(platform)} · ${r.proposal.format} · ${fmtDur(r.proposal.length)}`, true);
    render();
  } catch (e) { fail(e); }
}

/* export till flera plattformar */
state.exportPlats = null;
function exportPlatforms(p) {
  const pfs = platforms();
  const cur = p.platform || Object.keys(pfs).find((k) => pfs[k].format === p.format);
  if (!state.exportPlats || state.exportPlatsFor !== p.id) { state.exportPlats = cur ? [cur] : []; state.exportPlatsFor = p.id; }
  return `<section class="stack"><h2>Plattformar</h2>
    <p class="muted" style="margin:0;font-size:13px">Välj en eller flera. Filmen anpassas automatiskt (format, längd och beskärning) och varje export läggs i kön.</p>
    <div class="chips">${Object.entries(pfs).map(([k, pf]) => `<button class="chip" data-explat="${k}" aria-pressed="${state.exportPlats.includes(k)}">${esc(pf.label)} <span class="muted">· ${pf.format}</span></button>`).join("")}</div></section>
    <section class="stack"><h2>Språk för texterna</h2>
    <p class="muted" style="margin:0;font-size:13px">En version per språk. Artnamn, kapitel och datum översätts automatiskt; egna texter översätts av djupanalysen på Mac eller rättas under Redigera › Text. En undertextfil (.srt) följer med.</p>
    <div class="chips">${Object.entries((state.info && state.info.languages) || { sv: "Svenska" }).map(([k, l]) => `<button class="chip" data-exlang="${k}" aria-pressed="${(state.exportLangs || ["sv"]).includes(k)}">${esc(l)}</button>`).join("")}</div></section>`;
}

async function exportQueued() {
  const p = propById(state.exportProp);
  if (!p) return;
  try {
    const r = await api("POST", `/api/p/${state.pid}/proposal/${p.id}/export`, { platforms: state.exportPlats, resolution: state.exportRes, langs: state.exportLangs || ["sv"] });
    toast(`${r.queued} export${r.queued === 1 ? "" : "er"} lagda i kön.`, true);
    state.expectJob = true;
    loadQueue();
    await pollJob();
    render();
  } catch (e) { fail(e); }
}

/* ================= redigering ================= */
state.ed = { prop: null, i: 0, tab: "clip", scope: "film", alts: null, before: false, stamp: Date.now() };
const edProp = () => propById(state.ed.prop);
const stillUrl = (p, i, graded = true, w = 540) => `/api/p/${state.pid}/proposal/${p.id}/still?i=${i}&at=0.45&w=${w}&graded=${graded ? 1 : 0}&s=${state.ed.stamp}`;

function openEditor(propId) {
  state.ed = { prop: propId, i: 0, tab: "clip", scope: "film", alts: null, mode: "clip", stamp: Date.now() };
  state.view = "edit";
  render();
  const p = edProp();
  if (p && p.shots.some((s) => s.text)) edit("materialize", {}).then(() => render());  // gamla förslag: artnamn m.m. blir vanliga texter
  requestShotPreview(100);
}

async function edit(op, args = {}, { quiet = false } = {}) {
  const p = edProp();
  if (!p) return;
  try {
    const r = await api("POST", `/api/p/${state.pid}/proposal/${p.id}/edit`, { op, args });
    const ps = P().proposals;
    const k = ps.findIndex((x) => x.id === p.id);
    if (k >= 0) ps[k] = r.proposal;
    state.ed.i = Math.min(state.ed.i, r.proposal.shots.length - 1);
    state.ed.stamp = Date.now();
    if (op === "swap" || op === "delete" || op === "move" || op === "undo") state.ed.alts = null;
    if (["swap", "delete", "move", "undo", "trim"].includes(op) && state.ed.matchInfo) loadMatchInfo();
    if (!quiet) { render(); requestShotPreview(); } else refreshStill();
    document.querySelectorAll("[data-act=ed-undo]").forEach((b) => { b.disabled = !(r.proposal.undo_n || (r.proposal.history || []).length); });
  } catch (e) { fail(e); }
}

function refreshStill() {
  const p = edProp();
  if (!p) return;
  paintStage();
  const tl = $("#edTimeline");
  if (tl) tl.outerHTML = edTimeline(p);
  requestShotPreview();
}

function curGrade(p) {
  const s = p.shots[state.ed.i] || {};
  const g = state.ed.scope === "shot" ? (s.grade || p.grade) : p.grade;
  return Object.assign({ look: "none", strength: 1, exposure: 0, contrast: 0, saturation: 0, temperature: 0, tint: 0, sharpen: 0, vignette: 0, dehaze: null, particles: null, stabilize: null }, g || {});
}

function edTimeline(p) {
  const total = p.shots.reduce((a, s) => a + s.duration, 0) || 1;
  const blocks = p.shots.map((s, i) => {
    const fx = s.fx || {};
    const tags = [fx.speed > 1 ? "2×" : "", fx.speed && fx.speed < 1 ? "0,5×" : "", fx.freeze ? "Frys" : "", fx.zoom ? "Zoom" : "", fx.punch ? "Ryck" : "", fx.kenburns ? (fx.kenburns > 0 ? "Foto ↗" : "Foto ↙") : s.photo ? "Foto" : "", s.parent360 ? ({ planet: "Planet", ball: "Kula", whip: "360-svep", view: "360" }[(s.cam360 || {}).mode] || "360") : "", fx.roll ? "Roll" : "", s.grade ? "Färg" : "", s.manual_center ? "Flyttad" : "", s.fit ? ((s.fit.zoom ?? 1) < 1 ? "Utzoom" : "Inzoom") : "", state.ed.matchInfo && Object.values(state.ed.matchInfo.refs || {}).includes(i) && (p.match || {}).on !== false ? "Färgref" : ""].filter(Boolean);
    return `<button class="tlblock ${i === state.ed.i ? "sel" : ""}" data-edshot="${i}" data-drag="${i}" style="flex:${s.duration} 1 0;touch-action:pan-y" aria-label="Klipp ${i + 1}, ${dec(s.duration)} sekunder. Dra för att flytta.">
      <img alt="" loading="lazy" draggable="false" src="${frameUrl(s.clip_id, s.src_start + Math.min(s.duration, 1.5), 160)}"><span class="tlnum num">${i + 1}</span>${s.edited ? '<span class="tledited" title="Ändrat av dig"></span>' : ""}<span class="tldur num">${dec(s.duration)} s</span>${tags.length ? `<span class="tltags">${tags.join(" · ")}</span>` : ""}</button>`;
  }).join("");
  const title = (p.effects || {}).title;
  const trLabel = (state.info && state.info.transitions) || {};
  const trRow = p.shots.map((s, i) => `<span style="flex:${s.duration} 1 0;min-width:28px;text-align:right;font-size:10px;color:${s.tr && s.tr !== "cut" ? "var(--accent)" : "var(--dim)"}">${i < p.shots.length - 1 ? esc(s.tr && s.tr !== "cut" ? trLabel[s.tr] || s.tr : "|") : ""}</span>`).join("");
  const n = p.shots.length, i = state.ed.i;
  return `<section class="tl" id="edTimeline" aria-label="Tidslinje">
    <div class="tltools">
      <span class="muted" style="font-size:12px">Klipp ${i + 1} av ${n} · dra i klippen för att ändra ordning</span><span class="grow"></span>
      <button class="btn small" data-edmove="-1" ${i <= 0 ? "disabled" : ""} title="Flytta åt vänster (Alt+←)">${svgi(ICO.left, 14)}Flytta</button>
      <button class="btn small" data-edmove="1" ${i >= n - 1 ? "disabled" : ""} title="Flytta åt höger (Alt+→)">Flytta${svgi(ICO.right, 14)}</button>
      <button class="btn small danger" data-act="ed-delete" ${n <= 1 ? "disabled" : ""} title="Ta bort klippet (Delete)">${icon("trash", 14)}Ta bort klipp</button>
      <button class="btn small" data-act="ed-undo" title="Ångra (Ctrl/Cmd+Z)">Ångra</button></div>
    ${(() => { const ob = ovBars(p, total); return `<div class="tltrack"><span class="tllab">Text</span><div class="tlrow" style="position:relative;height:${ob.lanes * 24}px">${ob.html || '<button class="ovbar empty" data-act="ov-add" style="left:0;width:100%;top:0">+ Lägg till text</button>'}</div></div>`; })()}
    <div class="tltrack"><span class="tllab">Video</span><div class="tlrow">${blocks}</div></div>
    <div class="tltrack"><span class="tllab">Byte</span><div class="tlrow">${trRow}</div></div>
    <div class="tltrack"><span class="tllab">Ljud</span><div class="tlrow"><span class="tlaudio">${p.music_name ? `${esc(p.music_name)} · ${dec(p.bpm, 0)} BPM` : "Originalljud"}</span></div></div>
    <div class="muted num" style="font-size:12px;text-align:right">${p.shots.length} klipp · ${fmtDur(total)}</div></section>`;
}

function cam360Section(s) {
  const cam = s.cam360 || {};
  const mode = cam.mode === "view" ? "ai" : (cam.mode || "ai");
  const yaw = Number(cam.yaw || 0), fov = Number(cam.fov || 104);
  const modes = [["ai", "AI-vy"], ["planet", "Liten planet"], ["ball", "Kristallkula"], ["whip", "360-svep"]];
  return `<div class="stack" style="gap:8px;padding:12px;border-radius:12px;background:var(--accent-bg);border:1px solid var(--accent-bg-2)">
      <span class="flabel">360-kamera${s.view360 === "split" ? " · delad bild" : ""}</span>
      ${s.view360 === "split" ? '<span class="muted" style="font-size:12px">Motivet överst och andra hållet nedtill. Välj AI-vy-klippet för fler 360-effekter.</span>' : `
      <div class="chips">${modes.map(([k, l]) => chipBtn("data-cammode", k, l, mode === k)).join("")}</div>
      <label class="stack" style="gap:4px;font-size:13px">Vrid vyn <span class="muted num" data-camval="yaw">${Math.round(yaw)}°</span>
        <input type="range" min="-180" max="180" step="5" value="${yaw}" data-cam="yaw" style="accent-color:var(--accent)"></label>
      <label class="stack" style="gap:4px;font-size:13px">Bildvinkel <span class="muted num" data-camval="fov">${Math.round(fov)}°</span>
        <input type="range" min="60" max="150" step="2" value="${fov}" data-cam="fov" style="accent-color:var(--accent)"></label>`}
      <label class="row" style="gap:10px;font-size:14px"><input type="checkbox" data-camroll ${(s.fx || {}).roll ? "checked" : ""} style="width:18px;height:18px;accent-color:var(--accent)">Barrel roll (ett varv runt)</label>
      <span class="muted" style="font-size:12px">Syns när filmen förhandsvisas.</span></div>`;
}

function chipBtn(attr, val, label, on) {
  return `<button class="chip" ${attr}="${val}" aria-pressed="${!!on}">${label}</button>`;
}

function edInspectorClip(p, s) {
  const fx = s.fx || {};
  const speedMode = fx.freeze ? "freeze" : fx.speed > 1 ? "fast" : fx.speed && fx.speed < 1 ? "slow" : "normal";
  const effect = fx.zoom ? "zoom" : fx.punch ? "punch" : "none";
  const beat = p.bpm ? 60 / p.bpm : 0.5;
  const alts = state.ed.alts;
  return `<div class="stack" style="gap:4px"><span class="eyebrow">Klipp ${state.ed.i + 1} av ${p.shots.length}</span>
      <b style="font-size:16px">${esc(s.desc || s.label || s.name)}</b>
      <span class="muted" style="font-size:13px">${esc(s.name)} · ${dec(s.src_start)}–${dec(s.src_end)} s${s.species ? ` · ${esc(s.species)}` : ""}</span></div>
    <div class="stack" style="gap:8px"><span class="flabel">Längd</span>
      <div class="row" style="flex-wrap:nowrap"><button class="btn icon small" data-edtrim="${-beat}" aria-label="Kortare">−</button>
      <input type="range" min="0.5" max="10" step="0.1" value="${s.duration}" data-edlen aria-label="Längd i sekunder" style="flex:1 1 auto;accent-color:var(--accent)">
      <button class="btn icon small" data-edtrim="${beat}" aria-label="Längre">+</button><span class="num" style="width:48px;text-align:right" data-edlenval>${dec(s.duration)} s</span></div>
      ${p.bpm ? '<span class="muted" style="font-size:12px">Fäster på musikens takt</span>' : ""}</div>
    ${s.parent360 ? cam360Section(s) : ""}
    ${s.photo ? `<div class="stack" style="gap:8px"><span class="flabel">Rörelse i fotot</span><div class="chips">
      ${chipBtn("data-edfx", "kb_in", "Zooma in mot motivet", fx.kenburns > 0)}${chipBtn("data-edfx", "kb_out", "Zooma ut", fx.kenburns < 0)}${chipBtn("data-edfx", "none", "Stilla", !fx.kenburns && effect === "none")}</div></div>` : `
    <div class="stack" style="gap:8px"><span class="flabel">Hastighet</span><div class="chips">
      ${chipBtn("data-edspeed", "slow", "Slowmotion 0,5×", speedMode === "slow")}${chipBtn("data-edspeed", "normal", "Normal", speedMode === "normal")}
      ${chipBtn("data-edspeed", "fast", "Snabbspola 2×", speedMode === "fast")}${chipBtn("data-edspeed", "freeze", "Frys slutet", speedMode === "freeze")}</div></div>
    <div class="stack" style="gap:8px"><span class="flabel">Effekt</span><div class="chips">
      ${chipBtn("data-edfx", "none", "Ingen", effect === "none")}${chipBtn("data-edfx", "zoom", "Långsam zoom", effect === "zoom")}${chipBtn("data-edfx", "punch", "Zoomryck", effect === "punch")}</div></div>`}
    ${fitSection(p, s)}
    <div class="stack" style="gap:6px"><span class="flabel">Omslagsbild</span>
      <div class="row" style="gap:8px;align-items:center">${(p.cover || {}).i === state.ed.i ? '<span class="badge" style="position:static">Omslag</span><span class="muted" style="font-size:12px">Den här bilden blir omslag vid export.</span>'
        : `<button class="btn small" data-act="ed-cover">Använd klippet som omslag</button><span class="muted" style="font-size:12px">${p.cover ? `Nu: klipp ${p.cover.i + 1}` : "Annars väljer AI:n den bästa bilden."}</span>`}</div></div>
    <div class="stack" style="gap:8px"><span class="flabel">Motivet i bilden</span>
      <span class="muted" style="font-size:12px">Klicka i originalbilden till vänster för att flytta utsnittet.</span>
      ${s.manual_center ? `<button class="btn small" data-act="ed-autocenter">${svgi(ICO.target, 14)}Låt AI följa motivet igen</button>` : ""}</div>
    <div class="stack" style="gap:8px"><span class="flabel">${svgi(ICO.swap, 14)} Byt mot liknande</span>
      ${alts === null ? `<button class="btn small" data-act="ed-alts">Visa förslag från AI</button>`
        : alts === "loading" ? '<span class="muted" style="font-size:13px">Letar …</span>'
        : alts.length ? `<div class="altgrid">${alts.map((a, k) => `<button class="altbtn" data-edalt="${k}" title="${esc(a.desc || a.name)}"><img alt="" loading="lazy" src="${frameUrl(a.clip_id, a.thumb_t, 200)}"><span>${esc(a.label || a.name)}</span></button>`).join("")}</div>`
        : '<span class="muted" style="font-size:13px">Inga fler liknande sekvenser.</span>'}</div>
    ${state.ed.i < p.shots.length - 1 ? `<label class="stack" style="gap:8px"><span class="flabel">Övergång till nästa klipp</span>
      <select class="selfield" data-edtr>${Object.entries((state.info && state.info.transitions) || { cut: "Rakt klipp" }).map(([k, l]) => `<option value="${k}" ${(s.tr || "cut") === k ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>` : ""}
    <div class="stack" style="gap:8px"><span class="flabel">Texter på klippet</span>
      ${(() => { const here = (p.overlays || []).filter((o) => o.shot_uid === s.uid);
        return `${here.length ? here.map((o) => `<button class="chip" data-ovsel="${o.id}" data-edshot="${state.ed.i}" style="justify-content:flex-start">${esc(o.text.slice(0, 40))}${o.auto ? " · AI" : ""}</button>`).join("") : '<span class="muted" style="font-size:13px">Ingen text på klippet.</span>'}
        <button class="btn small" data-act="ov-add">+ Lägg till text</button>`; })()}</div>
`;
}

const FIT_BG = [["blur", "Suddig"], ["black", "Svart"], ["white", "Vit"], ["sand", "Sand"], ["ocean", "Havsblå"]];
function fitLabel(z) {
  if (Math.abs(z - 1) < 0.01) return "Fyller bilden";
  if (z <= 0.01) return "Hela bilden";
  return z < 1 ? `Utzoomat ${Math.round((1 - z) * 100)} %` : `Inzoomat ${Math.round((z - 1) * 100)} %`;
}
function fitSection(p, s) {
  const f = s.fit || {};
  const z = f.zoom ?? 1;
  const bg = f.bg || "blur";
  const custom = bg.startsWith("0x") ? `#${bg.slice(2)}` : "#000000";
  return `<div class="stack" style="gap:8px"><div class="spread" style="align-items:center"><span class="flabel">Inpassning${f.auto ? ' <span class="badge" style="position:static">AI</span>' : ""}</span>
      <button class="btn small" data-act="ed-fit-auto" title="AI zoomar ut om motivet inte ryms">Låt AI välja</button></div>
    <div class="row" style="flex-wrap:nowrap;gap:8px"><span class="muted" style="font-size:12px">Hela</span>
      <input type="range" min="0" max="1.8" step="0.02" value="${z}" data-edfit aria-label="Zooma ut eller in" list="fitTicks" style="flex:1 1 auto;accent-color:var(--accent)">
      <datalist id="fitTicks"><option value="1"></option></datalist>
      <span class="muted" style="font-size:12px">Tajt</span></div>
    <span class="muted num" style="font-size:12px" data-edfitval>${fitLabel(z)}</span>
    ${z < 0.99 ? `<div class="chips">${FIT_BG.map(([k, l]) => chipBtn("data-edfitbg", k, l, bg === k)).join("")}
      <label class="chip" style="gap:6px;cursor:pointer">Färg<input type="color" data-edfitcolor value="${custom}" style="width:22px;height:18px;border:0;padding:0;background:none"></label></div>` : ""}
    <div class="row" style="gap:6px"><button class="btn small" data-act="ed-fit-fill">Fyll bilden</button><button class="btn small" data-act="ed-fit-whole">Hela bilden</button>
      <button class="btn small" data-act="ed-fit-all">Samma på alla klipp</button></div></div>`;
}

function encSlider(g, k, label) {
  const auto = g[k] == null;
  return `<label class="sl"><span>${label}</span><input type="range" min="0" max="1" step="0.05" value="${auto ? 0.4 : g[k]}" data-edgrade="${k}" style="accent-color:var(--accent)${auto ? ";opacity:.5" : ""}"><span class="num" data-edgv="${k}">${auto ? "AI" : Math.round(g[k] * 100)}</span></label>`;
}

function matchSection(p) {
  const mi = state.ed.matchInfo;
  const s = p.shots[state.ed.i] || {};
  const m = Object.assign({ on: true, strength: 0.7, ref: null }, p.match || {});
  if (mi && mi.effect_on === false && !p.match) m.on = false;
  const refs = mi ? Object.values(mi.refs || {}) : [];
  const isRef = refs.includes(state.ed.i);
  const refTxt = !mi ? "Mäter klippen …" : !m.on ? "Av – klippen behåller sina egna färger."
    : refs.length ? `Referens: ${refs.map((r) => `klipp ${r + 1}`).join(" och ")}${m.ref ? "" : " (vald av AI)"}${refs.length > 1 ? " – under och ovan ytan matchas var för sig" : ""}.` : "För få klipp att matcha.";
  return `<div class="stack" style="gap:8px"><div class="spread" style="align-items:center"><span class="flabel">Färgmatchning</span>
      <div class="chips">${chipBtn("data-edmatch", "on", "På", m.on)}${chipBtn("data-edmatch", "off", "Av", !m.on)}</div></div>
    <span class="muted" style="font-size:12px">${refTxt}</span>
    ${m.on ? `<div class="row" style="gap:6px;flex-wrap:wrap">${isRef ? `<span class="badge" style="position:static">Klipp ${state.ed.i + 1} är referens</span>`
        : `<button class="btn small" data-act="ed-match-ref">Matcha mot klipp ${state.ed.i + 1}</button>`}
      ${m.ref ? '<button class="btn small" data-act="ed-match-auto">Låt AI välja referens</button>' : ""}</div>
      <label class="sl"><span>Styrka</span><input type="range" min="0" max="1" step="0.05" value="${m.strength}" data-edmatchk style="accent-color:var(--accent)"><span class="num" data-edmatchv>${Math.round(m.strength * 100)}</span></label>
      <label class="row" style="gap:10px;color:var(--text-2);font-size:13px"><input type="checkbox" data-edmatchskip ${s.nomatch ? "checked" : ""} style="width:18px;height:18px;accent-color:var(--accent)">Matcha inte klipp ${state.ed.i + 1}</label>` : ""}</div>`;
}
async function loadMatchInfo() {
  const p = edProp();
  if (!p) return;
  try {
    state.ed.matchInfo = await api("POST", `/api/p/${state.pid}/proposal/${p.id}/matchinfo`, {});
    if (state.view === "edit" && state.ed.tab === "color") render();
  } catch (e) { /* visas inte */ }
}

function edInspectorColor(p) {
  if (state.ed.matchInfo === undefined) { state.ed.matchInfo = null; loadMatchInfo(); }
  const g = curGrade(p);
  const looks = (state.info && state.info.looks) || {};
  const s = p.shots[state.ed.i] || {};
  const thumb = frameUrl(s.clip_id, s.src_start + Math.min(s.duration, 1.5), 160);
  const slider = (k, label, lo = -1) => `<label class="sl"><span>${label}</span><input type="range" min="${lo}" max="1" step="0.05" value="${g[k] || 0}" data-edgrade="${k}" style="accent-color:var(--accent)"><span class="num" data-edgv="${k}">${Math.round((g[k] || 0) * 100)}</span></label>`;
  return `${matchSection(p)}<div class="stack" style="gap:8px"><span class="flabel">Gäller</span><div class="chips">
      ${chipBtn("data-edscope", "film", "Hela filmen", state.ed.scope === "film")}${chipBtn("data-edscope", "shot", `Klipp ${state.ed.i + 1}`, state.ed.scope === "shot")}</div>
      ${state.ed.scope === "shot" && s.grade ? `<button class="btn small" data-act="ed-grade-reset">Använd filmens färg för klippet</button>` : ""}
      ${state.ed.scope === "film" && s.grade ? `<span class="muted" style="font-size:12px">Klipp ${state.ed.i + 1} har egen färg. Väljer du ett utseende här gäller det alla klipp.</span>` : ""}</div>
    <div class="stack" style="gap:8px"><span class="flabel">Utseende</span><div class="lookgrid">
      ${Object.entries(looks).map(([k, l]) => `<button class="lookbtn" data-edlook="${k}" aria-pressed="${g.look === k}"><img alt="" src="${thumb}" style="filter:${LOOK_CSS[k] || "none"}"><span>${esc(l)}</span></button>`).join("")}</div>
      ${slider("strength", "Styrka", 0)}</div>
    <div class="stack" style="gap:6px"><div class="spread" style="align-items:center"><span class="flabel">Justera</span><button class="btn small" data-act="ed-grade-zero">Nollställ</button></div>
      ${slider("exposure", "Exponering")}${slider("contrast", "Kontrast")}${slider("saturation", "Mättnad")}${slider("temperature", "Temperatur")}${slider("tint", "Nyans")}${slider("sharpen", "Skärpa", 0)}${slider("vignette", "Vinjett", 0)}</div>
    <div class="stack" style="gap:6px"><div class="spread" style="align-items:center"><span class="flabel">Bildförbättring</span><button class="btn small" data-act="ed-enh-auto">Låt AI välja</button></div>
      ${encSlider(g, "dehaze", "Ta bort dis")}${encSlider(g, "particles", "Partiklar")}
      <label class="row" style="gap:10px;color:var(--text-2);font-size:13px"><input type="checkbox" data-edstab ${g.stabilize ? "checked" : ""} style="width:18px;height:18px;accent-color:var(--accent)">Stabilisera skakig bild${g.stabilize == null ? ' <span class="muted">(AI: automatiskt)</span>' : ""}</label></div>
    <p class="muted" style="margin:0;font-size:12px"><b>Original</b> = som kameran filmade (ingen AI-vitbalans, disborttagning eller färgsättning). <b>Stilens färg</b> = AI:ns korrigering plus filmstilens färg. Jämför med Före/efter överst.</p>`;
}

const TEXT_STYLES = { doc: "Dokumentär – namnskylt", fun: "Humor – pratbubbla", title: "Rubrik", caption: "Undertext",
  place: "Plats – reseskylt", meme: "Meme", minimal: "Minimal", chapter: "Kapitel",
  tiktok: "TikTok – vit ruta", hook: "Krok – stor och fet", pov: "POV", highlight: "Överstruken", neon: "Neon",
  number: "Nummer (topplista)", quote: "Citat" };
const TEXT_ANIMS = { "": "Stilens egen", fade: "Tona in", typewriter: "Skrivmaskin", words: "Ord för ord", pop: "Pop",
  slide_up: "Glid upp", slide_left: "Glid in från sidan", zoom: "Zooma in", glitch: "Glitch", highlight: "Överstrykning",
  bounce: "Gungar", karaoke: "Karaoke" };
const TEXT_FONTS = { "": "Stilens egen", sans: "Fet", impact: "Anton", bebas: "Bebas Neue", black: "Archivo Black",
  marker: "Tuschpenna", script: "Skrivstil", comic: "Serietidning", serif: "Elegant" };
const TEXT_TEMPLATES = [
  ["pov", "POV: du hittar …", "pov"], ["hook", "Vänta tills slutet", "hook"], ["number", "1", "number"],
  ["tiktok", "Det här hände på dyket", "tiktok"], ["highlight", "Bästa dyket hittills", "highlight"],
  ["quote", "Havet minns allt", "quote"], ["neon", "Gullmarsfjorden", "neon"]];
const POS9 = [[0.5, 0.16, "↑"], [0.5, 0.5, "•"], [0.5, 0.76, "↓"], [0.24, 0.16, "↖"], [0.76, 0.16, "↗"], [0.24, 0.76, "↙"], [0.76, 0.76, "↘"]];
const TONES = { doc: "Dokumentär", fun: "Humor", travel: "Reseberättare", poetic: "Poetisk", short: "Kort och käck", social: "Sociala medier – krok och POV" };

function ovBars(p, total) {
  // texter som överlappar i tid läggs på egna rader
  const at = Object.fromEntries(p.shots.map((s, i) => [s.uid, { at: s.at, i }]));
  const items = [];
  const title = (p.effects || {}).title;
  if (title && p.shots.length) items.push({ a: 0, b: Math.min(3.5, p.shots[0].duration), html: (l, w, top) => `<button class="ovbar st-title" data-act="ed-title-focus" style="left:${l}%;width:${w}%;top:${top}px" title="Titel: ${esc(title)}">${esc(title)}</button>` });
  (p.overlays || []).forEach((o) => {
    const s = at[o.shot_uid];
    if (!s) return;
    const a = s.at + Number(o.offset || 0);
    items.push({ a, b: a + Number(o.dur || 2), html: (l, w, top) => `<div role="button" tabindex="0" class="ovbar st-${o.style} ${state.ed.ov === o.id ? "sel" : ""}" data-ovsel="${o.id}" data-edshot="${s.i}" style="left:${l}%;width:${w}%;top:${top}px" title="${esc(o.text)} – dra för att flytta, dra i kanterna för att ändra längden"><span class="ovh l" data-ovh="l"></span><span class="ovtxt">${o.auto ? "AI · " : ""}${esc(o.text)}</span><span class="ovh r" data-ovh="r"></span></div>` });
  });
  items.sort((x, y) => x.a - y.a);
  const ends = [];
  const html = items.map((it) => {
    let lane = ends.findIndex((e) => e <= it.a + 0.05);
    if (lane < 0) { lane = ends.length; ends.push(0); }
    ends[lane] = it.b;
    const l = (it.a / total) * 100, w = Math.max(2, Math.min(100 - l, ((it.b - it.a) / total) * 100));
    return it.html(l, w, lane * 24);
  }).join("");
  return { html, lanes: Math.max(1, ends.length) };
}

const AUTO_LABEL = { label: "Artnamn", chapter: "Kapitel", pop: "Pratbubbla" };
function ovTime(p, o) {
  const s = p.shots.find((x) => x.uid === o.shot_uid);
  return s ? s.at + Number(o.offset || 0) : 1e9;
}
function speechRows(p) {
  const cl = clips();
  const rows = [];
  p.shots.forEach((s, i) => {
    const c = cl.find((x) => x.id === s.clip_id);
    const segs = ((c && c.speech) || {}).segments || [];
    const sp = (s.fx || {}).speed || 1;
    if (Math.abs(sp - 1) > 0.1) return;
    const a = s.src_start, b = s.src_start + s.duration;
    segs.forEach((g, k) => {
      if (g.end > a + 0.1 && g.start < b - 0.1) rows.push({ t: s.at + Math.max(0, g.start - a), i, clip: c.id, k, text: g.text });
    });
  });
  return rows;
}
function freeTextsForm(p) {
  const n = p.shots.length;
  const sorted = (p.overlays || []).slice().sort((a, b) => ovTime(p, a) - ovTime(p, b));
  const nAuto = sorted.filter((o) => o.auto).length;
  const items = sorted.map((o) => {
    const idx = Math.max(0, p.shots.findIndex((s) => s.uid === o.shot_uid));
    const sel = state.ed.ov === o.id;
    const opt = (obj, cur) => Object.entries(obj).map(([k, l]) => `<option value="${k}" ${(cur || "") === k ? "selected" : ""}>${l}</option>`).join("");
    const more = sel ? `
      <div class="row" style="flex-wrap:nowrap;gap:6px;font-size:12px">
        <label class="stack" style="gap:2px;flex:1">Animation<select class="selfield" data-ovf="anim">${opt(TEXT_ANIMS, o.anim)}</select></label>
        <label class="stack" style="gap:2px;flex:1">Typsnitt<select class="selfield" data-ovf="font">${opt(TEXT_FONTS, o.font)}</select></label></div>
      <label class="sl" style="font-size:12px"><span>Storlek</span><input type="range" min="0.5" max="2.2" step="0.05" value="${o.size || 1}" data-ovf="size" style="accent-color:var(--accent)"><span class="num">${Math.round((o.size || 1) * 100)} %</span></label>
      <div class="row" style="gap:10px;font-size:12px;align-items:center">
        <label class="row" style="gap:6px">Färg<input type="color" data-ovf="color" value="${o.color || "#ffffff"}" style="width:30px;height:24px;border:0;background:none;padding:0"></label>
        <label class="row" style="gap:6px">Ruta<input type="color" data-ovf="box" value="${o.box && o.box !== "none" ? o.box.slice(0, 7) : "#000000"}" style="width:30px;height:24px;border:0;background:none;padding:0"></label>
        <button class="btn small" data-ovreset="${o.id}" title="Stilens färger och typsnitt">Återställ</button></div>
      <div class="stack" style="gap:4px;font-size:12px"><span class="muted">Plats – välj här eller klicka i bilden</span>
        <div class="row" style="gap:4px;flex-wrap:wrap">${POS9.map(([x, y, l]) => `<button class="btn icon small" data-ovpos="${o.id}" data-x="${x}" data-y="${y}" aria-label="Placera">${l}</button>`).join("")}
          <button class="btn small" data-ovpos="${o.id}" data-x="" data-y="" ${o.x == null ? 'aria-pressed="true"' : ""}>Stilens plats</button></div></div>` : "";
    return `<div class="ovitem ${sel ? "sel" : ""}" data-ovid="${o.id}">
      <div class="ovmeta"><span class="num">${fmtDur(ovTime(p, o))}</span> · klipp ${idx + 1}${o.auto ? ` <span class="badge" style="position:static">AI · ${AUTO_LABEL[o.auto] || "auto"}</span>` : ""}</div>
      <div class="row" style="flex-wrap:nowrap;gap:6px">
        <select class="selfield" data-ovf="style" style="flex:1 1 auto">${opt(TEXT_STYLES, o.style)}</select>
        ${sel ? "" : `<button class="btn small" data-ovsel="${o.id}" data-edshot="${idx}">Effekter</button>`}
        <button class="btn icon small" data-ovdel="${o.id}" aria-label="Ta bort texten">${icon("trash", 14)}</button></div>
      <textarea class="field" data-ovf="text" rows="${o.text.length > 40 ? 2 : 1}" maxlength="160" placeholder="Text">${esc(o.text)}</textarea>
      <input class="field" data-ovf="sub" value="${esc(o.sub || "")}" maxlength="120" placeholder="Andra raden (valfri)">
      <div class="row" style="flex-wrap:nowrap;gap:6px;font-size:12px">
        <label class="stack" style="gap:2px;flex:1">Klipp<select class="selfield" data-ovf="i">${p.shots.map((_, k) => `<option value="${k}" ${k === idx ? "selected" : ""}>${k + 1}</option>`).join("")}</select></label>
        <label class="stack" style="gap:2px;flex:1.4">Start (s)<span class="row" style="gap:3px;flex-wrap:nowrap"><button class="btn icon small" data-ovnudge="${o.id}" data-d="-0.5" aria-label="Tidigare">‹</button><input class="field" type="number" step="0.1" min="0" data-ovf="offset" value="${Number(o.offset).toFixed(1)}"><button class="btn icon small" data-ovnudge="${o.id}" data-d="0.5" aria-label="Senare">›</button></span></label>
        <label class="stack" style="gap:2px;flex:1">Längd (s)<input class="field" type="number" step="0.1" min="0.6" max="15" data-ovf="dur" value="${Number(o.dur).toFixed(1)}"></label></div>${more}</div>`;
  }).join("");
  const tpl = `<div class="stack" style="gap:6px"><span class="muted" style="font-size:12px">Snabbmallar för sociala medier – läggs på klipp ${state.ed.i + 1}</span>
    <div class="chips">${TEXT_TEMPLATES.map(([k, t, st]) => `<button class="chip" data-ovtpl="${st}" data-text="${esc(t)}">${esc(TEXT_STYLES[st].split(" –")[0])}</button>`).join("")}</div></div>`;
  const tone = state.ed.tone || p.overlay_tone || "doc";
  return `<div class="stack" style="gap:10px;padding-top:14px;border-top:1px solid var(--line)">
    <span class="flabel">Texter i filmen</span>
    <div class="row" style="flex-wrap:nowrap;gap:6px"><select class="selfield" data-edtone style="flex:1 1 auto">${Object.entries(TONES).map(([k, l]) => `<option value="${k}" ${k === tone ? "selected" : ""}>${l}</option>`).join("")}</select>
      <button class="btn small primary" data-act="ov-suggest" ${state.ed.suggesting ? "disabled" : ""}>${state.ed.suggesting ? "Skriver …" : `${icon("spark", 14)}Föreslå texter`}</button></div>
    <span class="muted" style="font-size:12px">${state.info && state.info.llm ? "Djupanalysen skriver texter utifrån vad som händer i klippen." : "Förslagen bygger på vad AI:n känt igen i klippen. Med djupanalysen (Mac) skrivs de fritt utifrån vad som händer."} Förslaget ersätter de automatiska texterna – allt går att ändra och ångra.</span>
    <div class="spread" style="align-items:center"><span class="flabel">Alla texter · ${sorted.length}</span>
      ${nAuto ? `<button class="btn small" data-act="ov-clear-auto">Ta bort AI:ns ${nAuto}</button>` : ""}</div>
    ${items || '<span class="muted" style="font-size:13px">Inga texter i filmen än.</span>'}
    <button class="btn small" data-act="ov-add">+ Lägg till text på klipp ${state.ed.i + 1}${n ? "" : ""}</button>
    ${tpl}
    ${speechSection(p)}</div>`;
}

function speechSection(p) {
  const rows = speechRows(p);
  if (!rows.length) return "";
  const on = effectsOn().speech !== false;
  return `<div class="stack" style="gap:8px;padding-top:12px;border-top:1px solid var(--line)">
    <div class="spread" style="align-items:center"><span class="flabel">Talundertexter · ${rows.length}</span>
      <button class="btn small" data-effect="speech">${on ? "Stäng av" : "Slå på"}</button></div>
    <span class="muted" style="font-size:12px">Det Whisper hörde. Rätta orden här – ändringen gäller klippet i alla filmer.</span>
    ${rows.map((r) => `<div class="ovitem"><div class="ovmeta"><span class="num">${fmtDur(r.t)}</span> · klipp ${r.i + 1} <span class="badge" style="position:static">Tal</span></div>
      <div class="row" style="flex-wrap:nowrap;gap:6px"><textarea class="field" rows="${r.text.length > 44 ? 2 : 1}" data-speechclip="${r.clip}" data-speechk="${r.k}">${esc(r.text)}</textarea>
      <button class="btn icon small" data-speechdel="${r.clip}" data-k="${r.k}" aria-label="Ta bort repliken">${icon("trash", 14)}</button></div></div>`).join("")}</div>`;
}

function edInspectorText(p) {
  const langs = (state.info && state.info.languages) || { sv: "Svenska" };
  const lang = state.ed.lang || "sv";
  const sel = `<label class="stack" style="gap:6px"><span class="flabel">Språk</span><select class="selfield" data-edlang>${Object.entries(langs).map(([k, l]) => `<option value="${k}" ${k === lang ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>`;
  if (lang !== "sv") {
    if (!state.ed.texts || state.ed.texts.lang !== lang || state.ed.texts.prop !== p.id) {
      state.ed.texts = { lang, prop: p.id, loading: true };
      api("POST", `/api/p/${state.pid}/proposal/${p.id}/texts`, { lang }).then((r) => { state.ed.texts = Object.assign(r, { prop: p.id }); render(); }).catch(fail);
      return `${sel}<span class="muted">Hämtar texterna …</span>`;
    }
    if (state.ed.texts.loading) return `${sel}<span class="muted">Hämtar texterna …</span>`;
    const tx = state.ed.texts.texts, orig = state.ed.texts.original;
    const rows = p.shots.map((s, i) => tx.shots[i] ? `<div class="stack" style="gap:6px;padding-top:8px;border-top:1px solid var(--line)">
        <span class="muted" style="font-size:12px">Klipp ${i + 1} · original: ${esc(orig.shots[i] ? orig.shots[i].text : "")}</span>
        <input class="field" data-i18ntext="${i}" value="${esc(tx.shots[i].text)}" maxlength="60">
        ${tx.shots[i].sub || (orig.shots[i] && orig.shots[i].sub) ? `<input class="field" data-i18nsub="${i}" value="${esc(tx.shots[i].sub || "")}" maxlength="60">` : ""}</div>` : "").join("");
    return `${sel}
      <label class="stack" style="gap:6px"><span class="flabel">Titel</span><span class="muted" style="font-size:12px">Original: ${esc(orig.title || "–")}</span>
        <input class="field" id="i18nTitle" value="${esc(tx.title || "")}" maxlength="80"></label>
      ${rows}
      ${state.ed.texts.missing.length ? `<p class="muted" style="margin:0;font-size:12px">${state.ed.texts.missing.length} egna texter är inte översatta än. De översätts av djupanalysen vid export på Macen – eller skriv in dem här.</p>` : ""}
      <div class="row"><button class="btn small primary" data-act="ed-i18n-save">Spara ${esc(langs[lang])}</button></div>`;
  }
  const title = (p.effects || {}).title || "";
  if (isPromo(p)) return sel + promoForm(p) + freeTextsForm(p);
  const lyr = p.style === "mv_lyrics" ? lyricsForm(p) : "";
  return `${sel}${lyr}<label class="stack" style="gap:6px"><span class="flabel">Titel i början av filmen</span>
      <div class="row" style="flex-wrap:nowrap;gap:6px"><input class="field" id="edTitle" data-edtitle value="${esc(title)}" maxlength="80" placeholder="Ingen titel" style="flex:1 1 auto">
      ${title ? `<button class="btn icon small" data-act="ed-title-clear" aria-label="Ta bort titeln">${icon("trash", 14)}</button>` : ""}</div></label>
    ${freeTextsForm(p)}`;
}

function promoDraft(p) {
  if (!state.ed.promo || state.ed.promo.prop !== p.id) {
    const pr = p.promo || {};
    state.ed.promo = { prop: p.id, hook: pr.hook || "", points: (pr.points || []).join("\n"), cta: pr.cta || "",
      url: pr.url || "", logo: pr.logo || "", endcard: pr.endcard !== false, all: false };
  }
  return state.ed.promo;
}

function promoForm(p) {
  const d = promoDraft(p);
  const trailer = p.style === "trailer";
  const last = P().promo_last;
  const empty = !d.hook && !d.points && !d.cta && !d.url && !d.logo;
  const nPromo = (P().proposals || []).filter((x) => x.id !== p.id && x.promo && (x.style === "trailer") === trailer).length;
  const logoName = d.logo ? d.logo.split(/[\\/]/).pop() : "";
  return `<p class="muted" style="margin:0;font-size:13px">${trailer ? "Texterna är valfria. Utan egen slutbild visas filmens titel." : "Allt är valfritt och kan ändras när som helst – samma film kan användas för olika erbjudanden."}</p>
    ${empty && last ? `<button class="btn small" data-act="promo-last">Fyll i senast använda texter</button>` : ""}
    <label class="stack" style="gap:6px"><span class="flabel">${trailer ? "Inledande text" : "Krok – de första sekunderna"}</span>
      <textarea class="field" rows="2" data-promo="hook" maxlength="120" placeholder="${trailer ? "I mörkret under ytan …" : "Dyk med oss i Gullmarsfjorden"}">${esc(d.hook)}</textarea></label>
    <label class="stack" style="gap:6px"><span class="flabel">${trailer ? "Textskyltar (en per rad)" : "Säljpunkter (en per rad)"}</span>
      <textarea class="field" rows="3" data-promo="points" placeholder="${trailer ? "… väntar något\nsom ingen har sett" : "Små grupper\nAll utrustning ingår"}">${esc(d.points)}</textarea></label>
    <label class="stack" style="gap:6px"><span class="flabel">${trailer ? "Slutbild (titel eller datum)" : "Uppmaning på slutbilden"}</span>
      <input class="field" data-promo="cta" maxlength="80" value="${esc(d.cta)}" placeholder="${trailer ? "Premiär i vår" : "Boka din plats"}"></label>
    <label class="stack" style="gap:6px"><span class="flabel">Webbadress eller kontakt</span>
      <input class="field" data-promo="url" maxlength="80" value="${esc(d.url)}" placeholder="www.exempel.se"></label>
    <div class="stack" style="gap:6px"><span class="flabel">Logga</span>
      <div class="row">${logoName ? `<span class="tag">${esc(logoName)}</span><button class="btn small" data-act="promo-logo-clear">Ta bort</button>` : '<span class="muted" style="font-size:13px">Ingen logga</span>'}
      ${remote() ? "" : `<button class="btn small" data-act="promo-logo">${logoName ? "Byt" : "Välj logga"}</button>`}</div></div>
    <label class="row" style="gap:10px;font-size:14px"><input type="checkbox" data-promo="endcard" ${d.endcard ? "checked" : ""} style="width:18px;height:18px;accent-color:var(--accent)">Slutbild med logga och uppmaning</label>
    ${nPromo ? `<label class="row" style="gap:10px;font-size:14px"><input type="checkbox" data-promo="all" ${d.all ? "checked" : ""} style="width:18px;height:18px;accent-color:var(--accent)">Använd i alla ${nPromo + 1} ${trailer ? "trailrar" : "reklamförslag"}</label>` : ""}
    <div class="row"><button class="btn small primary" data-act="promo-save">Spara texterna</button></div>`;
}

function lyricsForm(p) {
  const ly = p.lyrics || {};
  const bpl = ly.beats_per_line || 8;
  return `<div class="stack" style="gap:8px;padding-bottom:14px;border-bottom:1px solid var(--line)">
    <label class="stack" style="gap:6px"><span class="flabel">Sångtext (en rad visas i taget, tom rad = paus)</span>
      <textarea class="field" rows="7" id="lyLines" placeholder="Under ytan\ndär tystnaden bor">${esc((ly.lines || []).join("\n"))}</textarea></label>
    <div class="row" style="flex-wrap:nowrap;gap:10px">
      <label class="stack" style="gap:6px;flex:1"><span class="flabel">Börjar vid (s)</span><input class="field" id="lyStart" type="number" min="0" step="0.5" value="${Number(ly.start || 0)}"></label>
      <label class="stack" style="gap:6px;flex:1"><span class="flabel">Varje rad</span><select class="selfield" id="lyBpl">${[[4, "1 takt"], [8, "2 takter"], [16, "4 takter"]].map(([v, l]) => `<option value="${v}" ${v === bpl ? "selected" : ""}>${l}</option>`).join("")}</select></label></div>
    <div class="row"><button class="btn small primary" data-act="lyrics-save">Spara sångtexten</button></div>
    <p class="muted" style="margin:0;font-size:12px">${p.bpm ? `Raderna följer låtens takt (${dec(p.bpm, 0)} BPM).` : "Välj musik först så följer raderna takten."}</p></div>`;
}

function viewEdit() {
  const p = edProp() || propById(state.shown[0]) || ((P() && P().proposals) || [])[0];
  if (!p) return `<main class="main"><div class="empty">Skapa ett filmförslag först.</div></main>`;
  state.ed.prop = p.id;
  const i = Math.min(state.ed.i, p.shots.length - 1);
  state.ed.i = i;
  const s = p.shots[i];
  const tab = state.ed.tab;
  const prev = p.renders && p.renders.preview;
  const busyHere = running(`render:preview:${p.id}`);
  const tabs = [["clip", "Klipp"], ["color", "Färg"], ["text", "Text"]].map(([k, l]) => `<button role="tab" aria-selected="${tab === k}" aria-pressed="${tab === k}" data-edtab="${k}">${l}</button>`).join("");
  const inspector = tab === "color" ? edInspectorColor(p) : tab === "text" ? edInspectorText(p) : edInspectorClip(p, s);
  const src = frameUrl(s.clip_id, s.src_start + Math.min(s.duration, 1.5) * ((s.fx || {}).speed || 1), 640);
  const cx = s.cx ?? 0.5, cy = s.cy ?? 0.5;
  return `<main class="main wide edmain">
    <div class="spread edhead"><div class="head"><h1>${esc(p.title || p.style_label)}</h1>
      <p class="lead">${esc(p.style_label)} · ${p.platform ? `${esc(platformLabel(p.platform))} · ` : ""}${p.format} · ${fmtDur(p.length)}</p></div>
      <div class="row">${platformSelect(p)}${lengthSelect(p)}<button class="btn" data-act="ed-undo" ${(p.undo_n || (p.history || []).length) ? "" : "disabled"}>${svgi(ICO.undo, 16)}Ångra</button>
        ${prev ? "" : `<button class="btn" data-preview="${p.id}" ${busyHere ? "disabled" : ""}>${icon("play", 14)}${busyHere ? "Renderar …" : "Förhandsvisa filmen"}</button>`}
        <button class="btn primary" data-export="${p.id}">Exportera</button></div></div>
    <div class="edgrid">
      <div class="edleft">
        <section class="edstage">
          ${edStage(p, i, s, src, cx, cy, tab, prev, busyHere)}
        </section>
        ${edTimeline(p)}
      </div>
      <aside class="edinsp"><div class="seg edtabs" role="tablist" style="grid-template-columns:repeat(3,minmax(0,1fr))">${tabs}</div>${inspector}</aside>
    </div>
  </main>`;
}

const STAGE_MODES = [["clip", "Klippet"], ["compare", "Före/efter"], ["side", "Sida vid sida"], ["film", "Hela filmen"]];
function edStage(p, i, s, src, cx, cy, tab, prev, busyHere) {
  const mode = state.ed.mode || "clip";
  const [fw, fh] = p.format.split(":").map(Number);
  const ar = `${fw}/${fh};width:min(100%, calc(var(--stageh) * ${(fw / fh).toFixed(4)}));height:auto`;
  const sp = (state.ed.shotPrev || {})[i];
  const fresh = sp && sp.stamp === state.ed.stamp;
  const after = stillUrl(p, i, true), before = stillUrl(p, i, false);
  const busy = state.ed.shotBusy === i;
  const seg = `<div class="seg stagemodes" role="tablist">${STAGE_MODES.map(([k, l]) => `<button role="tab" data-edmode="${k}" aria-pressed="${mode === k}" aria-selected="${mode === k}">${l}</button>`).join("")}</div>`;
  const status = busy ? `<span class="stagestat">${icon("spark", 12)}Uppdaterar klippet …</span>` : "";
  let body = "";
  if (mode === "clip" && tab === "text") {
    body = `<figure class="edfig"><div class="edstill placer" style="aspect-ratio:${ar}" data-edplace>
      ${fresh ? `<video id="edClipVid" src="${mediaUrl("shots", sp.file)}" poster="${after}" autoplay loop muted playsinline></video>`
        : `<img id="edStill" alt="Klicka för att placera texten" src="${after}">`}${status}${p.format !== "16:9" ? '<span class="safezone"></span>' : ""}</div>
      <figcaption>Klicka i bilden för att flytta vald text dit.${p.format !== "16:9" ? " Streckat: där appens knappar inte täcker." : ""}</figcaption></figure>`;
  } else if (mode === "clip") {
    body = `<figure class="edfig"><div class="edstill" style="aspect-ratio:${ar}">
      ${fresh ? `<video id="edClipVid" src="${mediaUrl("shots", sp.file)}" poster="${after}" autoplay loop playsinline controls></video>`
        : `<img id="edStill" alt="Klippet som det ser ut i filmen" src="${after}">`}${status}</div>
      <figcaption>Klipp ${i + 1} som i filmen – effekter, färg, texter och musik. Uppdateras efter varje ändring.</figcaption></figure>`;
  } else if (mode === "compare") {
    const x = state.ed.split ?? 50;
    body = `<figure class="edfig"><div class="edstill cmp" style="aspect-ratio:${ar}" data-cmp>
      <img alt="Före" src="${before}"><img id="edStill" class="after" alt="Efter" src="${after}" style="clip-path:inset(0 0 0 ${x}%)">
      <span class="cmpline" style="left:${x}%"></span><span class="cmptag l">Före</span><span class="cmptag r">Efter</span>
      <input type="range" min="0" max="100" value="${x}" data-cmpx aria-label="Dra för att jämföra före och efter"></div>
      <figcaption>Dra över bilden: vänster om linjen är originalet, höger är resultatet.</figcaption></figure>`;
  } else if (mode === "side") {
    const proxy = sp && sp.proxy;
    const t0 = s.src_start, t1 = s.src_start + s.duration * ((s.fx || {}).speed || 1);
    body = `<div class="sidebyside">
      <figure class="edfig"><figcaption>Original</figcaption><div class="edorig">
        ${proxy ? `<video id="edOrigVid" src="${mediaUrl("proxies", proxy)}#t=${t0.toFixed(2)},${t1.toFixed(2)}" muted playsinline autoplay data-loop="${t0},${t1}"></video>` : `<img alt="" src="${src}">`}</div></figure>
      <figure class="edfig"><figcaption>I filmen</figcaption><div class="edstill" style="aspect-ratio:${ar}">
        ${fresh ? `<video id="edClipVid" src="${mediaUrl("shots", sp.file)}" poster="${after}" autoplay loop playsinline muted></video>` : `<img id="edStill" alt="" src="${after}">`}${status}</div></figure></div>`;
  } else {
    body = prev && !busyHere ? `<video class="edvideo" controls playsinline preload="metadata" src="${mediaUrl("renders", prev)}?v=${p.renders.v || 0}"></video>`
      : busyHere ? `<div class="progress"><div class="spread" style="font-size:13px"><span class="muted" data-live-text>${esc(job().message || "")}</span><span class="num muted" data-live-pct></span></div><div class="bar"><div data-live-fill style="width:0%"></div></div></div>`
      : `<div class="empty" style="padding:28px">Filmen har ändrats sedan den senaste förhandsvisningen.<br><button class="btn primary" data-preview="${p.id}" style="margin-top:12px">${icon("play", 14)}Förhandsvisa hela filmen</button></div>`;
  }
  if (mode === "side") setTimeout(wireOrigLoop, 0);
  setTimeout(fitStage, 0);
  const source = tab === "clip" && mode !== "side" && mode !== "film" ? `<figure class="edfig"><figcaption>Originalbild – klicka för att flytta utsnittet</figcaption>
      <div class="edsrc" data-edsrc><img alt="Originalbilden" src="${src}"><span class="edring" style="left:${cx * 100}%;top:${cy * 100}%"></span></div></figure>` : "";
  return `${seg}<div class="edviews">${body}${source}</div>`;
}

/* Förhandsvisning av det valda klippet: görs automatiskt efter varje ändring (bara den senaste räknas) */
let shotTimer = null, shotToken = 0;
function requestShotPreview(delay = 350) {
  clearTimeout(shotTimer);
  shotTimer = setTimeout(runShotPreview, delay);
}
async function runShotPreview() {
  const p = edProp();
  if (!p || state.view !== "edit") return;
  const i = state.ed.i, stamp = state.ed.stamp, token = ++shotToken;
  const have = (state.ed.shotPrev || {})[i];
  if (have && have.stamp === stamp) return;
  state.ed.shotBusy = i;
  paintStage();
  try {
    const r = await api("POST", `/api/p/${state.pid}/proposal/${p.id}/shotpreview`, { i });
    if (token !== shotToken || state.ed.stamp !== stamp) return;
    state.ed.shotPrev = Object.assign({}, state.ed.shotPrev, { [i]: { file: r.file, proxy: r.proxy, stamp } });
  } catch (e) {
    if (token === shotToken) toast(e.message || String(e));
  } finally {
    if (token === shotToken) { state.ed.shotBusy = null; paintStage(); }
  }
}
function paintStage() {
  const p = edProp();
  const st = document.querySelector(".edstage");
  if (!p || !st || state.view !== "edit") return;
  const i = Math.min(state.ed.i, p.shots.length - 1);
  const s = p.shots[i];
  const src = frameUrl(s.clip_id, s.src_start + Math.min(s.duration, 1.5) * ((s.fx || {}).speed || 1), 640);
  st.innerHTML = edStage(p, i, s, src, s.cx ?? 0.5, s.cy ?? 0.5, state.ed.tab, p.renders && p.renders.preview, running(`render:preview:${p.id}`));
  wireOrigLoop();
  fitStage();
}
function fitStage() {
  const main = document.querySelector(".edmain");
  const left = document.querySelector(".edleft");
  if (!main || !left) return;
  if (window.innerWidth <= 980) { main.style.removeProperty("--stageh"); return; }
  const top = left.getBoundingClientRect().top + window.scrollY;
  const tl = document.getElementById("edTimeline");
  const tlH = tl ? tl.getBoundingClientRect().height : 220;
  const st = document.querySelector(".edstage");
  const still = st && st.querySelector(".edstill");
  const chrome = st && still ? st.getBoundingClientRect().height - still.getBoundingClientRect().height : 120;
  const h = Math.max(180, Math.min(820, window.innerHeight - top - tlH - chrome - 30));
  main.style.setProperty("--stageh", `${Math.round(h)}px`);
}
window.addEventListener("resize", () => { if (state.view === "edit") fitStage(); });

function wireOrigLoop() {
  const v = document.getElementById("edOrigVid");
  if (!v || !v.dataset.loop) return;
  const [a, b] = v.dataset.loop.split(",").map(Number);
  v.addEventListener("timeupdate", () => { if (v.currentTime >= b - 0.05) { v.currentTime = a; v.play().catch(() => {}); } });
}

let gradeTimer = null, fitTimer = null;
function onGradeInput(key, value) {
  const p = edProp();
  if (!p) return;
  const g = curGrade(p);
  g[key] = Number(value);
  const v = document.querySelector(`[data-edgv="${key}"]`);
  if (v) v.textContent = Math.round(Number(value) * 100);
  stageGrade(g);
}
function stageGrade(g) {
  const p = edProp();
  const s = p.shots[state.ed.i];
  if (state.ed.scope === "shot") s.grade = g; else p.grade = g;
  clearTimeout(gradeTimer);
  gradeTimer = setTimeout(() => edit("grade", { scope: state.ed.scope, i: state.ed.i, grade: g }, { quiet: true }), 350);
}

/* ================= händelser ================= */
document.addEventListener("click", async (ev) => {
  const t = ev.target.closest("button, [data-edsrc], [data-edplace], [data-ovsel]");
  if (!t) return;
  const d = t.dataset;
  if (d.edsrc !== undefined) {
    const r = t.getBoundingClientRect();
    const cx = (ev.clientX - r.left) / r.width, cy = (ev.clientY - r.top) / r.height;
    const ring = t.querySelector(".edring");
    if (ring) { ring.style.left = `${cx * 100}%`; ring.style.top = `${cy * 100}%`; }
    return edit("center", { i: state.ed.i, cx, cy }, { quiet: true });
  }
  if (d.qmove) { state.queue = await api("POST", `/api/queue/${d.qmove}/move`, { dir: Number(d.dir) }); return render(); }
  if (d.qretry) { try { state.queue = await api("POST", `/api/queue/${d.qretry}/retry`, {}); state.expectJob = true; toast("Jobbet ligger i kön igen.", true); } catch (e) { fail(e); } loadQueue(); return render(); }
  if (d.qdismiss) { state.queue = await api("POST", `/api/queue/${d.qdismiss}/dismiss`, {}); return render(); }
  if (d.qcancel) { state.queue = await api("POST", `/api/queue/${d.qcancel}/cancel`, {}); loadQueue(); return render(); }
  if (d.qopen) {
    await loadProject(d.qopen);
    state.view = (P().proposals || []).length ? "proposals" : "analyze";
    return render();
  }
  if (d.ft) {
    const pl = state.setup.plans[d.ft];
    pl.on = !pl.on;
    if (d.ft === "auto" && pl.on) Object.entries(state.setup.plans).forEach(([k, x]) => { if (k !== "auto") x.on = false; });
    if (d.ft !== "auto" && pl.on) state.setup.plans.auto.on = false;
    return render();
  }
  if (d.plantab) { state.planTab = d.plantab; return render(); }
  if (d.explat) {
    const set = new Set(state.exportPlats);
    if (set.has(d.explat)) set.delete(d.explat); else set.add(d.explat);
    state.exportPlats = [...set];
    return render();
  }
  if (d.exlang) {
    const set = new Set(state.exportLangs || ["sv"]);
    if (set.has(d.exlang)) set.delete(d.exlang); else set.add(d.exlang);
    if (!set.size) set.add("sv");
    state.exportLangs = [...set];
    return render();
  }
  if (d.dvoff) return diveOffset(Number(d.dvoff));
  if (d.edit) return openEditor(d.edit);
  if (d.ovsel && window.__ovDragged && Date.now() - window.__ovDragged < 400) return undefined;
  if (d.ovsel) { state.ed.ov = d.ovsel; state.ed.tab = "text"; }
  if (d.preview && state.view === "edit") state.ed.mode = "film";
  if (d.edshot !== undefined) { state.ed.i = Number(d.edshot); state.ed.alts = null; render(); return requestShotPreview(150); }
  if (d.edtab) { state.ed.tab = d.edtab; return render(); }
  if (d.edmode) { state.ed.mode = d.edmode; paintStage(); document.querySelectorAll("[data-edmode]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.edmode === d.edmode))); return requestShotPreview(0); }
  if (d.edfitbg) return edit("fit", { i: state.ed.i, bg: d.edfitbg });
  if (d.edmatch) { await edit("match", { on: d.edmatch === "on" }); return loadMatchInfo(); }
  if (d.edtrim) { const s = edProp().shots[state.ed.i]; return edit("trim", { i: state.ed.i, duration: s.duration + Number(d.edtrim) }); }
  if (d.edspeed) return edit("speed", { i: state.ed.i, mode: d.edspeed });
  if (d.edfx) return edit("fx", { i: state.ed.i, effect: d.edfx });
  if (d.ovdel) return edit("overlay_delete", { id: d.ovdel });
  if (d.ovnudge) {
    const pp = edProp();
    const o = (pp.overlays || []).find((x) => x.id === d.ovnudge);
    if (!o) return undefined;
    const t0 = ovTime(pp, o) + Number(d.d);
    const tot = ovFilmTotal(pp);
    const start = Math.max(0, Math.min(tot - 0.3, t0));
    let i = pp.shots.findIndex((s) => start >= s.at - 0.01 && start < s.at + s.duration);
    if (i < 0) i = pp.shots.length - 1;
    state.ed.ov = o.id;
    return edit("overlay_update", { id: o.id, i, offset: Math.round((start - pp.shots[i].at) * 10) / 10 });
  }
  if (d.speechdel) return speechEdit(d.speechdel, Number(d.k), "", true);
  if (d.ovpos) return edit("overlay_update", { id: d.ovpos, x: d.x === "" ? null : Number(d.x), y: d.y === "" ? null : Number(d.y) });
  if (d.ovreset) return edit("overlay_update", { id: d.ovreset, color: "", box: "", font: "", anim: "", size: 1 });
  if (d.ovtpl) {
    await edit("overlay_add", { i: state.ed.i, text: d.text, style: d.ovtpl, offset: 0.2 });
    const ov = edProp().overlays || [];
    state.ed.ov = ov.length ? ov[ov.length - 1].id : null;
    state.ed.tab = "text";
    return render();
  }
  if (d.edplace !== undefined) {
    const pp = edProp();
    let o = (pp.overlays || []).find((x) => x.id === state.ed.ov);
    if (!o) {  // ingen vald: ta texten på det här klippet
      o = (pp.overlays || []).find((x) => x.shot_uid === pp.shots[state.ed.i].uid);
      if (!o) return toast("Klippet har ingen text. Lägg till en först.");
      state.ed.ov = o.id;
    }
    const r = t.getBoundingClientRect();
    return edit("overlay_update", { id: o.id, x: Math.round(((ev.clientX - r.left) / r.width) * 1000) / 1000, y: Math.round(((ev.clientY - r.top) / r.height) * 1000) / 1000 });
  }
  if (d.cammode) return edit("cam360", { i: state.ed.i, mode: d.cammode, ...(d.cammode === "ai" ? { yaw: 0, fov: 104 } : {}) });
  if (d.edmove) { const j = state.ed.i + Number(d.edmove); await edit("move", { i: state.ed.i, dir: Number(d.edmove) }); state.ed.i = Math.max(0, Math.min(j, edProp().shots.length - 1)); return render(); }
  if (d.edscope) { state.ed.scope = d.edscope; return render(); }
  if (d.edlook) {
    const p = edProp();
    const g = curGrade(p);
    g.look = d.edlook;
    if (state.ed.scope === "film") {
      // hela filmen: utseendet gäller alla klipp, även de som hade fått en egen färg
      const own = p.shots.filter((x) => x.grade).length;
      p.grade = g;
      p.shots.forEach((x) => { delete x.grade; });
      clearTimeout(gradeTimer);
      gradeTimer = setTimeout(() => edit("grade", { scope: "film", i: state.ed.i, grade: g, all_shots: true }, { quiet: true }), 150);
      if (own) toast(`${own} klipp hade egen färg – nu gäller ${(state.info.looks || {})[d.edlook] || "utseendet"} för hela filmen.`, true);
    } else stageGrade(g);
    return render();
  }
  if (d.edalt !== undefined) {
    const a = state.ed.alts[Number(d.edalt)];
    return edit("swap", { i: state.ed.i, alt: { clip_id: a.clip_id, start: a.start } });
  }
  switch (d.act) {
    case "queue": state.view = "queue"; await loadQueue(); return render();
    case "qpause": state.queue = await api("POST", "/api/queue/pause", { paused: !state.queue.paused }); return render();
    case "qclear": state.queue = await api("POST", "/api/queue/clear", {}); return render();
    case "setup-project": state.setup = { mode: "project", plans: defaultPlans() }; state.view = "setup"; return render();
    case "setup-cancel": state.setup = null; state.view = P() ? "proposals" : "import"; return render();
    case "setup-go": return setupGo();
    case "export-queue": return exportQueued();
    case "ed-undo": return edit("undo");
    case "ed-delete": await edit("delete", { i: state.ed.i }); state.ed.i = Math.min(state.ed.i, edProp().shots.length - 1); return render();
    case "ed-autocenter": return edit("auto_center", { i: state.ed.i });
    case "ed-grade-reset": return edit("grade_reset_shot", { i: state.ed.i });
    case "ed-enh-auto": { const g = curGrade(edProp()); g.dehaze = null; g.particles = null; g.stabilize = null; stageGrade(g); return render(); }
    case "dive-import": return diveImport();
    case "dive-auto": return diveOffset(null);
    case "dive-remove": await api("POST", `/api/p/${state.pid}/divelog/remove`, {}); state.dive = null; return render();
    case "dive-units": { const u = (settings().units || "metric") === "metric" ? "imperial" : "metric"; await saveSettings({ units: u }); return render(); }
    case "ed-i18n-save": return saveI18n();
    case "ed-title-focus": state.ed.tab = "text"; render(); setTimeout(() => { const el = document.getElementById("edTitle"); if (el) { el.focus(); el.select(); } }, 50); return undefined;
    case "ov-clear-auto": return edit("overlay_clear", { auto_only: true });
    case "ov-add": { await edit("overlay_add", { i: state.ed.i, text: "Ny text", style: (state.ed.tone && { fun: "fun", doc: "doc", travel: "place", short: "meme" }[state.ed.tone]) || "caption" }); const ov = edProp().overlays || []; state.ed.ov = ov.length ? ov[ov.length - 1].id : null; state.ed.tab = "text"; return render(); }
    case "ov-suggest": {
      state.ed.suggesting = true; render();
      try { await edit("overlay_suggest", { tone: state.ed.tone || edProp().overlay_tone || "doc" }); toast(`${(edProp().overlays || []).length} texter föreslagna (${edProp().overlay_how || "AI"}). Förhandsvisa för att se dem.`, true); } finally { state.ed.suppress = false; state.ed.suggesting = false; }
      return render();
    }
    case "promo-save": {
      const d = promoDraft(edProp());
      await edit("promo", { hook: d.hook, points: d.points, cta: d.cta, url: d.url, logo: d.logo, endcard: d.endcard, all: d.all });
      if (d.all) await loadProject(state.pid);
      toast(d.all ? "Texterna används nu i alla reklamförslag." : "Texterna är sparade. Förhandsvisa för att se dem.", true);
      return render();
    }
    case "promo-last": { const l = P().promo_last || {}; Object.assign(promoDraft(edProp()), { hook: l.hook || "", points: (l.points || []).join("\n"), cta: l.cta || "", url: l.url || "", logo: l.logo || "", endcard: l.endcard !== false }); return render(); }
    case "promo-logo": {
      const paths = await choosePaths("image");
      if (!paths.length) return undefined;
      try { const r = await api("POST", `/api/p/${state.pid}/logo`, { path: paths[0] }); promoDraft(edProp()).logo = r.logo; } catch (e) { fail(e); }
      return render();
    }
    case "promo-logo-clear": promoDraft(edProp()).logo = ""; return render();
    case "lyrics-save": return edit("lyrics", { lines: $("#lyLines").value, start: Number($("#lyStart").value || 0), beats_per_line: Number($("#lyBpl").value) });
    case "ed-grade-zero": { const g = curGrade(edProp()); ["exposure", "contrast", "saturation", "temperature", "tint", "sharpen", "vignette"].forEach((k) => { g[k] = 0; }); g.strength = 1; stageGrade(g); return render(); }
    case "ed-title": return edit("title", { text: $("#edTitle").value });
    case "ed-text": return edit("text", { i: state.ed.i, kind: $("#edTxtKind").value, text: $("#edTxt").value, sub: $("#edTxtSub").value });
    case "ed-text-clear": return edit("text", { i: state.ed.i, text: "" });
    case "ed-title-clear": return edit("title", { text: "" });
    case "ed-match-ref": await edit("match", { ref: state.ed.i }); return loadMatchInfo();
    case "ed-match-auto": await edit("match", { ref: "auto" }); return loadMatchInfo();
    case "ed-cover": await edit("cover", { i: state.ed.i, at: 0.45 }); return toast("Omslagsbilden sparas bredvid filmen vid export, med texterna.", true);
    case "ed-fit-auto": return edit("fit", { i: state.ed.i, auto: true });
    case "ed-fit-fill": return edit("fit", { i: state.ed.i, zoom: 1 });
    case "ed-fit-whole": return edit("fit", { i: state.ed.i, zoom: 0 });
    case "ed-fit-all": {
      const f = edProp().shots[state.ed.i].fit || { zoom: 1, bg: "blur" };
      await edit("fit", { all: true, zoom: f.zoom ?? 1, bg: f.bg || "blur" });
      return toast("Samma inpassning på alla klipp.", true);
    }
    case "ed-alts":
      state.ed.alts = "loading"; render();
      try { state.ed.alts = (await api("POST", `/api/p/${state.pid}/proposal/${state.ed.prop}/alternatives`, { i: state.ed.i })).alternatives; } catch (e) { state.ed.alts = null; fail(e); }
      return render();
    default: return undefined;
  }
});

document.addEventListener("input", (ev) => {
  const t = ev.target;
  if (t.dataset.promo && state.ed.promo) { state.ed.promo[t.dataset.promo] = t.type === "checkbox" ? t.checked : t.value; return undefined; }
  if (t.dataset.edgrade) return onGradeInput(t.dataset.edgrade, t.value);
  if (t.dataset.edmatchk !== undefined) { const v = document.querySelector("[data-edmatchv]"); if (v) v.textContent = Math.round(t.value * 100); return undefined; }
  if (t.dataset.cmpx !== undefined) {
    state.ed.split = Number(t.value);
    const box = t.closest("[data-cmp]");
    box.querySelector(".after").style.clipPath = `inset(0 0 0 ${t.value}%)`;
    box.querySelector(".cmpline").style.left = `${t.value}%`;
    return undefined;
  }
  if (t.dataset.edfit !== undefined) {
    const z = Number(t.value);
    const v = document.querySelector("[data-edfitval]");
    if (v) v.textContent = fitLabel(z);
    clearTimeout(fitTimer);
    fitTimer = setTimeout(() => edit("fit", { i: state.ed.i, zoom: z }, { quiet: Math.abs(z - 1) > 0.01 && !!(edProp().shots[state.ed.i].fit) }), 300);
    return undefined;
  }
  if (t.dataset.edlen !== undefined) { const v = document.querySelector("[data-edlenval]"); if (v) v.textContent = `${dec(Number(t.value))} s`; }
  if (t.dataset.cam) { const v = document.querySelector(`[data-camval="${t.dataset.cam}"]`); if (v) v.textContent = `${t.value}°`; }
  return undefined;
});

document.addEventListener("change", (ev) => {
  const t = ev.target;
  const d = t.dataset;
  if (d.edlen !== undefined) return edit("trim", { i: state.ed.i, duration: Number(t.value) });
  if (d.edtr !== undefined) return edit("transition", { i: state.ed.i, type: t.value });
  if (d.edfitcolor !== undefined) return edit("fit", { i: state.ed.i, bg: t.value });
  if (d.edtitle !== undefined) return edit("title", { text: t.value });
  if (d.speechclip) { speechEdit(d.speechclip, Number(d.speechk), t.value); return undefined; }
  if (d.edmatchskip !== undefined) { edit("match", { i: state.ed.i, skip: t.checked }).then(loadMatchInfo); return undefined; }
  if (d.edmatchk !== undefined) { edit("match", { strength: Number(t.value) }, { quiet: true }); return undefined; }
  if (d.proplen) return changeLength(d.proplen, t.value);
  if (d.edtone !== undefined) { state.ed.tone = t.value; return undefined; }
  if (d.ovf) {
    const id = t.closest("[data-ovid]").dataset.ovid;
    const v = ["offset", "dur", "i", "size"].includes(d.ovf) ? Number(t.value) : t.value;
    state.ed.ov = id;
    return edit("overlay_update", { id, [d.ovf]: v });
  }
  if (d.cam) return edit("cam360", { i: state.ed.i, [d.cam]: Number(t.value) });
  if (d.camroll !== undefined) return edit("cam360", { i: state.ed.i, roll: t.checked });
  if (d.promo && state.ed.promo && t.type === "checkbox") { state.ed.promo[d.promo] = t.checked; return undefined; }
  if (d.edstab !== undefined) { const g = curGrade(edProp()); g.stabilize = t.checked; stageGrade(g); return render(); }
  if (d.edlang !== undefined) { state.ed.lang = t.value; state.ed.texts = null; return render(); }
  if (d.platform) return changePlatform(d.platform, t.value);
  if (d.ftplat) { const pl = state.setup.plans[d.ftplat]; pl.platform = t.value; pl.length = null; return render(); }
  if (d.ftlen) { state.setup.plans[d.ftlen].length = Number(t.value); return undefined; }
  if (d.ftcount) { state.setup.plans[d.ftcount].count = Number(t.value); return undefined; }
  return undefined;
});


loadQueue();


async function saveI18n() {
  const p = edProp();
  const shots = {};
  document.querySelectorAll("[data-i18ntext]").forEach((el) => {
    const i = el.dataset.i18ntext;
    const sub = document.querySelector(`[data-i18nsub="${i}"]`);
    shots[i] = { text: el.value, sub: sub ? sub.value : "" };
  });
  await edit("i18n", { lang: state.ed.lang, title: $("#i18nTitle").value, shots });
  state.ed.texts = null;
  toast("Sparat. Exportera med språket valt för att få filmen med de här texterna.", true);
  render();
}

/* ================= dykdata ================= */
state.dive = null;
async function loadDive() {
  if (!state.pid) return;
  try { state.dive = await api("GET", `/api/p/${state.pid}/divelog`); state.divePid = state.pid; render(); } catch (_) { /* tyst */ }
}
function fmtOffset(s) {
  const sign = s < 0 ? "−" : "+";
  const a = Math.abs(Math.round(s));
  const h = Math.floor(a / 3600), m = Math.floor((a % 3600) / 60), ss = a % 60;
  return `${sign}${h ? `${h} h ` : ""}${m} min${ss ? ` ${ss} s` : ""}`;
}
function diveProfile(dv) {
  if (!dv.dives.length) return "";
  const W = 640, H = 120;
  const t0 = Math.min(...dv.dives.map((d) => d.start)), t1 = Math.max(...dv.dives.map((d) => d.start + d.duration));
  const span = Math.max(60, t1 - t0);
  const maxd = Math.max(...dv.dives.map((d) => d.max_depth)) || 10;
  const x = (t) => ((t - t0) / span) * W;
  const y = (d) => 8 + (d / maxd) * (H - 16);
  const paths = dv.dives.map((d) => `<path d="${d.profile.map((p, k) => `${k ? "L" : "M"}${x(d.start + p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join(" ")}" fill="none" stroke="var(--accent)" stroke-width="2"/>`).join("");
  const marks = dv.clip_marks.map((c) => { const tt = c.t + dv.offset; if (tt < t0 - 600 || tt > t1 + 600) return ""; return `<rect x="${x(tt).toFixed(1)}" y="0" width="${Math.max(2, (c.dur / span) * W).toFixed(1)}" height="${H}" fill="#F2C14E" opacity=".35"><title>${esc(c.name)}</title></rect>`; }).join("");
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Dykprofil med klippen markerade" style="width:100%;height:auto;background:#0B1016;border-radius:10px">${marks}${paths}</svg>`;
}
function diveCard() {
  if (remote()) return "";
  if (state.pid && state.divePid !== state.pid) { state.divePid = state.pid; loadDive(); }
  const dv = state.dive;
  const units = (settings().units || "metric");
  if (!dv || !dv.dives.length) {
    return `<section class="box" style="flex-direction:row;align-items:center;gap:14px;flex-wrap:wrap">
      <div class="stack grow" style="gap:4px"><b>Dykdata från dykdatorn</b>
      <span class="muted" style="font-size:13px">Visa djup och temperatur i filmerna. Exportera loggen från Subsurface (eller Suunto DM5) och välj filen här – UDDF, Subsurface-XML, SML och CSV fungerar.</span></div>
      <button class="btn" data-act="dive-import">Importera dyklogg</button></section>`;
  }
  const md = Math.max(...dv.dives.map((d) => d.max_depth));
  return `<section class="box stack" style="gap:12px">
    <div class="spread" style="align-items:center"><div class="stack" style="gap:4px"><b>Dykdata · ${esc(dv.source || "")}</b>
      <span class="muted" style="font-size:13px">${dv.dives.length} dyk · max ${md} m · ${dv.matched} av ${dv.clips} klipp ligger i ett dyk</span></div>
      <div class="row"><button class="btn small" data-act="dive-units">${units === "metric" ? "m · °C" : "ft · °F"}</button><button class="btn small" data-act="dive-import">Byt logg</button><button class="btn small" data-act="dive-remove">Ta bort</button></div></div>
    ${diveProfile(dv)}
    <div class="row" style="flex-wrap:wrap;gap:8px;align-items:center"><span class="muted" style="font-size:13px">Klockskillnad kamera → dykdator: <b class="num" style="color:var(--text)">${fmtOffset(dv.offset)}</b></span>
      <button class="btn small" data-dvoff="-3600">−1 h</button><button class="btn small" data-dvoff="-60">−1 min</button><button class="btn small" data-dvoff="60">+1 min</button><button class="btn small" data-dvoff="3600">+1 h</button><button class="btn small" data-act="dive-auto">Automatiskt</button></div>
    <span class="muted" style="font-size:12px">Gula fält är klippen. De ska ligga i dyket (kurvan). Slå av eller på dykdata under Effekter i förslagsvyn.</span></section>`;
}
async function diveImport() {
  try {
    const r = await api("POST", "/api/choose", { kind: "divelog" });
    if (!r.paths || !r.paths.length) return;
    state.dive = await api("POST", `/api/p/${state.pid}/divelog`, { path: r.paths[0] });
    toast(`${state.dive.dives.length} dyk inlästa – ${state.dive.matched} av ${state.dive.clips} klipp matchade.`, true);
    if (state.dive.matched) await saveSettings({ effects: Object.assign({}, settings().effects || {}, { divedata: true }) });
    render();
  } catch (e) { fail(e); }
}
async function diveOffset(delta) {
  try {
    const body = delta == null ? { auto: true } : { offset: (state.dive.offset || 0) + delta };
    state.dive = await api("POST", `/api/p/${state.pid}/divelog/offset`, body);
    (P().proposals || []).forEach((p) => { if (p.renders) delete p.renders.preview; });
    render();
  } catch (e) { fail(e); }
}

/* ================= musik: bibliotek och källor ================= */
state.music = null;
state.msearch = null;
let musicAudio = null;
const LIC_SHORT = { own: "Egen/köpt", commercial: "Fri, även reklam", cc: "Creative Commons", private: "Bara privat", unknown: "Okänd" };

async function loadMusic() {
  try { state.music = await api("GET", "/api/music"); } catch (e) { fail(e); }
  if (state.view === "music") render();
}

function playMusic(url, btn) {
  if (musicAudio && musicAudio.dataset.url === url && !musicAudio.paused) { musicAudio.pause(); render(); return; }
  if (musicAudio) musicAudio.pause();
  musicAudio = new Audio(url);
  musicAudio.dataset.url = url;
  musicAudio.play().catch(() => toast("Kunde inte spela upp låten"));
  musicAudio.onended = () => render();
  render();
}
const playing = (url) => musicAudio && musicAudio.dataset.url === url && !musicAudio.paused;

function licBadge(lic) {
  lic = lic || {};
  const code = lic.code ? ` · ${String(lic.code).toUpperCase()}` : "";
  const col = lic.kind === "private" ? "var(--warn)" : lic.kind === "unknown" ? "var(--muted)" : "var(--good)";
  return `<span class="tag" style="color:${col}">${esc(LIC_SHORT[lic.kind] || "Okänd")}${esc(code)}</span>`;
}

function viewMusic() {
  if (!state.music) { loadMusic(); return '<main class="main"><div class="empty">Läser musikbiblioteket …</div></main>'; }
  const m = state.music;
  const pm = P() && P().music;
  const kinds = m.license_kinds || {};
  const busy = (state.queue.tasks || []).some((t) => t.pid === "_music");
  const tracks = m.tracks.map((t) => `<div class="mrow">
      <button class="btn icon small" data-mplay="/api/music/file?id=${t.id}" aria-label="Spela">${playing(`/api/music/file?id=${t.id}`) ? svgi(ICO.pause, 14) : icon("play", 13)}</button>
      <div class="stack" style="gap:2px;min-width:0;flex:1 1 220px"><b class="ell">${esc(t.title || t.name)}</b><span class="muted ell" style="font-size:12px">${esc(t.artist || "")}${t.artist ? " · " : ""}${fmtDur(t.duration)} · ${dec(t.bpm, 0)} BPM · ${esc(t.character || "")}</span></div>
      <select class="selfield" data-mlic="${t.id}" aria-label="Licens" style="width:auto;max-width:210px">${Object.entries(kinds).map(([k, l]) => `<option value="${k}" ${((t.license || {}).kind || "own") === k ? "selected" : ""} title="${esc(l)}">${esc(LIC_SHORT[k])}</option>`).join("")}</select>
      ${P() ? `<button class="btn small" data-muse="${t.id}">${pm && pm.track_id === t.id ? "Används" : "Använd i projektet"}</button>` : ""}</div>`).join("");
  const sr = state.msearch;
  const results = sr && sr.results ? sr.results.map((r, k) => `<div class="mrow">
      <button class="btn icon small" data-mplay="${esc(r.url)}" aria-label="Spela">${playing(r.url) ? svgi(ICO.pause, 14) : icon("play", 13)}</button>
      <div class="stack" style="gap:2px;min-width:0;flex:1 1 220px"><b class="ell">${esc(r.title)}</b><span class="muted ell" style="font-size:12px">${esc(r.artist)}${r.duration ? ` · ${fmtDur(r.duration)}` : ""} · ${esc((r.license || {}).source || r.source || "")}</span></div>
      ${licBadge(r.license)}<button class="btn small primary" data-mget="${k}" ${r.got ? "disabled" : ""}>${r.got ? "Hämtad" : "Hämta"}</button></div>`).join("") : "";
  return `<main class="main wide" style="max-width:1100px">
    <div class="head"><h1>Musik</h1><p class="lead">AI:n väljer en låt som passar varje film (tempo, energi och längd) ur ditt bibliotek. Licensen följer med: namn på upphovspersonen läggs till när det krävs, och reklamfilmer använder bara musik som får användas kommersiellt.</p></div>
    <section class="box" style="flex-direction:row;flex-wrap:wrap;align-items:center;gap:14px">
      <label class="row" style="gap:10px;font-size:15px;flex:1 1 300px"><input type="checkbox" data-mauto ${m.auto ? "checked" : ""} style="width:20px;height:20px;accent-color:var(--accent)"><b>AI väljer musik automatiskt</b></label>
      ${P() ? `<span class="muted" style="font-size:13px">${esc(P().name)}: ${pm ? `${esc(pm.name)}${pm.auto === false ? " (vald av dig)" : ""}` : "AI väljer"}</span>
        ${pm ? '<button class="btn small" data-act="music-remove">Låt AI välja</button>' : ""}` : ""}
    </section>
    <section class="stack" style="gap:12px"><div class="spread"><h2>Ditt bibliotek <span class="muted" style="font-weight:400">· ${m.tracks.length} låtar</span></h2>
      <div class="row">${remote() ? "" : '<button class="btn small" data-act="music-adddir">+ Lägg till mapp</button>'}<button class="btn small" data-act="music-scan" ${busy ? "disabled" : ""}>${busy ? "Läser in …" : "Läs in igen"}</button></div></div>
      <div class="chips">${m.dirs.map((d, k) => `<span class="tag" title="${esc(d)}">${esc(d.split(/[\\\\/]/).filter(Boolean).pop() || d)}${remote() ? "" : ` <button class="linkbtn" data-mdirdel="${k}" aria-label="Ta bort mappen">✕</button>`}</span>`).join("") || '<span class="muted" style="font-size:13px">Inga mappar än. Lägg till mappen där du har din musik – även nedladdat från Epidemic, Artlist, Pixabay eller YouTube Audio Library.</span>'}</div>
      <div class="mlist">${tracks || `<div class="empty" style="padding:22px;display:flex;flex-direction:column;gap:12px;align-items:center">
        <b>Inga låtar i biblioteket än</b>
        <span class="muted" style="font-size:13px">Hämta ett gratis startpaket med lugn, mellan och energisk musik (CC0 och CC BY – får användas även i reklam), eller lägg till en egen mapp.</span>
        ${m.starter && m.starter.errors && m.starter.errors.length && !m.starter.done ? `<span style="color:var(--warn);font-size:13px">Förra försöket misslyckades: ${esc(m.starter.errors[0])}. Kontrollera internetanslutningen.</span>` : ""}
        <button class="btn primary" data-act="music-starter" ${busy ? "disabled" : ""}>${busy ? "Hämtar …" : "Hämta gratis musik"}</button></div>`}</div></section>
    <section class="stack" style="gap:12px"><h2>Hämta gratis musik</h2>
      <div class="searchbar"><span class="sico">${icon("search", 17)}</span><input class="field" id="mq" type="search" value="${esc(sr ? sr.q : "")}" placeholder="T.ex. calm ocean, ambient piano, upbeat travel, cinematic" aria-label="Sök musik">
        <select class="selfield" id="msrc" style="width:auto">${["commons", "openverse", ...(m.sources || [])].map((x) => `<option value="${esc(x)}" ${sr && sr.src === x ? "selected" : ""}>${x === "openverse" ? "Openverse (gratis)" : x === "commons" ? "Wikimedia Commons (gratis)" : esc(x)}</option>`).join("")}</select>
        <button class="btn" data-act="music-search">Sök</button></div>
      <label class="row" style="gap:10px;font-size:14px"><input type="checkbox" id="mcom" ${sr && sr.commercial ? "checked" : ""} style="width:18px;height:18px;accent-color:var(--accent)">Bara musik som får användas i reklam</label>
      ${sr && sr.loading ? '<span class="muted">Söker …</span>' : ""}
      ${sr && sr.results && !sr.results.length ? '<span class="muted">Inga träffar. Sök gärna på engelska.</span>' : ""}
      <div class="mlist">${results}</div>
      <p class="muted" style="margin:0;font-size:12px">Wikimedia Commons och Openverse (Jamendo, Freesound m.fl.) har musik med öppen licens. Sök gärna på engelska, t.ex. "Kevin MacLeod". Musik med CC BY kräver att upphovspersonen namnges – det gör programmet automatiskt i slutet av filmen och i en textfil vid export.</p></section>
    <section class="box"><h2 style="font-size:14px">Andra musiktjänster</h2><p style="margin:0">Har du Epidemic Sound, Artlist eller någon annan tjänst: ladda ner låtarna till en av mapparna ovan så används de som allt annat. Tjänster med eget API kan läggas till med en liten beskrivningsfil (adress och nyckel) i mappen <code>music_sources</code> i DeHazeIQ:s datamapp – se exempelfilen där.</p></section>
  </main>`;
}

async function musicPost(verb, body) {
  try { state.music = await api("POST", `/api/music/${verb}`, body || {}); render(); } catch (e) { fail(e); }
}

async function musicSearch() {
  const q = ($("#mq") || {}).value || "";
  if (!q.trim()) return;
  const src = ($("#msrc") || {}).value || "commons";
  const commercial = !!($("#mcom") || {}).checked;
  state.msearch = { q, src, commercial, loading: true };
  render();
  try {
    const r = await api("GET", `/api/music/search?q=${encodeURIComponent(q)}&source=${encodeURIComponent(src)}&commercial=${commercial ? 1 : 0}`);
    state.msearch = { q, src, commercial, results: r.results };
  } catch (e) { state.msearch = { q, src, commercial, results: [] }; fail(e); }
  render();
}

document.addEventListener("click", async (ev) => {
  const t = ev.target.closest("button");
  if (!t) return undefined;
  const d = t.dataset;
  if (d.mplay) return playMusic(d.mplay, t);
  if (d.mget !== undefined) {
    const r = state.msearch.results[Number(d.mget)];
    t.disabled = true; t.textContent = "Hämtar …";
    try { await api("POST", "/api/music/download", { item: r }); r.got = true; toast(`${r.title} är hämtad och läses in i biblioteket.`, true); loadQueue(); setTimeout(loadMusic, 4000); } catch (e) { fail(e); }
    return render();
  }
  if (d.muse) {
    try { const r = await api("POST", `/api/p/${state.pid}/music`, { track: d.muse }); P().music = r.music; toast(`Musik: ${r.music.name}`, true); } catch (e) { fail(e); }
    return render();
  }
  if (d.mdirdel !== undefined) { const dirs = state.music.dirs.filter((_, k) => k !== Number(d.mdirdel)); return musicPost("dirs", { dirs }); }
  switch (d.act) {
    case "music-view": state.view = "music"; loadMusic(); return render();
    case "music-scan": await musicPost("scan"); state.expectJob = true; loadQueue(); toast("Läser in musiken i bakgrunden.", true); setTimeout(loadMusic, 5000); return undefined;
    case "music-adddir": {
      const paths = await choosePaths("folder");
      if (!paths.length) return undefined;
      await musicPost("dirs", { dirs: [...state.music.dirs, ...paths] });
      await musicPost("scan"); loadQueue(); setTimeout(loadMusic, 5000);
      toast("Mappen läggs till och musiken läses in i bakgrunden.", true);
      return undefined;
    }
    case "music-search": return musicSearch();
    case "music-starter": await musicPost("starter"); state.expectJob = true; loadQueue(); toast("Hämtar gratis musik i bakgrunden – det tar någon minut.", true); setTimeout(loadMusic, 15000); setTimeout(loadMusic, 45000); return undefined;
    default: return undefined;
  }
});
document.addEventListener("change", (ev) => {
  const t = ev.target;
  if (t.dataset.mlic) return musicPost("license", { id: t.dataset.mlic, kind: t.value });
  if (t.dataset.mauto !== undefined) return musicPost("auto", { on: t.checked });
  return undefined;
});
document.addEventListener("keydown", (ev) => {
  if (ev.key === "Enter" && ev.target.id === "mq") { ev.preventDefault(); musicSearch(); }
});


/* ---------- tidslinjen: dra och släpp, tangentbord ---------- */
let tlDrag = null;
document.addEventListener("pointerdown", (ev) => {
  const b = ev.target.closest("[data-drag]");
  if (!b || state.view !== "edit") return;
  tlDrag = { i: Number(b.dataset.drag), x: ev.clientX, el: b, moved: false };
});
document.addEventListener("dragstart", (ev) => { if (ev.target.closest && ev.target.closest("[data-drag]")) ev.preventDefault(); });
document.addEventListener("pointercancel", () => { tlDrag = null; });
document.addEventListener("pointermove", (ev) => {
  if (!tlDrag) return;
  if (!tlDrag.moved && Math.abs(ev.clientX - tlDrag.x) < 10) return;
  tlDrag.moved = true;
  tlDrag.el.classList.add("dragging");
  const blocks = [...document.querySelectorAll("[data-drag]")];
  let to = blocks.length - 1;
  for (let k = 0; k < blocks.length; k++) {
    const r = blocks[k].getBoundingClientRect();
    if (ev.clientX < r.left + r.width / 2) { to = k; break; }
  }
  if (to > tlDrag.i) to -= 0; // släpp efter klippet till höger
  blocks.forEach((x, k) => x.classList.toggle("dropbefore", k === to && to !== tlDrag.i));
  tlDrag.to = to;
});
document.addEventListener("pointerup", async () => {
  const d = tlDrag;
  tlDrag = null;
  document.querySelectorAll(".dragging,.dropbefore").forEach((x) => x.classList.remove("dragging", "dropbefore"));
  if (!d || !d.moved || d.to === undefined) return;
  let to = d.to > d.i ? d.to - 1 : d.to;
  if (to === d.i) return;
  state.ed.suppressClick = true;
  await edit("move", { i: d.i, to });
  state.ed.i = to;
  render();
});
document.addEventListener("click", (ev) => {
  if (state.ed && state.ed.suppressClick && ev.target.closest("[data-drag]")) { ev.stopImmediatePropagation(); ev.preventDefault(); state.ed.suppressClick = false; }
}, true);
document.addEventListener("keydown", async (ev) => {
  if (state.view !== "edit" || !state.ed || ev.target.closest("input, textarea, select")) return;
  const p = edProp();
  if (!p) return;
  if (ev.key === "Delete" || ev.key === "Backspace") {
    ev.preventDefault();
    if (p.shots.length <= 1) return;
    // två tryck inom två sekunder – ett tangenttryck av misstag ska inte ta bort en scen
    const now = Date.now();
    if (!state.ed.delArm || state.ed.delArm.i !== state.ed.i || now - state.ed.delArm.t > 2000) {
      state.ed.delArm = { i: state.ed.i, t: now };
      toast(`Tryck ${ev.key === "Delete" ? "Delete" : "⌫"} igen för att ta bort scen ${state.ed.i + 1} (går att ångra).`);
      return;
    }
    state.ed.delArm = null;
    await edit("delete", { i: state.ed.i }); state.ed.i = Math.min(state.ed.i, edProp().shots.length - 1); render();
  }
  else if (ev.altKey && (ev.key === "ArrowLeft" || ev.key === "ArrowRight")) { ev.preventDefault(); const dir = ev.key === "ArrowLeft" ? -1 : 1; const j = state.ed.i + dir; if (j < 0 || j >= p.shots.length) return; await edit("move", { i: state.ed.i, dir }); state.ed.i = j; render(); }
  else if (ev.key === "ArrowLeft" || ev.key === "ArrowRight") { state.ed.i = Math.max(0, Math.min(p.shots.length - 1, state.ed.i + (ev.key === "ArrowLeft" ? -1 : 1))); state.ed.alts = null; render(); }
  else if ((ev.metaKey || ev.ctrlKey) && ev.key.toLowerCase() === "z") { ev.preventDefault(); await edit("undo"); render(); }
});

async function speechEdit(clipId, k, text, del = false) {
  await edit("speech_text", { clip_id: clipId, k, text, delete: del });
  try {  // klippens tal ligger i projektet: hämta om det
    const c = clips().find((x) => x.id === clipId);
    const segs = [...(((c || {}).speech || {}).segments || [])];
    if (del || !text.trim()) segs.splice(k, 1); else segs[k] = Object.assign({}, segs[k], { text: text.trim() });
    if (c) c.speech = Object.assign({}, c.speech, { segments: segs });
  } catch (e) { /* uppdateras vid nästa laddning */ }
  render();
}

/* Dra en text i textraden på tidslinjen: mitten flyttar, kanterna ändrar början/längd */
let ovDrag = null;
function ovFilmTotal(p) { return p.shots.reduce((a, s) => a + s.duration, 0) || 1; }
document.addEventListener("pointerdown", (ev) => {
  const b = ev.target.closest(".ovbar");
  if (!b || state.view !== "edit" || !b.dataset.ovsel || ev.button > 0) return;
  const row = b.parentElement.getBoundingClientRect();
  const h = ev.target.closest("[data-ovh]");
  ovDrag = { id: b.dataset.ovsel, x: ev.clientX, el: b, w: row.width, mode: h ? h.dataset.ovh : "move",
    left0: parseFloat(b.style.left), width0: parseFloat(b.style.width), moved: false };
  try { b.setPointerCapture(ev.pointerId); } catch (e) { /* äldre webbläsare */ }
  ev.preventDefault();
});
document.addEventListener("pointermove", (ev) => {
  if (!ovDrag) return;
  const dx = ev.clientX - ovDrag.x;
  if (!ovDrag.moved && Math.abs(dx) < 4) return;
  ovDrag.moved = true;
  const d = ovDrag, pct = (dx / d.w) * 100;
  d.el.classList.add("dragging");
  if (d.mode === "move") d.el.style.left = `${Math.max(0, Math.min(100 - d.width0, d.left0 + pct))}%`;
  else if (d.mode === "r") d.el.style.width = `${Math.max(1.5, Math.min(100 - d.left0, d.width0 + pct))}%`;
  else {
    const l = Math.max(0, Math.min(d.left0 + d.width0 - 1.5, d.left0 + pct));
    d.el.style.left = `${l}%`;
    d.el.style.width = `${d.width0 + (d.left0 - l)}%`;
  }
  const p = edProp(), tot = ovFilmTotal(p);
  d.el.dataset.tip = `${(parseFloat(d.el.style.left) / 100 * tot).toFixed(1)} s · ${(parseFloat(d.el.style.width) / 100 * tot).toFixed(1)} s`;
});
document.addEventListener("pointerup", async () => {
  const d = ovDrag;
  ovDrag = null;
  if (!d) return;
  if (!d.moved) return;
  const p = edProp();
  const tot = ovFilmTotal(p);
  const start = (parseFloat(d.el.style.left) / 100) * tot;
  const dur = Math.max(0.6, Math.round((parseFloat(d.el.style.width) / 100) * tot * 10) / 10);
  let i = p.shots.findIndex((s) => start >= s.at - 0.01 && start < s.at + s.duration);
  if (i < 0) i = p.shots.length - 1;
  const offset = Math.max(0, Math.round((start - p.shots[i].at) * 10) / 10);
  state.ed.ov = d.id;
  state.ed.i = i;
  window.__ovDragged = Date.now();
  const args = { id: d.id, i, offset };
  if (d.mode !== "move") args.dur = dur;
  await edit("overlay_update", args);
});
