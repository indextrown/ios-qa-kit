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

// ── 시나리오
async function showScenarios() {
  $("#main").innerHTML = `<h1>시나리오</h1><p class="muted">scenarios/*.qa.yml · 최근 10번 결과 (왼쪽이 오래된 것). 통과·실패가 섞이면 불안정.</p><div id="sc"><p class="muted">불러오는 중…</p></div>`;
  let list;
  try { list = await api("/api/scenarios"); }
  catch (e) { $("#sc").innerHTML = `<p class="muted">불러오지 못함: ${esc(e.message)}</p>`; return; }
  $("#sc").innerHTML = `<table><thead><tr><th>이름</th><th>설명</th><th>태그</th><th>최근 결과</th><th>마지막</th></tr></thead><tbody>${
    list.map((s) => `<tr><td><strong>${esc(s.name)}</strong>${s.flaky ? ` <span class="pill flaky">불안정</span>` : ""}<div class="small">${esc(s.title)}</div></td>
      <td class="small">${esc(s.description)}</td><td>${s.tags.map((t) => `<span class="chip">${esc(t)}</span>`).join("")}</td>
      <td class="dots">${s.recent.map((ok) => `<span class="${ok ? "ok" : ""}" title="${ok ? "통과" : "실패"}"></span>`).join("") || `<span class="muted small">기록 없음</span>`}</td>
      <td class="small">${s.last ? `${pill(s.last.result)} ${esc(when(s.last.at))}${s.last.dir ? ` <a href="#/run/${esc(s.last.dir)}">상세</a>` : ""}` : ""}</td></tr>`).join("")
  }</tbody></table>`;
}

// ── 라이브 화면 (보기 전용)
const live = { on: false, timer: null, url: null };
async function tick() {
  if (!live.on) return;
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
  if (h.startsWith("#/run/")) return showRun(decodeURIComponent(h.slice(6)));
  if (h.startsWith("#/scenarios")) return showScenarios();
  return showRuns();
}
window.addEventListener("hashchange", route);
loadInfo();
route();
let saved = "1";
try { saved = localStorage.getItem("qakit-live") ?? "1"; } catch (_) { /* 기본 켜기 */ }
setLive(saved === "1");
