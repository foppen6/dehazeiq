/* DeHazeIQ – gränssnitt (vanilla JS, inga beroenden) */
"use strict";

const STYLE_INFO = {
  auto: { label: "Låt AI föreslå", desc: "Tre olika stilar utifrån materialet", sw: "#1B3E48" },
  cinematic: { label: "Cinematisk", desc: "Långa tagningar, mjuk färg", sw: "#2A2418", color: "#E3B76A",
    long: "Lugna tagningar, toningar i början och slutet och varm färgprofil." },
  action: { label: "Action", desc: "Högt tempo, klipp i takt", sw: "#3A1E1A", color: "#EE8A6B",
    long: "Korta klipp som följer musikens takt, med fokus på rörelse och energi." },
  calm: { label: "Lugn natur", desc: "Långsamt, berättande", sw: "#16302A", color: "#6FD3A5",
    long: "Få och långa klipp med naturliga färger. Originalljudet hörs svagt under musiken." },
};
const FORMAT_INFO = [
  { id: "9:16", name: "Reel / Shorts", sub: "9:16 · Instagram, TikTok", shape: [18, 30] },
  { id: "16:9", name: "YouTube", sub: "16:9 · liggande", shape: [34, 20] },
  { id: "1:1", name: "Kvadrat", sub: "1:1 · flöde", shape: [24, 24] },
  { id: "4:5", name: "Stående flöde", sub: "4:5 · Instagram", shape: [22, 27] },
];
const LENGTHS = [15, 30, 60, 180];
const SRC_COLOR = { Insta360: "var(--insta)", Nikon: "var(--nikon)", Mobil: "var(--mobile)", GoPro: "#6FB6F2" };

const state = {
  info: null, projects: [], pid: null, project: null, view: "import",
  filter: "all", exportProp: null, exportRes: "1080p", shown: [], themes: [], theme: null,
  lastJob: null, poll: null, autoAnalyze: false, expectJob: false,
};

/* ---------- hjälpare ---------- */
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtDur = (s) => { s = Math.max(0, Math.round(s || 0)); const m = Math.floor(s / 60); return `${m}:${String(s % 60).padStart(2, "0")}`; };
const fmtLong = (s) => { s = Math.round(s || 0); return s >= 60 ? `${Math.floor(s / 60)} min ${s % 60} s` : `${s} s`; };
const dec = (v, d = 1) => Number(v || 0).toFixed(d).replace(".", ",");
const frameUrl = (cid, t, w = 320) => `/api/p/${state.pid}/frame?clip=${encodeURIComponent(cid)}&t=${(t || 0).toFixed(1)}&w=${w}`;
const remote = () => !!(state.info && state.info.remote);
const revealLabel = () => {
  const pf = (state.info && state.info.platform) || "";
  return pf === "darwin" ? "Visa i Finder" : pf.startsWith("win") ? "Visa i Utforskaren" : "Visa i mappen";
};
const mediaUrl = (sub, file) => `/media/${state.pid}/${sub}/${encodeURIComponent(file)}`;

async function api(method, path, body) {
  const opt = { method, headers: { "X-DeHazeIQ": "1" } };
  if (body !== undefined) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
  const r = await fetch(path, opt);
  let data = null;
  try { data = await r.json(); } catch (_) { /* tomt svar */ }
  if (!r.ok) throw new Error((data && data.error) || `Fel ${r.status}`);
  return data;
}

let toastTimer = null;
function toast(msg, ok = false) {
  const t = $("#toast");
  t.textContent = msg; t.className = ok ? "toast ok" : "toast"; t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, ok ? 3500 : 7000);
}
const fail = (e) => toast(e.message || String(e));

function icon(name, size = 18) {
  const p = {
    upload: '<path d="M12 16V4"/><path d="m7 9 5-5 5 5"/><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/>',
    spark: '<path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1"/>',
    music: '<path d="M9 18V5l11-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="16" r="3"/>',
    redo: '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/>',
    star: '<path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"/>',
    eyeoff: '<path d="M3 3l18 18"/><path d="M10.6 6.1A10 10 0 0 1 12 6c5 0 9 6 9 6a17 17 0 0 1-3.1 3.6M6.5 7.5C4.2 9 3 12 3 12s4 6 9 6c1.5 0 2.9-.4 4.1-1"/>',
    play: '<path d="M8 5v14l11-7z" fill="currentColor" stroke="none"/>',
    folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    film: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4"/>',
    phone: '<rect x="6" y="2" width="12" height="20" rx="2.5"/><path d="M11 18h2"/>',
    pen: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="m13.5 6.5 4 4"/>',
    trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
    wifi: '<path d="M2 8.8a15 15 0 0 1 20 0M5 12.6a10 10 0 0 1 14 0M8.5 16.3a5 5 0 0 1 7 0"/><circle cx="12" cy="19.5" r=".8" fill="currentColor"/>',
  }[name] || "";
  return `<svg aria-hidden="true" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`;
}

/* ---------- data ---------- */
async function loadProjects() { state.projects = await api("GET", "/api/projects"); }

async function loadProject(pid) {
  state.pid = pid;
  localStorage.setItem("tv.pid", pid);
  state.project = await api("GET", `/api/p/${pid}`);
  const saved = JSON.parse(localStorage.getItem(`tv.shown.${pid}`) || "null");
  const ids = new Set((state.project.proposals || []).map((p) => p.id));
  state.shown = (saved || []).filter((id) => ids.has(id));
  if (!state.shown.length) state.shown = (state.project.proposals || []).slice(0, 3).map((p) => p.id);
  state.themes = [];
  state.theme = null;
  handleJob(state.project.job, true);
  loadThemes();
}

async function loadThemes() {
  if (!state.pid || running()) return;
  try {
    state.themes = await api("GET", `/api/p/${state.pid}/themes`);
    if (state.view === "proposals") render();
  } catch (_) { state.themes = []; }
}

function saveShown() { localStorage.setItem(`tv.shown.${state.pid}`, JSON.stringify(state.shown)); }
const P = () => state.project;
const clips = () => (P() ? P().clips : []);
const usable = () => clips().filter((c) => !c.is360);
const analyzed = () => clips().filter((c) => c.analysis);
const isUsed = (c) => !!c.analysis && !c.is360 && !c.excluded && (c.favorite || !c.auto_excluded);
const settings = () => (P() && P().settings) || { format: "9:16", length: 30, style: "auto" };
const propById = (id) => (P().proposals || []).find((p) => p.id === id);
const job = () => (P() && P().job) || { state: "idle" };
const running = (kindPrefix) => job().state === "running" && (!kindPrefix || (job().kind || "").startsWith(kindPrefix));

/* ---------- jobb ---------- */
function handleJob(j, initial = false) {
  if (!P()) return;
  P().job = j;
  const bar = $("#jobbar");
  if (j.state === "running") {
    bar.hidden = false;
    const titles = { import: "Importerar", analyze: "Analyserar material", auto: "Skapar filmer automatiskt" };
    const kind = (j.kind || "").split(":");
    $("#jobTitle").textContent = titles[kind[0]] || (kind[1] === "preview" ? "Skapar förhandsvisning" : `Exporterar ${kind[1] || ""}`);
    $("#jobPct").textContent = `${Math.round((j.progress || 0) * 100)} %`;
    $("#jobFill").style.width = `${(j.progress || 0) * 100}%`;
    $("#jobMsg").textContent = j.message || "";
    if (!state.poll) state.poll = setInterval(pollJob, 800);
  } else {
    bar.hidden = true;
    if (state.poll) { clearInterval(state.poll); state.poll = null; }
    if (!initial && ((state.lastJob && state.lastJob === j.id) || state.expectJob)) {
      state.expectJob = false;
      state.lastJob = null;
      onJobFinished(j);
    }
  }
  if (j.state === "running") state.lastJob = j.id;
}

async function pollJob() {
  try {
    const j = await api("GET", `/api/p/${state.pid}/status`);
    const wasRunning = running();
    handleJob(j);
    if (j.state === "running") {
      updateLiveBits(j);
      if (!wasRunning) render();
    }
  } catch (e) { /* tyst – försöker igen */ }
}

async function onJobFinished(j) {
  const kind = (j.kind || "").split(":");
  await loadProject(state.pid);
  await loadProjects();
  if (j.state === "error") {
    toast(j.message || "Något gick fel");
    if (kind[0] === "auto" && analyzed().length) state.view = "analyze";
    render();
    return;
  }
  if (kind[0] === "auto") {
    const r = j.result || {};
    const ex = (r.analysis || {}).excluded || 0;
    if (r.proposals && r.proposals.length) { state.shown = r.proposals.slice(0, 3); saveShown(); }
    loadThemes();
    toast(`Klart! ${r.proposals ? r.proposals.length : 0} filmförslag är klara.${ex ? ` ${ex} svaga klipp valdes bort automatiskt.` : ""}`, true);
    state.view = "proposals";
  } else if (kind[0] === "import") {
    const r = j.result || {};
    let msg = `${r.added || 0} klipp importerade`;
    if (r.skipped) msg += `, ${r.skipped} fanns redan`;
    if (r.failed && r.failed.length) msg += `\nKunde inte läsa: ${r.failed.slice(0, 4).join(", ")}`;
    toast(msg, true);
    if (state.autoAnalyze && usable().some((c) => !c.analysis && c.status === "proxy")) {
      state.autoAnalyze = false;
      return startAnalyze();
    }
  } else if (kind[0] === "analyze") {
    toast(`Analys klar: ${(j.result || {}).analyzed || 0} klipp`, true);
  } else if (kind[0] === "render" && kind[1] !== "preview") {
    toast(`Exporten är klar: ${(j.result || {}).file || ""}`, true);
  }
  render();
}

function updateLiveBits(j) {
  const fill = document.querySelector("[data-live-fill]");
  if (fill) fill.style.width = `${(j.progress || 0) * 100}%`;
  const txt = document.querySelector("[data-live-text]");
  if (txt) txt.textContent = j.message || "";
  const pct = document.querySelector("[data-live-pct]");
  if (pct) pct.textContent = `${Math.round((j.progress || 0) * 100)} %`;
}

/* ---------- åtgärder ---------- */
async function createProject(name) {
  const p = await api("POST", "/api/projects", { name });
  await loadProjects();
  await loadProject(p.id);
  state.view = "import";
  render();
}

async function choosePaths(kind) {
  try {
    const r = await api("POST", "/api/choose", { kind });
    return r.paths || [];
  } catch (e) {
    toast(`${e.message}\nKlistra in sökvägen i fältet i stället.`);
    return [];
  }
}

// Ny import = nytt projekt (namnges efter mappen) + hela flödet automatiskt
async function newImport(paths) {
  if (!paths || !paths.length) return;
  try {
    const p = await api("POST", "/api/import", { paths });
    state.expectJob = true;
    await loadProjects();
    await loadProject(p.id);
    state.view = "proposals";
    await pollJob();
    render();
  } catch (e) { fail(e); }
}

// Lägg till klipp i det öppna projektet (gör sedan om analys och förslag automatiskt)
async function addToProject(paths) {
  if (!paths || !paths.length) return;
  try {
    await api("POST", `/api/p/${state.pid}/import`, { paths });
    state.expectJob = true;
    state.view = "proposals";
    await pollJob();
    render();
  } catch (e) { fail(e); }
}

async function runAuto() {
  try {
    await api("POST", `/api/p/${state.pid}/auto`);
    state.expectJob = true;
    state.view = "proposals";
    await pollJob();
    render();
  } catch (e) { fail(e); }
}

/* ---------- byt namn / ta bort ---------- */
function openRename(pid) {
  const pr = state.projects.find((x) => x.id === pid);
  if (!pr) return;
  const m = $("#modal");
  m.innerHTML = `<form class="modal-card" id="renameForm" data-pid="${esc(pid)}" role="dialog" aria-modal="true" aria-labelledby="rnTitle">
    <h2 id="rnTitle" style="font-size:18px">Byt namn på projekt</h2>
    <label class="sr" for="rnName">Nytt namn</label><input class="field" id="rnName" value="${esc(pr.name)}" maxlength="80">
    <div class="row"><button class="btn" type="button" data-act="modal-close">Avbryt</button><button class="btn primary" type="submit">Spara</button></div></form>`;
  m.hidden = false;
  const inp = $("#rnName");
  inp.focus(); inp.select();
}

function openDelete(pid) {
  const pr = state.projects.find((x) => x.id === pid);
  if (!pr) return;
  const m = $("#modal");
  m.innerHTML = `<div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="delTitle">
    <h2 id="delTitle" style="font-size:18px">Ta bort "${esc(pr.name)}"?</h2>
    <p class="lead">Analys, förslag, förhandsvisningar och exporter i projektet tas bort. Dina originalfilmer rörs inte.</p>
    <div class="row"><button class="btn" data-act="modal-close">Avbryt</button><button class="btn danger" data-del-confirm="${esc(pid)}">Ta bort</button></div></div>`;
  m.hidden = false;
}

async function deleteProject(pid) {
  try {
    await api("POST", `/api/p/${pid}/delete`);
    $("#modal").hidden = true;
    localStorage.removeItem(`tv.shown.${pid}`);
    await loadProjects();
    if (state.pid === pid) {
      state.pid = null; state.project = null;
      if (state.projects[0]) await loadProject(state.projects[0].id);
      state.view = "proposals";
    }
    toast("Projektet är borttaget", true);
    render();
  } catch (e) { fail(e); }
}

async function startAnalyze(redo = false) {
  try {
    await api("POST", `/api/p/${state.pid}/analyze`, { redo });
    state.expectJob = true;
    state.view = "analyze";
    await pollJob();
    render();
  } catch (e) { fail(e); }
}

async function saveSettings(patch) {
  P().settings = Object.assign({}, settings(), patch);
  render();
  try { await api("POST", `/api/p/${state.pid}/settings`, patch); } catch (e) { fail(e); }
}

async function chooseMusic() {
  let path = null;
  try {
    const r = await api("POST", "/api/choose", { kind: "music" });
    path = r.paths && r.paths[0];
  } catch (_) {
    path = window.prompt("Sökväg till musikfil (MP3, M4A, WAV …)");
  }
  if (!path) return;
  try {
    const r = await api("POST", `/api/p/${state.pid}/music`, { path });
    P().music = r.music;
    toast(`Musik: ${r.music.name} · ${dec(r.music.bpm, 0)} BPM`, true);
    render();
  } catch (e) { fail(e); }
}

async function removeMusic() {
  await api("POST", `/api/p/${state.pid}/music`, { path: null });
  P().music = null;
  render();
}

async function toggleClip(cid, field) {
  const c = clips().find((x) => x.id === cid);
  if (!c) return;
  try {
    const r = await api("POST", `/api/p/${state.pid}/clip/${cid}`, { [field]: !c[field] });
    Object.assign(c, r);
    render();
  } catch (e) { fail(e); }
}

let generating = false;
async function generate() {
  if (generating) return;
  generating = true; render();
  try {
    const s = settings();
    const r = await api("POST", `/api/p/${state.pid}/generate`, { style: s.style, format: s.format, length: s.length, theme: state.theme });
    P().proposals = r.proposals.concat(P().proposals || []);
    state.shown = r.proposals.map((p) => p.id);
    saveShown();
    state.view = "proposals";
  } catch (e) { fail(e); }
  generating = false;
  render();
}

async function regenerate(id) {
  try {
    const r = await api("POST", `/api/p/${state.pid}/proposal/${id}/regenerate`);
    P().proposals.unshift(r.proposal);
    state.shown = state.shown.map((x) => (x === id ? r.proposal.id : x));
    saveShown();
    render();
  } catch (e) { fail(e); }
}

async function renderProp(id, resolution) {
  try {
    await api("POST", `/api/p/${state.pid}/proposal/${id}/render`, { resolution });
    state.expectJob = true;
    await pollJob();
    render();
  } catch (e) { fail(e); }
}

async function reveal(propId, file) {
  try { await api("POST", `/api/p/${state.pid}/proposal/${propId}/reveal`, { file }); } catch (e) { fail(e); }
}

/* ---------- topp ---------- */
function stepsModel() {
  const hasClips = clips().length > 0;
  const nAnalyzed = analyzed().length;
  const hasProps = (P() && (P().proposals || []).length) > 0;
  return [
    { id: "import", n: 1, label: "Importera", done: hasClips, enabled: true },
    { id: "analyze", n: 2, label: "Analys", done: hasClips && nAnalyzed >= usable().length && nAnalyzed > 0, enabled: hasClips },
    { id: "proposals", n: 3, label: "Förslag", done: hasProps, enabled: nAnalyzed > 0 || hasProps },
    { id: "review", n: 4, label: "Granska", soon: true },
    { id: "export", n: 5, label: "Exportera", done: false, enabled: hasProps },
  ];
}

function renderTop() {
  $("#crumb").textContent = P() ? `/ ${P().name}` : "";
  const ver = $("#ver");
  if (ver && state.info) ver.textContent = `v${state.info.version}`;
  $("#steps").innerHTML = stepsModel().map((s) => {
    const active = state.view === s.id;
    const cls = ["step", active ? "active" : "", !active && s.done ? "done" : ""].join(" ");
    const dot = !active && s.done ? "✓" : s.n;
    const dis = s.soon || !s.enabled ? "disabled" : "";
    const soon = s.soon ? '<span class="soon">v2</span>' : "";
    return `<button class="${cls}" data-step="${s.id}" ${dis} ${active ? 'aria-current="step"' : ""}><span class="dot">${dot}</span>${s.label}${soon}</button>`;
  }).join("");
  const info = state.info || {};
  const chip = `<span class="chip-status" title="Videokodning och motivigenkänning"><i style="background:${info.hw_encoder ? "var(--good)" : "var(--warn)"}"></i>${esc(info.encoder || "")} · ${info.clip_ai ? "AI på" : "AI saknas"}</span>`;
  $("#topActions").innerHTML = remote()
    ? `<span class="chip-status"><i></i>Ansluten via wifi</span>`
    : `${chip}<button class="btn small" data-act="lan" title="Styr DeHazeIQ från mobil eller surfplatta">${icon("phone", 15)}Mobil</button>`;
}

/* ---------- vy: importera ---------- */
function statusCell(c) {
  if (c.is360) return `<span class="st-work" title="${esc(c.note || "")}">360 – exportera platt</span>`;
  if (c.status === "error") return `<span class="st-bad" title="${esc(c.error || "")}">Fel</span>`;
  if (c.status === "analyzed") return '<span class="st-ok">Analyserad</span>';
  if (c.status === "proxy") return '<span class="st-ok">Proxy klar</span>';
  return '<span class="st-wait">Väntar</span>';
}

function viewImport() {
  const cs = clips();
  const total = cs.reduce((a, c) => a + (c.duration || 0), 0);
  const proxies = cs.filter((c) => ["proxy", "analyzed"].includes(c.status)).length;
  const s = settings();
  const unAnalyzed = usable().filter((c) => !c.analysis && c.status === "proxy").length;
  const busy = running();

  const side = `<aside class="side" aria-label="Projekt">
    <div class="eyebrow" style="padding:0 8px 8px">Projekt</div>
    ${state.projects.map((p) => `<div class="proj-row ${p.id === state.pid ? "active" : ""}">
        <button class="proj" data-proj="${esc(p.id)}"><span>${esc(p.name)}</span><small>${p.clips} klipp · ${fmtLong(p.duration)}</small></button>
        <button class="icon-btn" data-rename="${esc(p.id)}" aria-label="Byt namn på ${esc(p.name)}" title="Byt namn">${icon("pen", 15)}</button>
        ${remote() ? "" : `<button class="icon-btn" data-delete="${esc(p.id)}" aria-label="Ta bort ${esc(p.name)}" title="Ta bort">${icon("trash", 15)}</button>`}
      </div>`).join("") || '<p class="muted" style="padding:0 8px">Inga projekt ännu.</p>'}
    ${remote() ? "" : `<button class="btn primary" style="margin-top:8px" data-act="new-import" ${running() ? "disabled" : ""}>${icon("folder", 16)}Ny import</button>`}
  </aside>`;

  const rows = cs.map((c) => {
    const thumbOk = ["proxy", "analyzed"].includes(c.status);
    const img = thumbOk ? `<img class="thumb" loading="lazy" alt="" src="${frameUrl(c.id, (c.duration || 0) * 0.3, 160)}">` : '<span class="thumb"></span>';
    const fmt = `${c.width}×${c.height} · ${(c.codec || "").toUpperCase()}${c.bit_depth === 10 ? " 10-bit" : ""}`;
    return `<div class="tr">${img}<span class="num" style="font-weight:500;overflow:hidden;text-overflow:ellipsis">${esc(c.name)}</span>
      <span class="src"><i style="background:${SRC_COLOR[c.source] || "var(--dim)"}"></i>${esc(c.source)}</span>
      <span class="num" style="color:var(--text-2)">${fmtDur(c.duration)}</span><span class="muted">${esc(fmt)}</span>${statusCell(c)}</div>`;
  }).join("");

  const drop = remote()
    ? `<div class="box"><h2>Importera från datorn</h2><p>Nya klipp läggs till på datorn. Här kan du välja format, längd, stil, markera favoriter, skapa förslag och exportera.</p></div>`
    : null;
  const main = `<main class="main">
    <div class="head"><h1>Material och inställningar</h1><p class="lead">Nya klipp analyseras och filmförslagen görs om automatiskt.</p></div>
    ${drop || `<div class="drop">
      <div class="ico">${icon("upload", 26)}</div>
      <div class="drop-title">Lägg till fler klipp i projektet</div>
      <div class="muted" style="font-size:13px">MP4 · MOV · H.264 · H.265/HEVC 10-bit · Insta360 (platta exporter) · Nikon · mobil</div>
      <div class="row" style="justify-content:center">
        <button class="btn primary" data-act="add-folder" ${busy ? "disabled" : ""}>${icon("folder", 16)}Välj mapp</button>
        <button class="btn" data-act="add-files" ${busy ? "disabled" : ""}>Välj filer</button>
      </div>
      <form class="pathrow" id="pathForm"><label class="sr" for="pathInput">Sökväg till mapp eller fil</label>
        <input class="field" id="pathInput" placeholder="… eller klistra in en sökväg, t.ex. ~/Movies/Röda havet">
        <button class="btn" type="submit" ${busy ? "disabled" : ""}>Importera</button></form>
    </div>`}
    <section class="stack" aria-label="Importerade klipp">
      <div class="spread" style="align-items:baseline"><h2>${cs.length} klipp · ${fmtLong(total)}</h2><span class="muted" style="font-size:13px">Proxyfiler: ${proxies} av ${usable().length} klara</span></div>
      <div class="table-wrap"><div class="table">
        <div class="tr th"><span></span><span>Fil</span><span>Källa</span><span>Längd</span><span>Format</span><span>Status</span></div>
        ${rows || '<div class="empty">Inga klipp ännu. Välj en mapp ovan.</div>'}
      </div></div>
    </section>
  </main>`;

  const fmtCards = FORMAT_INFO.map((f) => `<button class="card-btn" data-format="${f.id}" aria-pressed="${s.format === f.id}">
      <span class="shape" style="width:${f.shape[0]}px;height:${f.shape[1]}px"></span><b>${f.name}</b><small>${f.sub}</small></button>`).join("");
  const lens = LENGTHS.map((l) => `<button data-length="${l}" aria-pressed="${Number(s.length) === l}">${l < 60 ? `${l} s` : `${l / 60} min`}</button>`).join("");
  const styles = Object.entries(STYLE_INFO).map(([k, v]) => `<button class="style-btn" data-style="${k}" aria-pressed="${s.style === k}">
      <span class="sw" style="background:${v.sw}">${k === "auto" ? icon("spark") : ""}</span><span class="t"><b>${v.label}</b><small>${v.desc}</small></span></button>`).join("");
  const m = P() && P().music;
  const musicBox = remote()
    ? `<div class="music"><span class="sw">${icon("music")}</span><span class="t"><b>${m ? esc(m.name) : "Ingen musik vald"}</b><small>${m ? `${dec(m.bpm, 0)} BPM · ${fmtDur(m.duration)}` : "Välj musik på datorn"}</small></span></div>`
    : m
    ? `<div class="music"><span class="sw">${icon("music")}</span><span class="t"><b>${esc(m.name)}</b><small>${dec(m.bpm, 0)} BPM · ${fmtDur(m.duration)}</small></span>
        <button class="btn small" data-act="music">Byt</button><button class="btn small" data-act="music-remove" aria-label="Ta bort musik">✕</button></div>`
    : `<button class="music" data-act="music" style="text-align:left;cursor:pointer"><span class="sw">${icon("music")}</span><span class="t"><b>Välj musik</b><small>Egen fil – takten analyseras automatiskt</small></span></button>`;

  let primary;
  if (busy) primary = `<button class="btn primary big push" disabled>Arbetar …</button>`;
  else if (unAnalyzed) primary = `<button class="btn primary big push" data-act="auto">Gör filmer automatiskt</button>`;
  else if (analyzed().length) primary = `<button class="btn primary big push" data-act="generate" ${generating ? "disabled" : ""}>${generating ? "Skapar …" : "Skapa nya filmförslag"}</button>`;
  else primary = `<button class="btn primary big push" disabled>Importera klipp först</button>`;

  const panel = `<aside class="panel" aria-label="Filminställningar">
    <div class="stack"><h2>Vad ska filmen användas till?</h2><div class="fmt-grid">${fmtCards}</div></div>
    <div class="stack"><h2>Längd</h2><div class="seg" role="group" aria-label="Längd" style="grid-template-columns:repeat(4,minmax(0,1fr))">${lens}</div></div>
    <div class="stack"><h2>Stil</h2>${styles}</div>
    <div class="stack"><h2>Musik</h2>${musicBox}</div>
    ${primary}
  </aside>`;
  return side + main + panel;
}

/* ---------- vy: analys ---------- */
function meter(v) {
  const c = v > 0.75 ? "var(--good)" : v > 0.5 ? "var(--warn)" : "var(--bad)";
  return `<span class="meter"><i style="width:${Math.round(v * 100)}%;background:${c}"></i></span>`;
}

function viewAnalyze() {
  const all = usable();
  const done = analyzed();
  const busy = running("analyze");
  const j = job();
  const tagCounts = {};
  done.forEach((c) => (c.analysis.tags || []).forEach((t) => { tagCounts[t] = (tagCounts[t] || 0) + 1; }));
  const tagList = Object.entries(tagCounts).sort((a, b) => b[1] - a[1]);
  const maxTag = tagList.length ? tagList[0][1] : 1;
  const favs = done.filter((c) => c.favorite).length;

  const used = done.filter(isUsed);
  const dropped = done.filter((c) => !isUsed(c));
  if (!["used", "dropped", "fav", "all"].includes(state.filter) && !state.filter.startsWith("tag:")) state.filter = "used";
  let list = used;
  if (state.filter === "all") list = done;
  else if (state.filter === "dropped") list = dropped;
  else if (state.filter === "fav") list = done.filter((c) => c.favorite);
  else if (state.filter.startsWith("tag:")) list = done.filter((c) => (c.analysis.tags || []).includes(state.filter.slice(4)));
  list = [...list].sort((a, b) => b.analysis.score - a.analysis.score);

  const chip = (id, label) => `<button class="chip" data-filter="${esc(id)}" aria-pressed="${state.filter === id}">${esc(label)}</button>`;
  const chips = [chip("used", `I filmerna ${used.length}`), chip("dropped", `Bortvalda ${dropped.length}`),
    chip("fav", `Favoriter ${favs}`), ...tagList.slice(0, 6).map(([t]) => chip(`tag:${t}`, t)), chip("all", `Alla ${done.length}`)].join("");

  const cards = list.map((c) => {
    const a = c.analysis;
    const mid = (a.best[0] + a.best[1]) / 2;
    const left = (a.best[0] / (c.duration || 1)) * 100;
    const width = Math.max(3, ((a.best[1] - a.best[0]) / (c.duration || 1)) * 100);
    const score = Math.round(a.score * 100);
    const inUse = isUsed(c);
    const why = c.excluded ? ["Bortvald av dig"] : (!c.favorite && c.reasons && c.reasons.length ? c.reasons : []);
    return `<article class="ccard ${inUse ? "" : "off"}">
      <div class="img"><img loading="lazy" alt="" src="${frameUrl(c.id, mid, 480)}">
        <span class="badge" style="left:10px;top:10px">${esc(c.source)}</span>
        <span class="score num ${score >= 70 ? "hi" : "lo"}">${score}</span>
        <span class="badge num" style="right:10px;bottom:10px;font-weight:500">${fmtDur(c.duration)}</span></div>
      <div class="body">
        <div class="stack" style="gap:6px"><div class="spread" style="font-size:12px;color:var(--muted)"><span title="${esc(c.name)}">Bästa sekvens</span><span class="num" style="color:var(--text-2)">${fmtDur(a.best[0])}–${fmtDur(a.best[1])}</span></div>
          <div class="best"><span style="left:${left}%;width:${width}%"></span></div></div>
        ${why.length ? `<div class="tags">${why.map((r) => `<span class="tag bad">${esc(r)}</span>`).join("")}</div>` : ""}
        <div class="tags">${(a.tags || []).map((t) => `<span class="tag">${esc(t)}</span>`).join("")}<span class="tag">${esc(a.movement)}</span></div>
        <div class="meters"><span>Skärpa${meter(a.sharpness)}</span><span>Exponering${meter(a.exposure)}</span><span>Stabilitet${meter(a.stability)}</span></div>
        <div class="card-actions">
          <button class="toggle fav" data-fav="${c.id}" aria-pressed="${!!c.favorite}">${icon("star", 14)}${c.favorite ? "Favorit" : (c.auto_excluded ? "Ta med ändå" : "Måste med")}</button>
          <button class="toggle ex" data-ex="${c.id}" aria-pressed="${!!c.excluded}">${icon("eyeoff", 14)}${c.excluded ? "Bortvald" : "Välj bort"}</button>
        </div>
      </div></article>`;
  }).join("");

  const prog = busy
    ? `<div class="progress"><div class="spread" style="font-size:13px"><b data-live-text>${esc(j.message || "")}</b><span class="muted num" data-live-pct>${Math.round((j.progress || 0) * 100)} %</span></div><div class="bar"><div data-live-fill style="width:${(j.progress || 0) * 100}%"></div></div></div>`
    : `<div class="progress"><div class="spread" style="font-size:13px"><b>${used.length} av ${done.length} klipp används</b></div><div class="bar"><div style="width:${done.length ? (used.length / done.length) * 100 : 0}%"></div></div></div>`;

  const main = `<main class="main">
    <div class="spread"><div class="head"><h1>${busy ? "AI analyserar materialet" : "Analysresultat"}</h1>
      <p class="lead">Bara skarpa, stabila och välexponerade klipp används. Svaga klipp väljs bort automatiskt – du behöver inte gå igenom dem.</p></div>${prog}</div>
    <div class="chips" role="group" aria-label="Filtrera">${chips}</div>
    <div class="grid">${cards || '<div class="empty">Inga klipp i det här urvalet ännu.</div>'}</div>
  </main>`;

  const found = tagList.slice(0, 8).map(([t, n]) => `<div class="found"><div class="spread" style="font-size:13px"><span>${esc(t)}</span><span class="muted num">${n} klipp</span></div><span class="meter"><i style="width:${(n / maxTag) * 100}%;background:var(--accent)"></i></span></div>`).join("");
  const info = state.info || {};
  const panel = `<aside class="panel" aria-label="Sammanfattning">
    <section class="stack" style="gap:14px"><h2>Hittat i materialet</h2>${found || '<p class="muted" style="margin:0">Visas när analysen är klar.</p>'}</section>
    <section class="box"><h2 style="font-size:14px">AI-bedömning</h2><p>${info.clip_ai
      ? "AI:n känner igen motiv, bedömer hur sevärd och snygg varje bild är och väljer bara höjdpunkterna. Tomt vatten, sand och ofokuserade bilder sorteras bort."
      : "AI-modellen saknas – urvalet görs med enklare bildanalys."}</p></section>
    <section class="box"><h2 style="font-size:14px">Automatiskt urval</h2><p>${dropped.length ? `${dropped.length} klipp valdes bort (suddiga, skakiga, felexponerade eller klart svagare). Även i godkända klipp används bara de delar som är skarpa hela vägen.` : "Alla klipp klarade kvalitetskraven. Bara de skarpaste delarna används."}</p></section>
    <section class="box"><h2 style="font-size:14px">Favoriter</h2><p>${favs ? `${favs} ${favs === 1 ? "klipp är markerat" : "klipp är markerade"} som "måste med". AI bygger filmen runt dem.` : 'Valfritt: markera klipp med "Måste med" för att alltid få med dem.'}</p></section>
    <div class="stack push">
      <button class="btn small" data-act="diagnostics" title="Sparar en liten rapport med analysvärden och en bild per klipp (inga filmer)">Exportera analysrapport</button>
      <button class="btn" data-act="reanalyze" ${running() ? "disabled" : ""}>Analysera om allt</button>
      <button class="btn primary big" data-act="generate" ${running() || !done.length || generating ? "disabled" : ""}>${generating ? "Skapar …" : "Skapa 3 filmförslag"}</button>
    </div>
  </aside>`;
  return main + panel;
}

/* ---------- vy: förslag ---------- */
function phoneSize(fmt, big = true) {
  const k = big ? 1 : 0.6;
  const map = { "9:16": [148, 263], "4:5": [180, 225], "1:1": [190, 190], "16:9": [260, 146] };
  const [w, h] = map[fmt] || map["9:16"];
  return [Math.round(w * k), Math.round(h * k)];
}

function propCard(p, idx) {
  const si = STYLE_INFO[p.style] || {};
  const [w, h] = phoneSize(p.format);
  const prev = p.renders && p.renders.preview;
  const busyHere = running(`render:preview:${p.id}`);
  const j = job();
  const shots = p.shots || [];
  const poster = shots.length ? frameUrl(shots[0].clip_id, shots[0].src_start + shots[0].duration / 2, 480) : "";
  let phone;
  if (prev) {
    phone = `<video controls playsinline preload="metadata" poster="${poster}" src="${mediaUrl("renders", prev)}"></video>`;
  } else {
    const fr = shots.slice(0, 4).map((s) => `<img alt="" loading="lazy" src="${frameUrl(s.clip_id, s.src_start + s.duration / 2, 320)}">`).join("");
    phone = `<div class="frames">${fr}</div>`;
    phone += busyHere
      ? `<div class="busy"><div class="spinner"></div><span data-live-text>${esc(j.message || "Renderar …")}</span><span class="num" data-live-pct>${Math.round((j.progress || 0) * 100)} %</span></div>`
      : `<button class="play" data-preview="${p.id}" aria-label="Skapa och spela förhandsvisning" ${running() ? "disabled" : ""}>${icon("play", 20)}</button>`;
  }
  const strip = shots.map((s) => `<img alt="" loading="lazy" style="flex:${s.duration} 1 0" src="${frameUrl(s.clip_id, s.src_start + s.duration / 2, 120)}">`).join("");
  const wide = p.format === "16:9";
  return `<article class="pcard ${idx === 0 ? "sel" : ""}">
    <div class="top" style="${wide ? "flex-direction:column" : ""}">
      <div class="phone" style="width:${w}px;height:${h}px">${phone}</div>
      <div class="info">
        <div class="stack" style="gap:4px"><span class="plabel" style="color:${si.color || "var(--accent)"}">Förslag ${"ABCDEFGHIJ"[idx] || ""} · ${esc(p.style_label)}</span>
          <h2 class="pname">${esc(p.title || p.style_label)}</h2><p class="pdesc">${esc(p.story || si.long || "")}</p>
          ${p.short ? `<p class="pdesc" style="color:var(--warn)">Kortare än önskat – det fanns bara ${fmtDur(p.length)} skarpt material.</p>` : ""}</div>
        <dl class="stats">
          <div><dt>Klipp</dt><dd class="num">${p.n_shots}</dd></div>
          <div><dt>Snittlängd</dt><dd class="num">${dec(p.avg_shot)} s</dd></div>
          <div><dt>Längd</dt><dd class="num">${fmtDur(p.length)}</dd></div>
          <div><dt>Musik</dt><dd>${p.music_name ? `${esc(p.music_name)} · ${dec(p.bpm, 0)} BPM` : "Originalljud"}</dd></div>
        </dl>
      </div>
    </div>
    <div class="bottom">
      <div class="stack" style="gap:6px"><div class="strip">${strip}</div>
        <div class="strip-legend"><span>Intro</span><span>Uppbyggnad</span><span>Höjdpunkt</span><span>Avslut</span></div></div>
      <div class="row" style="flex-wrap:nowrap">
        ${prev ? `<button class="btn primary" style="flex:1 1 auto" data-export="${p.id}">Exportera</button>`
               : `<button class="btn primary" style="flex:1 1 auto" data-preview="${p.id}" ${running() ? "disabled" : ""}>Förhandsvisa</button>
                  <button class="btn" data-export="${p.id}">Exportera</button>`}
        <button class="btn icon" data-regen="${p.id}" aria-label="Generera om detta förslag" title="Generera om">${icon("redo", 17)}</button>
      </div>
    </div>
  </article>`;
}

function autoProgress() {
  const j = job();
  const pct = Math.round((j.progress || 0) * 100);
  const stage = (j.message || "").match(/^(\d)\/4/);
  const n = stage ? Number(stage[1]) : 1;
  const steps = ["Läser in", "Analyserar och väljer bort svaga klipp", "Skapar filmförslag", "Gör förhandsvisningar"];
  return `<section class="auto-hero">
    <div class="spinner" style="width:34px;height:34px"></div>
    <h1>DeHazeIQ gör dina filmer</h1>
    <p class="lead">Du behöver inte göra något – förslagen dyker upp här när de är klara.</p>
    <ol class="auto-steps">${steps.map((t, i) => `<li class="${i + 1 < n ? "done" : i + 1 === n ? "now" : ""}"><span>${i + 1 < n ? "✓" : i + 1}</span>${t}</li>`).join("")}</ol>
    <div class="progress" style="width:min(520px,100%)"><div class="spread" style="font-size:13px"><span class="muted" data-live-text>${esc(j.message || "")}</span><span class="num muted" data-live-pct>${pct} %</span></div>
      <div class="bar"><div data-live-fill style="width:${pct}%"></div></div></div>
  </section>`;
}

function viewProposals() {
  if (running("auto")) return `<main class="main wide">${autoProgress()}</main>`;
  const s = settings();
  const props = P().proposals || [];
  const shown = state.shown.map(propById).filter(Boolean);
  const older = props.filter((p) => !state.shown.includes(p.id));
  const favs = clips().filter((c) => c.favorite).length;
  const fmt = FORMAT_INFO.find((f) => f.id === s.format);
  const styleSel = Object.entries(STYLE_INFO).map(([k, v]) => `<button class="chip" data-style="${k}" aria-pressed="${s.style === k}">${v.label}</button>`).join("");
  const themeSel = [`<button class="chip" data-theme="" aria-pressed="${!state.theme}">AI väljer berättelser</button>`]
    .concat((state.themes || []).map((t) => `<button class="chip" data-theme="${esc(t.id)}" aria-pressed="${state.theme === t.id}">${esc(t.title)}<span class="muted"> · ${t.clips} klipp</span></button>`)).join("");
  return `<main class="main wide">
    <div class="spread">
      <div class="head"><h1>${shown.length ? "Filmförslag" : "Inga förslag ännu"}</h1>
        <p class="lead">${esc(fmt ? fmt.name : s.format)} · ${fmtLong(s.length)} · samma material, olika urval, tempo och rytm.</p></div>
      <div class="row">
        ${favs ? `<span class="chip-status" style="height:40px;padding:0 14px;border-radius:10px;background:var(--panel-2);border:1px solid var(--line)">${icon("star", 15)} ${favs === 1 ? "1 favorit är låst" : `${favs} favoriter är låsta`}</span>` : ""}
        <button class="btn" data-act="generate" ${generating || running() ? "disabled" : ""}>${icon("redo", 16)}${generating ? "Skapar …" : "Generera nya förslag"}</button>
      </div>
    </div>
    <div class="props">${shown.map(propCard).join("") || '<div class="empty">Klicka på "Generera nya förslag".</div>'}</div>
    <section class="box" style="flex-direction:row;flex-wrap:wrap;align-items:center;gap:14px">
      <div class="stack" style="gap:8px;flex:1 1 100%"><b>Berättelse</b><div class="chips">${themeSel}</div></div>
      <div class="stack" style="gap:8px;flex:1 1 auto"><b>Stil</b><div class="chips">${styleSel}</div></div>
      <a href="#" data-step-link="import" style="font-size:13px">Ändra format, längd eller musik</a>
    </section>
    ${older.length ? `<section class="older"><h2>Tidigare förslag</h2>${older.slice(0, 9).map((p) => `<div class="older-row"><b>${esc(p.title || p.style_label)}</b><span class="muted">${esc(p.style_label)}</span><span class="muted num">${p.n_shots} klipp · ${fmtDur(p.length)} · ${esc(p.format)}</span><span class="grow"></span><button class="btn small" data-show="${p.id}">Visa</button></div>`).join("")}</section>` : ""}
  </main>`;
}

/* ---------- vy: exportera ---------- */
function viewExport() {
  const props = P().proposals || [];
  if (!state.exportProp || !propById(state.exportProp)) state.exportProp = state.shown[0] || (props[0] && props[0].id);
  const p = propById(state.exportProp);
  if (!p) return `<main class="main"><div class="empty">Skapa ett filmförslag först.</div></main>`;
  const list = state.shown.map(propById).filter(Boolean);
  if (!list.includes(p)) list.unshift(p);
  const choices = list.map((x, i) => `<button class="card-btn" data-pick="${x.id}" aria-pressed="${x.id === p.id}" style="flex-direction:row;align-items:center;gap:14px">
      <img alt="" style="width:46px;height:46px;border-radius:8px;object-fit:cover" src="${x.shots[0] ? frameUrl(x.shots[0].clip_id, x.shots[0].src_start + 1, 120) : ""}">
      <span class="stack" style="gap:2px"><b>${esc(x.style_label)}</b><small>${x.n_shots} klipp · ${fmtDur(x.length)} · ${esc(x.format)}</small></span></button>`).join("");
  const resBtns = [["720p", "720p"], ["1080p", "1080p"], ["4k", "4K"]].map(([k, l]) => `<button data-res="${k}" aria-pressed="${state.exportRes === k}">${l}</button>`).join("");
  const busy = running("render");
  const j = job();
  const r = p.renders || {};
  const files = Object.entries(r).filter(([k]) => k !== "preview");
  const fileRows = files.map(([k, name]) => k === "otio"
    ? `<div class="file"><span class="grow"><b>${esc(name)}</b><small class="muted">Tidslinje för DaVinci Resolve: Arkiv › Importera › Tidslinje</small></span>${remote() ? "" : `<button class="btn small" data-reveal="${esc(name)}">${revealLabel()}</button>`}</div>`
    : `<div class="file"><span class="grow"><b>${esc(name)}</b><small class="muted">${esc(k.toUpperCase())} · ${esc(p.format)}</small></span>${remote()
        ? `<a class="btn small" href="${mediaUrl("renders", name)}" download="${esc(name)}">Spara på enheten</a>`
        : `<a class="btn small" target="_blank" rel="noopener" href="${mediaUrl("renders", name)}">Öppna</a><button class="btn small" data-reveal="${esc(name)}">${revealLabel()}</button>`}</div>`).join("");
  const main = `<main class="main">
    <div class="head"><h1>Exportera filmen</h1><p class="lead">Renderas från originalfilerna i full kvalitet. En tidslinje (.otio) skapas samtidigt för finredigering.</p></div>
    <section class="stack"><h2>Förslag</h2><div class="stack" style="gap:8px">${choices}</div></section>
    <section class="stack"><h2>Upplösning</h2><div class="seg" role="group" aria-label="Upplösning" style="grid-template-columns:repeat(3,minmax(0,1fr));max-width:420px">${resBtns}</div>
      <p class="muted" style="margin:0;font-size:13px">Bildformat ${esc(p.format)}. Byt format genom att generera nya förslag.</p></section>
    ${busy ? `<div class="progress"><div class="spread" style="font-size:13px"><b data-live-text>${esc(j.message || "")}</b><span class="muted num" data-live-pct>${Math.round((j.progress || 0) * 100)} %</span></div><div class="bar"><div data-live-fill style="width:${(j.progress || 0) * 100}%"></div></div></div>` : ""}
  </main>`;
  const panel = `<aside class="panel" aria-label="Exporterade filer">
    <section class="stack"><h2>Exporterade filer</h2><div class="files">${fileRows || '<p class="muted" style="margin:0">Inga exporter ännu för det här förslaget.</p>'}</div></section>
    <p class="muted" style="margin:0;font-size:12px">Filerna sparas i projektmappen under renders. Kodning: ${esc((state.info && state.info.encoder) || "")}.</p>
    <button class="btn primary big push" data-act="export" ${running() ? "disabled" : ""}>${busy ? "Exporterar …" : `Exportera ${state.exportRes === "4k" ? "4K" : state.exportRes}`}</button>
  </aside>`;
  return main + panel;
}

/* ---------- mobil via wifi ---------- */
async function openLan() {
  let st;
  try { st = await api("GET", "/api/lan"); } catch (e) { return fail(e); }
  const m = $("#modal");
  const body = st.enabled
    ? `<p class="lead">Öppna adressen i mobilens eller surfplattans webbläsare. Enheten måste vara på samma wifi som datorn.</p>
       <div class="stack" style="gap:8px">${(st.urls.length ? st.urls : [`port ${st.port}`]).map((u) => `<div class="lan-url num">${esc(u)}</div>`).join("")}</div>
       <div class="stack" style="gap:4px"><span class="eyebrow">Kod</span><div class="lan-key num">${esc(st.key)}</div></div>
       <p class="muted" style="margin:0;font-size:13px">På mobilen kan du granska analysen, markera favoriter, skapa förslag, förhandsvisa och exportera. Import och musik väljs på datorn. Första gången kan brandväggen fråga om tillåtelse.</p>
       <div class="row"><button class="btn" data-act="lan-off">Stäng av</button><button class="btn primary" data-act="modal-close">Klar</button></div>`
    : `<p class="lead">Styr DeHazeIQ från mobil eller surfplatta via wifi. Datorn gör allt tungt arbete, filmerna stannar på datorn.</p>
       <p class="muted" style="margin:0;font-size:13px">Bara enheter på samma nätverk som har koden kommer åt programmet.</p>
       <div class="row"><button class="btn" data-act="modal-close">Avbryt</button><button class="btn primary" data-act="lan-on">${icon("wifi", 16)}Slå på</button></div>`;
  m.innerHTML = `<div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="lanTitle"><h2 id="lanTitle" style="font-size:18px">${icon("phone", 18)} Mobil och surfplatta</h2>${body}</div>`;
  m.hidden = false;
}

async function setLan(enable) {
  try { await api("POST", "/api/lan", { enable }); } catch (e) { return fail(e); }
  return openLan();
}

/* ---------- render ---------- */
function render() {
  renderTop();
  const v = $("#view");
  if (!P()) {
    v.innerHTML = `<main class="main" style="max-width:600px;margin:56px auto;align-items:center">
      <div class="hero"><img src="/static/logo.png" alt="DeHazeIQ">
        <h1>Välkommen till DeHazeIQ</h1><p class="tagline">AI-powered video editing, without the hassle</p>
        <p class="lead">Välj mappen med dina filmklipp. Resten sköts automatiskt: analys, bortval av suddiga klipp och tre färdiga filmförslag.</p>
        ${remote() ? '<p class="lead">Starta en import på datorn.</p>' : `<button class="btn primary big" style="padding:0 28px" data-act="new-import">${icon("folder", 18)}Välj mapp med filmklipp</button>
        <button class="btn small" data-act="new-import-files">eller välj enskilda filer</button>
        <form class="pathrow" id="welcomePath"><label class="sr" for="welcomeInput">Sökväg</label><input class="field" id="welcomeInput" placeholder="… eller klistra in en sökväg"><button class="btn" type="submit">Starta</button></form>`}</div></main>`;
    return;
  }
  const views = { import: viewImport, analyze: viewAnalyze, proposals: viewProposals, export: viewExport };
  v.innerHTML = (views[state.view] || viewImport)();
}

/* ---------- händelser ---------- */
document.addEventListener("click", async (ev) => {
  const t = ev.target.closest("button, a[data-step-link]");
  if (!t) return;
  const d = t.dataset;
  if (d.stepLink) { ev.preventDefault(); state.view = d.stepLink; return render(); }
  if (d.step) { state.view = d.step; return render(); }
  if (d.proj) {
    await loadProject(d.proj);
    state.view = running("auto") || (P().proposals || []).length ? "proposals" : analyzed().length ? "analyze" : "import";
    return render();
  }
  if (d.rename) return openRename(d.rename);
  if (d.delete) return openDelete(d.delete);
  if (d.delConfirm) return deleteProject(d.delConfirm);
  if (d.format) return saveSettings({ format: d.format });
  if (d.length) return saveSettings({ length: Number(d.length) });
  if (d.style) return saveSettings({ style: d.style });
  if (d.theme !== undefined) { state.theme = d.theme || null; return render(); }
  if (d.filter) { state.filter = d.filter; return render(); }
  if (d.fav) return toggleClip(d.fav, "favorite");
  if (d.ex) return toggleClip(d.ex, "excluded");
  if (d.preview) return renderProp(d.preview, "preview");
  if (d.regen) return regenerate(d.regen);
  if (d.export) { state.exportProp = d.export; state.view = "export"; return render(); }
  if (d.pick) { state.exportProp = d.pick; return render(); }
  if (d.res) { state.exportRes = d.res; return render(); }
  if (d.reveal) return reveal(state.exportProp, d.reveal);
  if (d.show) { state.shown = [d.show, ...state.shown.filter((x) => x !== d.show)].slice(0, 3); saveShown(); return render(); }
  switch (d.act) {
    case "new-import": return newImport(await choosePaths("folder"));
    case "new-import-files": return newImport(await choosePaths("files"));
    case "add-folder": return addToProject(await choosePaths("folder"));
    case "add-files": return addToProject(await choosePaths("files"));
    case "auto": return runAuto();
    case "analyze": return startAnalyze(false);
    case "reanalyze": return startAnalyze(true);
    case "generate": return generate();
    case "music": return chooseMusic();
    case "music-remove": return removeMusic();
    case "export": return renderProp(state.exportProp, state.exportRes);
    case "lan": return openLan();
    case "diagnostics":
      try {
        const r = await api("POST", `/api/p/${state.pid}/diagnostics`);
        if (remote()) window.location.href = mediaUrl("renders", r.file);
        else toast(`Rapporten är sparad: ${r.file}\nSkicka den till Claude för att justera urvalet.`, true);
      } catch (e) { fail(e); }
      return undefined;
    case "lan-on": return setLan(true);
    case "lan-off": return setLan(false);
    case "modal-close": $("#modal").hidden = true; return undefined;
    default: return undefined;
  }
});

document.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  if (ev.target.id === "renameForm") {
    const pid = ev.target.dataset.pid;
    const name = $("#rnName").value.trim();
    if (!name) return;
    try {
      await api("POST", `/api/p/${pid}/rename`, { name });
      $("#modal").hidden = true;
      await loadProjects();
      if (state.pid === pid) P().name = name;
      render();
    } catch (e) { fail(e); }
  } else if (ev.target.id === "pathForm") {
    const v = $("#pathInput").value.trim();
    if (v) addToProject(v.split("\n").map((x) => x.trim()).filter(Boolean));
  } else if (ev.target.id === "welcomePath") {
    const v = $("#welcomeInput").value.trim();
    if (v) newImport(v.split("\n").map((x) => x.trim()).filter(Boolean));
  }
});

/* ---------- start ---------- */
(async function init() {
  try {
    state.info = await api("GET", "/api/info");
    await loadProjects();
    const saved = localStorage.getItem("tv.pid");
    const pid = state.projects.find((p) => p.id === saved) ? saved : (state.projects[0] && state.projects[0].id);
    if (pid) {
      await loadProject(pid);
      if (running("auto") || (P().proposals || []).length) state.view = "proposals";
      else if (analyzed().length) state.view = "analyze";
    }
  } catch (e) { fail(e); }
  render();
})();
