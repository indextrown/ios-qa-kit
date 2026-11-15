// qakit ui (U1): 결과 보기 + 시뮬레이터 라이브 화면 (보기 전용). 서버는 bin/qakit의 cmd_ui.
"use strict";

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const api = async (path) => {
  const r = await fetch(path, { cache: "no-store" });
  if (!r.ok) throw new Error((await r.text()) || r.status);
  return r.json();
};
const fileUrl = (dir, name) => `/api/file?dir=${encodeURIComponent(dir)}&name=${encodeURIComponent(name)}`;
const RESULT = { Passed: "통과", Failed: "실패", unknown: "알 수 없음" };
const pill = (result) => `<span class="pill ${esc(RESULT[result] ? result : "other")}">${esc(RESULT[result] || result)}</span>`;
const when = (iso) => (iso ? iso.replace("T", " ").slice(5, 16) : "");
const secs = (s) => (s == null ? "" : `${Number(s).toFixed(1)}초`);

// ── 상단 정보
async function loadInfo() {
  try {
    const i = await api("/api/info");
    $("#ws-name").textContent = i.name;
    const app = i.app || {};
    $("#ws-meta").textContent = [i.device ? `실기기 ${i.device}` : i.simulator, app.branch && `${app.branch}@${app.commit}`,
      app.dirtyFiles ? `미커밋 ${app.dirtyFiles}` : null, i.precheck && `precheck: ${i.precheck}`, `qakit ${i.kit}`]
      .filter(Boolean).join("  ·  ");
    $("#live-device").textContent = i.simulator || "실기기 (라이브 화면 미지원)";
  } catch (e) {
    $("#ws-meta").textContent = `정보를 불러오지 못함: ${e.message}`;
  }
}

// ── 실행 기록
let runsCache = [];
async function showRuns() {
  $("#main").innerHTML = `<h1>실행 기록</h1><p class="muted">results/ 폴더와 history.jsonl. 행을 누르면 상세.</p>
    <div class="toolbar">
      <select id="f-result"><option value="">전체</option><option value="Failed">실패만</option><option value="Passed">통과만</option></select>
      <input id="f-text" placeholder="이름 검색" size="24">
      <button id="f-reload" type="button">새로고침</button>
      <span id="f-count" class="muted small"></span>
    </div><div id="runs"><p class="muted">불러오는 중…</p></div>`;
  const render = () => {
    const fr = $("#f-result").value, ft = $("#f-text").value.trim().toLowerCase();
    const rows = runsCache.filter((r) => (!fr || r.result === fr) && (!ft || r.name.toLowerCase().includes(ft)));
    $("#f-count").textContent = `${rows.length} / ${runsCache.length}개`;
    $("#runs").innerHTML = rows.length ? `<table><thead><tr><th>결과</th><th>이름</th><th>종류</th><th>시작</th><th>시간</th><th>경로</th></tr></thead><tbody>${
      rows.map((r) => `<tr class="click" data-dir="${esc(r.dir)}"><td>${pill(r.result)}${r.screenshot ? " 📷" : ""}</td>
        <td>${esc(r.name)}${r.device ? ` <span class="chip">${esc(r.device)}</span>` : ""}</td><td>${esc(r.kind)}</td>
        <td>${esc(when(r.start))}</td><td>${esc(secs(r.seconds))}</td><td class="muted">${esc(r.via || "")}</td></tr>`).join("")
    }</tbody></table>` : `<p class="muted">맞는 실행이 없습니다.</p>`;
    document.querySelectorAll("tr[data-dir]").forEach((tr) => tr.addEventListener("click", () => { location.hash = `#/run/${tr.dataset.dir}`; }));
  };
  const load = async () => {
    try { runsCache = await api("/api/runs?limit=300"); render(); }
    catch (e) { $("#runs").innerHTML = `<p class="muted">불러오지 못함: ${esc(e.message)}</p>`; }
  };
  $("#f-result").addEventListener("change", render);
  $("#f-text").addEventListener("input", render);
  $("#f-reload").addEventListener("click", load);
  await load();
}

// ── 실행 상세
async function showRun(dir) {
  $("#main").innerHTML = `<p><a href="#/runs">← 실행 기록</a></p><p class="muted">불러오는 중…</p>`;
  let d, meta;
  try {
    d = await api(`/api/run?dir=${encodeURIComponent(dir)}`);
    if (!runsCache.length) runsCache = await api("/api/runs?limit=300");
    meta = runsCache.find((r) => r.dir === dir) || {};
  } catch (e) {
    $("#main").innerHTML = `<p><a href="#/runs">← 실행 기록</a></p><p class="muted">불러오지 못함: ${esc(e.message)}</p>`;
    return;
  }
  const max = Math.max(1, ...d.timings.map((t) => t.seconds));
  const bars = d.timings.length ? `<div class="bars">${d.timings.map((t) => `<div class="bar ${t.name.startsWith("▸") ? "group" : ""} ${t.name.startsWith("앱") ? "launch" : ""}">
      <span>${t.seconds.toFixed(1)}초</span><div><div class="lbl" style="padding-left:${t.depth * 14}px" title="${esc(t.name)}">${esc(t.name)}${t.interrupts ? ` <span class="muted">(끼어드는 화면 ${t.interrupts}초)</span>` : ""}</div>
      <div class="fill" style="width:${(t.seconds / max) * 100}%;margin-left:${t.depth * 14}px"></div></div></div>`).join("")}</div>` : `<p class="muted">단계별 시간 없음 (상주 실행기로 돈 run만 남음)</p>`;
  $("#main").innerHTML = `<p><a href="#/runs">← 실행 기록</a></p>
    <h1>${esc(meta.name || dir)} ${pill(meta.result || "unknown")}</h1>
    <div class="kv"><span>${esc(when(meta.start))}</span><span>${esc(secs(meta.seconds))}</span><span>${esc(meta.via || "")}</span>
      ${meta.app ? `<span>${esc(meta.app.branch || "")}@${esc(meta.app.commit || "")}</span>` : ""}<span>${esc(meta.kit || "")}</span><span class="small">results/${esc(dir)}</span></div>
    <h2>요약</h2><pre>${esc(d.summary || "(요약 없음)")}</pre>
    ${d.images.length ? `<h2>스크린샷</h2><div class="grid">${d.images.map((n) => `<a href="${fileUrl(dir, n)}" target="_blank"><img src="${fileUrl(dir, n)}" alt="${esc(n)}"></a>`).join("")}</div>` : ""}
    <h2>단계별 시간${d.timingHead ? ` <span class="muted small">${esc(d.timingHead)}</span>` : ""}</h2>${bars}
    ${d.dumps.length ? `<h2>화면 구조·파일</h2><div class="links">${d.dumps.map((n) => `<button type="button" data-file="${esc(n)}">${esc(n)}</button>`).join("")}</div><pre id="file-view" hidden></pre>` : ""}
    <h2>로그 (끝 400줄)</h2><pre>${esc(d.log || "(로그 없음)")}</pre>`;
  document.querySelectorAll("button[data-file]").forEach((b) => b.addEventListener("click", async () => {
    const r = await fetch(fileUrl(dir, b.dataset.file));
    const v = $("#file-view"); v.hidden = false; v.textContent = await r.text();
  }));
}

// ── 시나리오 · 실행 (U2): 체크박스로 골라 실행, 실시간 로그, 멈춤
const sel = new Set(JSON.parse(sessionStorage.getItem("qakit-sel") || "[]"));
const saveSel = () => { try { sessionStorage.setItem("qakit-sel", JSON.stringify([...sel])); } catch (_) { /* 무시 */ } };
let scList = [];
const job = { from: 0, timer: null, running: false };
const CODE = { 0: "모두 통과", 1: "앱 판정 실패가 있음", 2: "실행 환경·설정 문제", 130: "멈춤", "-2": "멈춤", "-15": "멈춤" };
const post = async (path, body) => {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json", "X-Qakit-UI": "1" }, body: JSON.stringify(body || {}) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || r.status);
  return j;
};

async function showScenarios() {
  $("#main").innerHTML = `<h1>시나리오 · 실행</h1>
    <p class="muted">골라서 실행합니다. 최근 10번 결과는 왼쪽이 오래된 것 (회색: 환경 실패). 통과·실패가 섞이면 불안정.</p>
    <div class="runbar">
      <div class="toolbar">
        <input id="s-text" placeholder="이름·설명 검색" size="22">
        <button id="s-all" type="button">보이는 것 모두 선택</button>
        <button id="s-none" type="button">선택 해제</button>
        <span id="s-tags"></span>
      </div>
      <div class="toolbar">
        <label><input type="checkbox" id="o-reuse" checked> 앱 재사용 (--reuse-app)</label>
        <label>실패하면
          <select id="o-stop"><option value="">같은 원인 2번이면 멈춤</option><option value="never">끝까지</option><option value="first">첫 실패에서 멈춤</option></select>
        </label>
        <label><input type="checkbox" id="o-precheck" checked> 사전 확인</label>
        <button id="s-run" type="button" class="primary">선택한 0개 실행</button>
        <button id="s-stop" type="button" hidden>멈춤</button>
      </div>
    </div>
    <div id="job" hidden><h2>실행 <span id="job-status" class="muted small"></span></h2><pre id="job-log"></pre></div>
    <div id="sc"><p class="muted">불러오는 중…</p></div>`;
  $("#s-text").addEventListener("input", renderScenarios);
  $("#s-all").addEventListener("click", () => { visible().forEach((s) => sel.add(s.name)); saveSel(); renderScenarios(); });
  $("#s-none").addEventListener("click", () => { sel.clear(); saveSel(); renderScenarios(); });
  $("#s-run").addEventListener("click", runSelected);
  $("#s-stop").addEventListener("click", async () => { await post("/api/job/stop"); $("#job-status").textContent = "멈추는 중…"; });
  await loadScenarios();
  pollJob(true);
}
const visible = () => {
  const t = ($("#s-text")?.value || "").trim().toLowerCase();
  return scList.filter((s) => !t || `${s.name} ${s.title} ${s.description}`.toLowerCase().includes(t));
};
async function loadScenarios() {
  try { scList = await api("/api/scenarios"); renderScenarios(); }
  catch (e) { $("#sc").innerHTML = `<p class="muted">불러오지 못함: ${esc(e.message)}</p>`; }
}
function renderScenarios() {
  if (!$("#sc")) return;
  const tags = [...new Set(scList.flatMap((s) => s.tags))].sort();
  $("#s-tags").innerHTML = tags.length ? `태그 선택: ${tags.map((t) => `<button type="button" class="chip-btn" data-tag="${esc(t)}">${esc(t)}</button>`).join("")}` : "";
  document.querySelectorAll("[data-tag]").forEach((b) => b.addEventListener("click", () => {
    scList.filter((s) => s.tags.includes(b.dataset.tag)).forEach((s) => sel.add(s.name)); saveSel(); renderScenarios();
  }));
  const rows = visible();
  $("#sc").innerHTML = `<table><thead><tr><th></th><th>이름</th><th>설명</th><th>태그</th><th>최근 결과</th><th>마지막</th></tr></thead><tbody>${
    rows.map((s) => `<tr class="click" data-name="${esc(s.name)}"><td><input type="checkbox" ${sel.has(s.name) ? "checked" : ""} aria-label="${esc(s.name)} 선택"></td>
      <td><strong>${esc(s.name)}</strong>${s.flaky ? ` <span class="pill flaky">불안정</span>` : ""}<div class="small">${esc(s.title)}</div></td>
      <td class="small">${esc(s.description)}</td><td>${s.tags.map((t) => `<span class="chip">${esc(t)}</span>`).join("")}</td>
      <td class="dots">${s.recent.map((r) => `<span class="${r === "pass" ? "ok" : r === "env" ? "env" : ""}" title="${r === "pass" ? "통과" : r === "env" ? "환경 실패" : "실패"}"></span>`).join("") || `<span class="muted small">기록 없음</span>`}</td>
      <td class="small">${s.last ? `${pill(s.last.result)} ${esc(when(s.last.at))}${s.last.dir ? ` <a href="#/run/${esc(s.last.dir)}">상세</a>` : ""}` : ""}</td></tr>`).join("")
  }</tbody></table>`;
  document.querySelectorAll("tr[data-name]").forEach((tr) => tr.addEventListener("click", (ev) => {
    if (ev.target.closest("a")) return;
    const n = tr.dataset.name;
    if (sel.has(n)) sel.delete(n); else sel.add(n);
    saveSel(); renderScenarios();
  }));
  const n = [...sel].filter((x) => scList.some((s) => s.name === x)).length;
  $("#s-run").textContent = `선택한 ${n}개 실행`;
  $("#s-run").disabled = job.running || n === 0;
}
async function runSelected() {
  const names = scList.map((s) => s.name).filter((n) => sel.has(n));   // 목록 순서대로
  try {
    await post("/api/run", { scenarios: names, options: {
      reuse: $("#o-reuse").checked, stop: $("#o-stop").value || null, precheck: $("#o-precheck").checked } });
    job.from = 0; $("#job-log").textContent = "";
    pollJob(true);
  } catch (e) { alert(`실행하지 못함: ${e.message}`); }
}
async function pollJob(force) {
  clearTimeout(job.timer);
  let st;
  try { st = await api(`/api/job?from=${job.from}`); } catch (_) { job.timer = setTimeout(pollJob, 2000); return; }
  if (!st.args) { job.running = false; updateRunningBadge(); return; }
  if (force && job.from === 0 && $("#job-log")) $("#job-log").textContent = "";
  job.from = st.total;
  const wasRunning = job.running;
  job.running = st.running;
  updateRunningBadge();
  if ($("#job")) {
    $("#job").hidden = false;
    const log = $("#job-log");
    if (st.lines.length) { log.textContent += st.lines.join("\n") + "\n"; log.scrollTop = log.scrollHeight; }
    const secs = Math.round(((st.ended || Date.now() / 1000) - st.started));
    $("#job-status").textContent = `${st.args.join(" ")} · ${secs}초` + (st.running ? " · 실행 중" : ` · 끝 (종료 코드 ${st.code}: ${CODE[st.code] ?? "?"})`);
    $("#s-stop").hidden = !st.running;
    $("#s-run").disabled = st.running || ![...sel].length;
  }
  if (wasRunning && !st.running) { loadScenarios(); runsCache = []; }
  if (st.running) job.timer = setTimeout(pollJob, 1000);
}
function updateRunningBadge() {
  const b = $("#running");
  b.hidden = !job.running;
}

// ── 라이브 조작 (U3): 화면 위 요소 → ID·라벨로 단계, qakit do로 실행
const TYPE = { Button: "button", StaticText: "text", Text: "text", Image: "image", Cell: "cell", TextField: "textfield",
  SecureTextField: "securetextfield", Switch: "switch", Other: "other", CollectionView: "collectionview",
  ScrollView: "scrollview", Table: "table", SegmentedControl: "segment" };
const PREFER = new Set(["Button", "Cell", "TextField", "SecureTextField", "Switch", "Link", "Tab", "SegmentedControl"]);
const lv = { els: [], screen: null, sel: null, timer: null, at: null };
const yq = (v) => (/^[^\s"'{}\[\],:#&*!|>%@`-][^{}\[\],:#"]*$/.test(v) && !/\s$/.test(v) && !/: /.test(v) ? v : JSON.stringify(v));
function selectorFor(e) {
  const same = (k) => lv.els.filter((x) => x[k] === e[k]);
  if (e.id && !e.id.startsWith("_Tt")) {
    const dup = same("id");
    return dup.length > 1 ? `{ id: ${yq(e.id)}, index: ${dup.indexOf(e)} }` : yq(e.id);
  }
  const type = TYPE[e.type] || "any";
  const raw = e.labelRaw || "";
  if (raw.includes("\n")) return `{ type: ${type}, contains: ${yq(raw.split("\n")[0])} }`;
  const dup = lv.els.filter((x) => x.labelRaw === raw && x.type === e.type);
  return `{ type: ${type}, label: ${yq(raw)}${dup.length > 1 ? `, index: ${dup.indexOf(e)}` : ""} }`;
}
async function showLive() {
  $("#main").innerHTML = `<h1>라이브 조작</h1>
    <p class="muted">화면을 눌러 요소를 고르고 동작을 실행합니다 (qakit do — ID 우선, 없으면 라벨). 통과한 단계는 기록됩니다.
      <span class="legend small"><span style="color:#2f6fed">━ ID 있음</span><span style="color:#b45309">┅ 라벨만</span></span></p>
    <div class="live-wrap">
      <div><div class="stage"><div class="screen"><img id="lv-img" alt="시뮬레이터 화면"><div id="lv-overlay" class="overlay"></div></div></div>
        <p class="small muted" id="lv-status"></p></div>
      <div>
        <div class="panel"><h3>앱·화면</h3><div class="actions">
          <button type="button" id="lv-launch">앱 다시 켜기 (기록 새로 시작)</button>
          <button type="button" id="lv-dump">화면 구조 새로고침</button>
          <label class="small"><input type="checkbox" id="lv-boxes" checked> 요소 테두리</label></div></div>
        <div class="panel sel-info"><h3>고른 요소</h3><div id="lv-sel" class="muted">화면을 눌러 요소를 고르세요</div>
          <div class="actions" id="lv-actions" hidden>
            <button type="button" data-act="tap" class="primary">탭</button>
            <button type="button" data-act="wait">나타날 때까지 기다림</button>
            <button type="button" data-act="expect">보이는지 확인</button>
            <button type="button" data-act="up">위로 쓸기</button>
            <button type="button" data-act="down">아래로 쓸기</button>
          </div></div>
        <div class="panel"><h3>단계 직접 실행</h3>
          <input id="do-input" placeholder="예) tap: home_search_button  ·  { tap: X, expect: { visible: Y } }">
          <div class="actions"><button type="button" id="do-run">실행</button></div>
          <pre id="do-result" hidden></pre></div>
        <div class="panel steps"><h3>기록된 단계 <span id="lv-steps-note" class="muted small"></span></h3><div id="lv-steps" class="muted small">없음</div></div>
      </div>
    </div>`;
  $("#lv-launch").addEventListener("click", () => doStep("launch"));
  $("#lv-dump").addEventListener("click", loadElements);
  $("#lv-boxes").addEventListener("change", drawBoxes);
  $("#do-run").addEventListener("click", () => doStep($("#do-input").value.trim()));
  $("#do-input").addEventListener("keydown", (e) => { if (e.key === "Enter") doStep($("#do-input").value.trim()); });
  document.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", () => {
    const s = selectorFor(lv.sel);
    const step = { tap: `tap: ${s}`, wait: `wait: { for: ${s}, timeout: 10 }`, expect: `expect: { visible: ${s} }`,
      up: `swipe: { on: ${s}, dir: up }`, down: `swipe: { on: ${s}, dir: down }` }[b.dataset.act];
    doStep(step);
  }));
  const ov = $("#lv-overlay");
  ov.addEventListener("click", (ev) => { const e = hit(ev); if (e) { lv.sel = e; renderSel(); drawBoxes(); } });
  ov.addEventListener("mousemove", (ev) => { const e = hit(ev); ov.title = e ? `${e.type} ${e.id ? "#" + e.id : ""} ${e.label ? `"${e.label}"` : ""}` : ""; });
  liveLoop();
  loadElements();
  loadSteps();
}
function hit(ev) {
  if (!lv.screen) return null;
  const r = $("#lv-overlay").getBoundingClientRect();
  const x = ((ev.clientX - r.left) / r.width) * lv.screen.w, y = ((ev.clientY - r.top) / r.height) * lv.screen.h;
  const inside = lv.els.filter((e) => x >= e.x && x <= e.x + e.w && y >= e.y && y <= e.y + e.h);
  const pick = inside.filter((e) => PREFER.has(e.type)).length ? inside.filter((e) => PREFER.has(e.type)) : inside;
  return pick.sort((a, b) => a.w * a.h - b.w * b.h || b.depth - a.depth)[0] || null;
}
function drawBoxes() {
  const ov = $("#lv-overlay");
  if (!ov || !lv.screen) return;
  const show = $("#lv-boxes").checked;
  ov.innerHTML = lv.els.filter((e) => show || e === lv.sel).map((e) => `<div class="box ${e.id && !e.id.startsWith("_Tt") ? "" : "noid"} ${e === lv.sel ? "sel" : ""}"
    style="left:${(e.x / lv.screen.w) * 100}%;top:${(e.y / lv.screen.h) * 100}%;width:${(e.w / lv.screen.w) * 100}%;height:${(e.h / lv.screen.h) * 100}%"></div>`).join("");
}
function renderSel() {
  const e = lv.sel;
  $("#lv-actions").hidden = !e;
  $("#lv-sel").innerHTML = e ? `<div>${esc(e.type)} ${e.id ? `<code>#${esc(e.id)}</code>` : `<span class="pill flaky">ID 없음 — 라벨로</span>`} ${e.label ? `"${esc(e.label)}"` : ""}</div>
    <div class="small muted">@${e.x},${e.y} ${e.w}x${e.h}</div><div>단계 대상: <code>${esc(selectorFor(e))}</code></div>` : "화면을 눌러 요소를 고르세요";
}
async function loadElements() {
  $("#lv-status").textContent = "화면 구조 읽는 중…";
  try {
    const d = await api("/api/elements");
    lv.screen = d.screen; lv.els = d.elements; lv.at = new Date();
    if (lv.sel) lv.sel = lv.els.find((e) => e.id === lv.sel.id && e.labelRaw === lv.sel.labelRaw && e.type === lv.sel.type) || null;
    renderSel(); drawBoxes();
    $("#lv-status").textContent = `요소 ${lv.els.length}개 · 구조 ${lv.at.toLocaleTimeString()}`;
  } catch (e) { $("#lv-status").textContent = `화면 구조를 읽지 못함: ${e.message}`; }
}
async function loadSteps() {
  try {
    const d = await api("/api/do-steps");
    $("#lv-steps-note").textContent = d.fromLaunch ? "(앱을 다시 켠 뒤부터)" : d.steps.length ? "(앱 다시 켜기 전 것 포함)" : "";
    $("#lv-steps").innerHTML = d.steps.length ? `<ol>${d.steps.map((s) => `<li><code>${esc(s)}</code></li>`).join("")}</ol>` : "없음";
  } catch (_) { /* 무시 */ }
}
async function doStep(step) {
  if (!step) return;
  const out = $("#do-result");
  out.hidden = false; out.className = ""; out.textContent = `실행 중: ${step}`;
  document.querySelectorAll("#main button").forEach((b) => { b.disabled = true; });
  try {
    const r = await post("/api/do", { step });
    out.className = r.code === 0 ? "result-ok" : "result-fail";
    out.textContent = `${step}\n${r.output.trim()}`;
  } catch (e) { out.className = "result-fail"; out.textContent = `${step}\n${e.message}`; }
  document.querySelectorAll("#main button").forEach((b) => { b.disabled = false; });
  await liveShot();
  await loadElements();
  loadSteps();
}
async function liveShot() {
  try {
    const r = await fetch(`/api/screen?ts=${Date.now()}`, { cache: "no-store" });
    if (!r.ok) throw new Error((await r.json()).error || r.status);
    const url = URL.createObjectURL(await r.blob());
    const img = $("#lv-img");
    if (!img) return;
    if (img.dataset.url) URL.revokeObjectURL(img.dataset.url);
    img.src = url; img.dataset.url = url;
  } catch (e) { if ($("#lv-status")) $("#lv-status").textContent = `화면을 가져오지 못함: ${e.message}`; }
}
function liveLoop() {
  clearTimeout(lv.timer);
  if (!location.hash.startsWith("#/live")) return;
  liveShot().finally(() => { lv.timer = setTimeout(liveLoop, 1000); });
}

// ── 라이브 화면 (보기 전용)
const live = { on: false, timer: null, url: null };
async function tick() {
  live.timer = null;
  if (!live.on || location.hash.startsWith("#/live")) return;
  const started = performance.now();
  try {
    const r = await fetch(`/api/screen?ts=${Date.now()}`, { cache: "no-store" });
    if (!r.ok) throw new Error((await r.json()).error || r.status);
    const blob = await r.blob();
    if (live.url) URL.revokeObjectURL(live.url);
    live.url = URL.createObjectURL(blob);
    $("#live-img").src = live.url;
    $("#live-img").classList.add("on");
    $("#live-empty").hidden = true;
    $("#live-status").textContent = `${new Date().toLocaleTimeString()} 갱신 · ${Math.round(performance.now() - started)}ms`;
  } catch (e) {
    $("#live-status").textContent = `화면을 가져오지 못함: ${e.message}`;
  }
  if (live.on) live.timer = setTimeout(tick, Number($("#live-interval").value));
}
function setLive(on) {
  live.on = on;
  clearTimeout(live.timer);
  $("#live-toggle").textContent = on ? "끄기" : "켜기";
  if (on) tick();
  try { localStorage.setItem("qakit-live", on ? "1" : "0"); } catch (_) { /* 저장 못 해도 동작 */ }
}
$("#live-toggle").addEventListener("click", () => setLive(!live.on));
$("#live-interval").addEventListener("change", () => { if (live.on) { clearTimeout(live.timer); tick(); } });

// ── 라우팅
function route() {
  const h = location.hash || "#/runs";
  document.querySelectorAll("[data-nav]").forEach((a) => a.classList.toggle("on", h.startsWith(`#/${a.dataset.nav}`) || (a.dataset.nav === "runs" && h.startsWith("#/run/"))));
  document.body.classList.toggle("live-page", h.startsWith("#/live"));
  if (h.startsWith("#/live")) return showLive();   // 오른쪽 라이브 화면은 이 화면에서 쉰다 (tick이 건너뜀)
  if (live.on && !live.timer) tick();
  if (h.startsWith("#/run/")) return showRun(decodeURIComponent(h.slice(6)));
  if (h.startsWith("#/scenarios")) return showScenarios();
  return showRuns();
}
window.addEventListener("hashchange", route);
loadInfo();
route();
pollJob();   // 다른 화면에 있어도 실행 중 표시
let saved = "1";
try { saved = localStorage.getItem("qakit-live") ?? "1"; } catch (_) { /* 기본 켜기 */ }
setLive(saved === "1");
