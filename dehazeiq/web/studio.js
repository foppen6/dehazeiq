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
  none: "none", natural: "saturate(1.1) contrast(1.05)", underwater: "saturate(1.3) sepia(.12) brightness(1.05)",
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
    const n = state.queue.tasks.length;
    const b = document.querySelector("[data-qbadge]");
    if (b) { b.textContent = n; b.hidden = !n; }
    if (state.view === "queue") $("#view").innerHTML = viewQueue();
  } catch (_) { /* tyst */ }
}
setInterval(loadQueue, 2500);

function queueButton() {
  const n = (state.queue.tasks || []).length;
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
  return `<main class="main wide" style="max-width:1000px">
    <div class="spread"><div class="head"><h1>Jobbkö</h1><p class="lead">Ett jobb i taget i bakgrunden – du kan stänga fönstret eller jobba med annat. Ordningen går att ändra.</p></div>
      <div class="row"><button class="btn" data-act="qpause">${svgi(q.paused ? '<path d="M8 5v14l11-7z"/>' : ICO.pause, 16)}${q.paused ? "Fortsätt kön" : "Pausa kön"}</button>
      ${P() ? `<button class="btn primary" data-act="setup-project">Nya filmer av ${esc(P().name)}</button>` : ""}</div></div>
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
    const lens = [15, 30, 45, 60, 90, 180, 300].map((s) => `<option value="${s}" ${Number(len) === s ? "selected" : ""}>${s < 60 ? `${s} s` : `${s / 60} min`}</option>`).join("");
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
  if (!state.planTab || (state.planTab !== "all" && !plans.includes(state.planTab))) state.planTab = plans[0];
  const n = (k) => props.filter((p) => p.plan === k).length;
  return `<div class="chips" role="tablist" aria-label="Filmtyp">${plans.map((k) => `<button class="chip" role="tab" data-plantab="${k}" aria-pressed="${state.planTab === k}">${esc((filmTypes()[k] || {}).label || k)} <span class="muted">· ${n(k)}</span></button>`).join("")}
    <button class="chip" data-plantab="all" aria-pressed="${state.planTab === "all"}">Alla</button>
    <button class="chip" data-act="setup-project">+ Fler filmtyper</button></div>`;
}

function planProposals() {
  const props = (P() && P().proposals) || [];
  if (!props.some((p) => p.plan)) return null;
  const list = state.planTab === "all" ? props : props.filter((p) => p.plan === state.planTab);
  return list;
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
  state.ed = { prop: propId, i: 0, tab: "clip", scope: "film", alts: null, before: false, stamp: Date.now() };
  state.view = "edit";
  render();
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
    if (!quiet) render(); else refreshStill();
  } catch (e) { fail(e); }
}

function refreshStill() {
  const p = edProp();
  if (!p) return;
  const img = $("#edStill");
  if (img) img.src = stillUrl(p, state.ed.i, !state.ed.before);
  const tl = $("#edTimeline");
  if (tl) tl.outerHTML = edTimeline(p);
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
    const tags = [fx.speed > 1 ? "2×" : "", fx.speed && fx.speed < 1 ? "0,5×" : "", fx.freeze ? "Frys" : "", fx.zoom ? "Zoom" : "", fx.punch ? "Ryck" : "", fx.kenburns ? (fx.kenburns > 0 ? "Foto ↗" : "Foto ↙") : s.photo ? "Foto" : "", s.parent360 ? ({ planet: "Planet", ball: "Kula", whip: "360-svep", view: "360" }[(s.cam360 || {}).mode] || "360") : "", fx.roll ? "Roll" : "", s.grade ? "Färg" : "", s.manual_center ? "Flyttad" : ""].filter(Boolean);
    return `<button class="tlblock ${i === state.ed.i ? "sel" : ""}" data-edshot="${i}" data-drag="${i}" style="flex:${s.duration} 1 0;touch-action:pan-y" aria-label="Klipp ${i + 1}, ${dec(s.duration)} sekunder. Dra för att flytta.">
      <img alt="" loading="lazy" draggable="false" src="${frameUrl(s.clip_id, s.src_start + Math.min(s.duration, 1.5), 160)}"><span class="tlnum num">${i + 1}</span><span class="tldur num">${dec(s.duration)} s</span>${tags.length ? `<span class="tltags">${tags.join(" · ")}</span>` : ""}</button>`;
  }).join("");
  const title = (p.effects || {}).title;
  const trLabel = (state.info && state.info.transitions) || {};
  const textRow = p.shots.map((s, i) => `<span style="flex:${s.duration} 1 0;min-width:28px">${i === 0 && title ? `<span class="tltitle">${esc(title)}${s.text ? ` · ${esc(s.text.text)}` : ""}</span>` : s.text ? `<span class="tltitle" title="${esc(s.text.text)}">${esc(s.text.text)}</span>` : ""}</span>`).join("");
  const trRow = p.shots.map((s, i) => `<span style="flex:${s.duration} 1 0;min-width:28px;text-align:right;font-size:10px;color:${s.tr && s.tr !== "cut" ? "var(--accent)" : "var(--dim)"}">${i < p.shots.length - 1 ? esc(s.tr && s.tr !== "cut" ? trLabel[s.tr] || s.tr : "|") : ""}</span>`).join("");
  const n = p.shots.length, i = state.ed.i;
  return `<section class="tl" id="edTimeline" aria-label="Tidslinje">
    <div class="tltools">
      <span class="muted" style="font-size:12px">Klipp ${i + 1} av ${n} · dra i klippen för att ändra ordning</span><span class="grow"></span>
      <button class="btn small" data-edmove="-1" ${i <= 0 ? "disabled" : ""} title="Flytta åt vänster (Alt+←)">${svgi(ICO.left, 14)}Flytta</button>
      <button class="btn small" data-edmove="1" ${i >= n - 1 ? "disabled" : ""} title="Flytta åt höger (Alt+→)">Flytta${svgi(ICO.right, 14)}</button>
      <button class="btn small danger" data-act="ed-delete" ${n <= 1 ? "disabled" : ""} title="Ta bort klippet (Delete)">${icon("trash", 14)}Ta bort klipp</button>
      <button class="btn small" data-act="ed-undo" title="Ångra (Ctrl/Cmd+Z)">Ångra</button></div>
    <div class="tltrack"><span class="tllab">Text</span><div class="tlrow">${textRow}</div></div>
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
    <div class="stack" style="gap:8px"><span class="flabel">Text på klippet</span>
      <div class="row" style="flex-wrap:nowrap"><select class="selfield" id="edTxtKind" style="flex:0 0 130px">
        ${[["label", "Artnamn"], ["chapter", "Kapitel"], ["pop", "Pratbubbla"]].map(([k, l]) => `<option value="${k}" ${((s.text || {}).kind || "label") === k ? "selected" : ""}>${l}</option>`).join("")}</select>
        <input class="field" id="edTxt" value="${esc((s.text || {}).text || "")}" maxlength="60" placeholder="Ingen text" style="flex:1 1 auto;min-width:0"></div>
      <input class="field" id="edTxtSub" value="${esc((s.text || {}).sub || "")}" maxlength="60" placeholder="Andra raden, t.ex. latinskt namn">
      <div class="row"><button class="btn small" data-act="ed-text">Spara text</button>${s.text ? '<button class="btn small" data-act="ed-text-clear">Ta bort</button>' : ""}</div></div>
`;
}

function encSlider(g, k, label) {
  const auto = g[k] == null;
  return `<label class="sl"><span>${label}</span><input type="range" min="0" max="1" step="0.05" value="${auto ? 0.4 : g[k]}" data-edgrade="${k}" style="accent-color:var(--accent)${auto ? ";opacity:.5" : ""}"><span class="num" data-edgv="${k}">${auto ? "AI" : Math.round(g[k] * 100)}</span></label>`;
}

function edInspectorColor(p) {
  const g = curGrade(p);
  const looks = (state.info && state.info.looks) || {};
  const s = p.shots[state.ed.i] || {};
  const thumb = frameUrl(s.clip_id, s.src_start + Math.min(s.duration, 1.5), 160);
  const slider = (k, label, lo = -1) => `<label class="sl"><span>${label}</span><input type="range" min="${lo}" max="1" step="0.05" value="${g[k] || 0}" data-edgrade="${k}" style="accent-color:var(--accent)"><span class="num" data-edgv="${k}">${Math.round((g[k] || 0) * 100)}</span></label>`;
  return `<div class="stack" style="gap:8px"><span class="flabel">Gäller</span><div class="chips">
      ${chipBtn("data-edscope", "film", "Hela filmen", state.ed.scope === "film")}${chipBtn("data-edscope", "shot", `Klipp ${state.ed.i + 1}`, state.ed.scope === "shot")}</div>
      ${state.ed.scope === "shot" && s.grade ? `<button class="btn small" data-act="ed-grade-reset">Använd filmens färg för klippet</button>` : ""}</div>
    <div class="stack" style="gap:8px"><span class="flabel">Utseende</span><div class="lookgrid">
      ${Object.entries(looks).map(([k, l]) => `<button class="lookbtn" data-edlook="${k}" aria-pressed="${g.look === k}"><img alt="" src="${thumb}" style="filter:${LOOK_CSS[k] || "none"}"><span>${esc(l)}</span></button>`).join("")}</div>
      ${slider("strength", "Styrka", 0)}</div>
    <div class="stack" style="gap:6px"><div class="spread" style="align-items:center"><span class="flabel">Justera</span><button class="btn small" data-act="ed-grade-zero">Nollställ</button></div>
      ${slider("exposure", "Exponering")}${slider("contrast", "Kontrast")}${slider("saturation", "Mättnad")}${slider("temperature", "Temperatur")}${slider("tint", "Nyans")}${slider("sharpen", "Skärpa", 0)}${slider("vignette", "Vinjett", 0)}</div>
    <div class="stack" style="gap:6px"><div class="spread" style="align-items:center"><span class="flabel">Bildförbättring</span><button class="btn small" data-act="ed-enh-auto">Låt AI välja</button></div>
      ${encSlider(g, "dehaze", "Ta bort dis")}${encSlider(g, "particles", "Partiklar")}
      <label class="row" style="gap:10px;color:var(--text-2);font-size:13px"><input type="checkbox" data-edstab ${g.stabilize ? "checked" : ""} style="width:18px;height:18px;accent-color:var(--accent)">Stabilisera skakig bild${g.stabilize == null ? ' <span class="muted">(AI: automatiskt)</span>' : ""}</label></div>
    <p class="muted" style="margin:0;font-size:12px">AI:ns vitbalans för undervatten ligger kvar under din färgsättning. Håll in "Före" för att jämföra. Bildförbättring syns i förhandsvisningen av filmen.</p>`;
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
  if (isPromo(p)) return sel + promoForm(p);
  const lyr = p.style === "mv_lyrics" ? lyricsForm(p) : "";
  return `${sel}${lyr}<label class="stack" style="gap:6px"><span class="flabel">Titel i början av filmen</span>
      <input class="field" id="edTitle" value="${esc(title)}" maxlength="80" placeholder="Ingen titel"></label>
    <div class="row"><button class="btn small primary" data-act="ed-title">Spara titel</button><button class="btn small" data-act="ed-title-clear">Ta bort titel</button></div>
    <p class="muted" style="margin:0;font-size:12px">Titeln tonas in över första klippet. Slå av eller på den under Effekter i förslagsvyn.</p>`;
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
    <div class="spread"><div class="head"><h1>${esc(p.title || p.style_label)}</h1>
      <p class="lead">${esc(p.style_label)} · ${p.platform ? `${esc(platformLabel(p.platform))} · ` : ""}${p.format} · ${fmtDur(p.length)}</p></div>
      <div class="row">${platformSelect(p)}<button class="btn" data-act="ed-undo" ${(p.history || []).length ? "" : "disabled"}>${svgi(ICO.undo, 16)}Ångra</button>
        ${prev ? "" : `<button class="btn" data-preview="${p.id}" ${busyHere ? "disabled" : ""}>${icon("play", 14)}${busyHere ? "Renderar …" : "Förhandsvisa filmen"}</button>`}
        <button class="btn primary" data-export="${p.id}">Exportera</button></div></div>
    <div class="edgrid">
      <section class="edstage">
        <div class="edviews">
          <figure class="edfig"><figcaption>I filmen</figcaption>
            <div class="edstill" style="aspect-ratio:${p.format.replace(":", "/")}">
              <img id="edStill" alt="Klippet som det ser ut i filmen" src="${stillUrl(p, i, !state.ed.before)}">
              <button class="beforebtn" data-act="ed-before" aria-pressed="${state.ed.before}">Före</button></div></figure>
          ${tab === "clip" ? `<figure class="edfig"><figcaption>Originalbild – klicka för att flytta utsnittet</figcaption>
            <div class="edsrc" data-edsrc><img alt="Originalbilden" src="${src}"><span class="edring" style="left:${cx * 100}%;top:${cy * 100}%"></span></div></figure>` : ""}
        </div>
        ${prev && !busyHere ? `<video class="edvideo" controls playsinline preload="metadata" src="${mediaUrl("renders", prev)}"></video>`
          : busyHere ? `<div class="progress"><div class="spread" style="font-size:13px"><span class="muted" data-live-text>${esc(job().message || "")}</span><span class="num muted" data-live-pct></span></div><div class="bar"><div data-live-fill style="width:0%"></div></div></div>` : ""}
      </section>
      <aside class="edinsp"><div class="seg" role="tablist" style="grid-template-columns:repeat(3,minmax(0,1fr))">${tabs}</div>${inspector}</aside>
    </div>
    ${edTimeline(p)}
  </main>`;
}

let gradeTimer = null;
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
  const t = ev.target.closest("button, [data-edsrc]");
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
  if (d.edshot !== undefined) { state.ed.i = Number(d.edshot); state.ed.alts = null; return render(); }
  if (d.edtab) { state.ed.tab = d.edtab; return render(); }
  if (d.edtrim) { const s = edProp().shots[state.ed.i]; return edit("trim", { i: state.ed.i, duration: s.duration + Number(d.edtrim) }); }
  if (d.edspeed) return edit("speed", { i: state.ed.i, mode: d.edspeed });
  if (d.edfx) return edit("fx", { i: state.ed.i, effect: d.edfx });
  if (d.cammode) return edit("cam360", { i: state.ed.i, mode: d.cammode, ...(d.cammode === "ai" ? { yaw: 0, fov: 104 } : {}) });
  if (d.edmove) { const j = state.ed.i + Number(d.edmove); await edit("move", { i: state.ed.i, dir: Number(d.edmove) }); state.ed.i = Math.max(0, Math.min(j, edProp().shots.length - 1)); return render(); }
  if (d.edscope) { state.ed.scope = d.edscope; return render(); }
  if (d.edlook) { const g = curGrade(edProp()); g.look = d.edlook; stageGrade(g); return render(); }
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
    case "ed-before": return undefined;  // hålls in, se pointerdown/pointerup
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
  if (t.dataset.edlen !== undefined) { const v = document.querySelector("[data-edlenval]"); if (v) v.textContent = `${dec(Number(t.value))} s`; }
  if (t.dataset.cam) { const v = document.querySelector(`[data-camval="${t.dataset.cam}"]`); if (v) v.textContent = `${t.value}°`; }
  return undefined;
});

document.addEventListener("change", (ev) => {
  const t = ev.target;
  const d = t.dataset;
  if (d.edlen !== undefined) return edit("trim", { i: state.ed.i, duration: Number(t.value) });
  if (d.edtr !== undefined) return edit("transition", { i: state.ed.i, type: t.value });
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

/* "Före": håll in för att jämföra */
document.addEventListener("pointerdown", (ev) => {
  if (ev.target.closest(".beforebtn")) { state.ed.before = true; refreshStill(); }
});
document.addEventListener("pointerup", () => {
  if (state.ed.before && state.view === "edit") { state.ed.before = false; refreshStill(); }
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
        <select class="selfield" id="msrc" style="width:auto">${["openverse", ...(m.sources || [])].map((x) => `<option value="${esc(x)}" ${sr && sr.src === x ? "selected" : ""}>${x === "openverse" ? "Openverse (gratis)" : esc(x)}</option>`).join("")}</select>
        <button class="btn" data-act="music-search">Sök</button></div>
      <label class="row" style="gap:10px;font-size:14px"><input type="checkbox" id="mcom" ${sr && sr.commercial ? "checked" : ""} style="width:18px;height:18px;accent-color:var(--accent)">Bara musik som får användas i reklam</label>
      ${sr && sr.loading ? '<span class="muted">Söker …</span>' : ""}
      ${sr && sr.results && !sr.results.length ? '<span class="muted">Inga träffar. Sök gärna på engelska.</span>' : ""}
      <div class="mlist">${results}</div>
      <p class="muted" style="margin:0;font-size:12px">Openverse samlar musik med öppen licens från bland annat Jamendo, Freesound och Wikimedia Commons. Musik med CC BY kräver att upphovspersonen namnges – det gör programmet automatiskt i slutet av filmen och i en textfil vid export.</p></section>
    <section class="box"><h2 style="font-size:14px">Andra musiktjänster</h2><p style="margin:0">Har du Epidemic Sound, Artlist eller någon annan tjänst: ladda ner låtarna till en av mapparna ovan så används de som allt annat. Tjänster med eget API kan läggas till med en liten beskrivningsfil (adress och nyckel) i mappen <code>music_sources</code> i DeHazeIQ:s datamapp – se exempelfilen där.</p></section>
  </main>`;
}

async function musicPost(verb, body) {
  try { state.music = await api("POST", `/api/music/${verb}`, body || {}); render(); } catch (e) { fail(e); }
}

async function musicSearch() {
  const q = ($("#mq") || {}).value || "";
  if (!q.trim()) return;
  const src = ($("#msrc") || {}).value || "openverse";
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
  if (ev.key === "Delete" || ev.key === "Backspace") { ev.preventDefault(); if (p.shots.length > 1) await edit("delete", { i: state.ed.i }); state.ed.i = Math.min(state.ed.i, edProp().shots.length - 1); render(); }
  else if (ev.altKey && (ev.key === "ArrowLeft" || ev.key === "ArrowRight")) { ev.preventDefault(); const dir = ev.key === "ArrowLeft" ? -1 : 1; const j = state.ed.i + dir; if (j < 0 || j >= p.shots.length) return; await edit("move", { i: state.ed.i, dir }); state.ed.i = j; render(); }
  else if (ev.key === "ArrowLeft" || ev.key === "ArrowRight") { state.ed.i = Math.max(0, Math.min(p.shots.length - 1, state.ed.i + (ev.key === "ArrowLeft" ? -1 : 1))); state.ed.alts = null; render(); }
  else if ((ev.metaKey || ev.ctrlKey) && ev.key.toLowerCase() === "z") { ev.preventDefault(); await edit("undo"); render(); }
});
