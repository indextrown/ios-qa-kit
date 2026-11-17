import { useCallback, useEffect, useRef, useState } from "react";
import { Eye, EyeOff, Hand, Camera, Circle, Square as StopIcon, Keyboard, Radio, Image as ImageIcon, MousePointer2, MousePointerClick, Pause, Play, RotateCcw, ScanLine, TerminalSquare, Timer, CheckCircle2, ArrowUp, ArrowDown, Loader2, Zap, History } from "lucide-react";
import { fileUrl, get, post, screenUrl, type DoResult, type El, type Elements, type Job } from "../lib/api";
import { SaveScenario } from "../components/SaveScenario";
import { StepList } from "../components/StepList";
import { RunScenario } from "../components/RunScenario";
import { AiActivity } from "../components/AiActivity";
import { RobotCursor } from "../components/RobotCursor";
import { StreamImg } from "../components/StreamImg";
import { Sep, ToolBtn } from "../components/ToolBar";
import { cx, store, stored } from "../lib/util";
import { Badge, Button, Card, Empty, Mono, PageHeader } from "../components/ui";

// 덤프 종류 → 시나리오 대상 type
const TYPE: Record<string, string> = { Button: "button", StaticText: "text", Text: "text", Image: "image", Cell: "cell", TextField: "textfield",
  SecureTextField: "securetextfield", Switch: "switch", Other: "other", CollectionView: "collectionview", ScrollView: "scrollview", Table: "table" };
const PREFER = new Set(["Button", "Cell", "TextField", "SecureTextField", "Switch", "Link", "SegmentedControl"]);
const hasId = (e: El) => !!e.id && !e.id.startsWith("_Tt");
const yq = (v: string) => (/^[^\s"'{}[\],:#&*!|>%@`-][^{}[\],:#"]*$/.test(v) && !/\s$/.test(v) && !/: /.test(v) ? v : JSON.stringify(v));

/** 고른 요소 → 시나리오 대상: ID 우선, 없으면 종류+라벨 (같은 것이 여럿이면 index, 줄바꿈 라벨은 첫 줄 contains) */
/** 같은 줄(세로 가운데가 겹침)의 왼쪽에 있는 글자 — 안드로이드 row: 대상용 ("거리 측정" 줄의 스위치) */
function rowLabel(e: El, all: El[]) {
  const cy = e.y + e.h / 2;
  const cands = all.filter((x) => x !== e && x.type === "StaticText" && x.label && x.x + x.w <= e.x + 1
    && Math.abs(x.y + x.h / 2 - cy) <= Math.max(x.h, e.h) / 2);
  cands.sort((a, b) => (b.x + b.w) - (a.x + a.w));   // 가장 가까운 왼쪽 글자
  const label = cands[0]?.label;
  // 그 글자가 화면에 하나뿐일 때만 (row: 는 첫 번째 같은 글자를 기준으로 줄을 잡는다)
  return label && all.filter((x) => x.label === label).length === 1 ? label : null;
}

/** 단계 대상이 무엇에 기대는가 — 순서 번호(index)는 화면이 조금만 바뀌어도 다른 요소를 고른다 */
function selectorBasis(sel: string): [string, boolean] {
  if (!sel.startsWith("{")) return ["ID", false];
  const idx = /\bindex: /.test(sel);
  if (/^\{ id: /.test(sel)) return /\brow: /.test(sel) ? ["ID + 줄 글자", false] : ["ID + 순서", idx];
  if (/\bcontains: /.test(sel)) return ["포함 글자", false];
  return [idx ? "라벨 + 순서" : "라벨", idx];
}

interface Prev { name: string; count: number; first: string[] }
const SCROLLERS = new Set(["ScrollView", "CollectionView", "Table", "WebView"]);
/** 끌기 → swipe: 단계. 시작점을 품은 가장 작은 목록·스크롤 영역, 없으면 시작점을 품은 가장 큰 요소(지도 등) 위에서.
 *  dir은 손가락이 움직인 방향 (시나리오 swipe와 같음) */
function swipeStep(x: number, y: number, dx: number, dy: number, els: Elements) {
  const scr = els.screen;
  if (!scr) return null;
  const px = x * scr.w, py = y * scr.h;
  const inside = els.elements.filter((e) => px >= e.x && px <= e.x + e.w && py >= e.y && py <= e.y + e.h
    && e.w * e.h < scr.w * scr.h * 0.98);
  const scroll = inside.filter((e) => SCROLLERS.has(e.type)).sort((a, b) => a.w * a.h - b.w * b.h)[0];
  const target = scroll ?? [...inside].sort((a, b) => b.w * b.h - a.w * a.h)[0];
  if (!target) return null;
  const dir = Math.abs(dx * scr.w) > Math.abs(dy * scr.h) ? (dx > 0 ? "right" : "left") : (dy > 0 ? "down" : "up");
  return `swipe: { on: ${selectorFor(target, els.elements, els.platform === "android")}, dir: ${dir} }`;
}

function selectorFor(e: El, all: El[], android = false) {
  if (hasId(e)) {
    const dup = all.filter((x) => x.id === e.id);
    if (dup.length <= 1) return yq(e.id!);
    // 안드로이드: ID가 여럿이면(Compose 토글 목록 등) 순서 번호보다 줄 이름이 덜 깨진다 → { id, row: 줄 글자 }
    const row = android ? rowLabel(e, all) : null;
    return row ? `{ id: ${yq(e.id!)}, row: ${yq(row)} }` : `{ id: ${yq(e.id!)}, index: ${dup.indexOf(e)} }`;
  }
  const type = TYPE[e.type] ?? "any";
  const raw = e.labelRaw ?? "";
  if (raw.includes("\n")) return `{ type: ${type}, contains: ${yq(raw.split("\n")[0])} }`;
  const dup = all.filter((x) => x.labelRaw === raw && x.type === e.type);
  return `{ type: ${type}, label: ${yq(raw)}${dup.length > 1 ? `, index: ${dup.indexOf(e)}` : ""} }`;
}

export function Live({ job, refreshJob }: { job: Job | null; refreshJob: () => void }) {
  const [ai, setAi] = useState<{ busy: boolean; client?: string | null; active?: boolean }>({ busy: false });
  const onAiBusy = useCallback((b: boolean, client?: string | null, active?: boolean) =>
    setAi((p) => (p.busy === b && p.client === client && p.active === active ? p : { busy: b, client, active })), []);
  const busy = !!job?.running || ai.busy;   // 시나리오 실행 중이거나 AI가 조작 중이면 손 조작을 잠근다
  const [img, setImg] = useState<string | null>(null);
  const [shotError, setShotError] = useState<string | null>(null);
  // 화면 그림의 실제 가로·세로 (화면 구조를 아직 못 읽었을 때 방향 판단용)
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);
  const [streaming, setStreaming] = useState(() => stored("qakit-live", true));
  const [interval, setIntervalMs] = useState(() => stored("qakit-live-ms", 1000));
  const [boxes, setBoxes] = useState(() => stored("qakit-boxes", true));
  const [tab, setTab] = useState<Tab>(() => { const t = stored<string>("qakit-live-tab", "act"); return TABS.some(([id]) => id === t) ? t as Tab : "act"; });   // 오른쪽 패널 탭
  useEffect(() => store("qakit-live-tab", tab), [tab]);
  // 화면 방식: 실시간(시뮬레이터 화면을 바로 읽어 영상으로) · 스크린샷(정해진 간격으로 사진). 실시간이 안 되면 스크린샷으로
  const [mode, setMode] = useState<"stream" | "shot">(() => stored("qakit-screen-mode", "stream"));
  const [streamNote, setStreamNote] = useState<string | null>(null);
  const [fps, setFps] = useState(0);
  const [streamKey, setStreamKey] = useState(() => Date.now());
  const [els, setEls] = useState<Elements | null>(null);
  const [dumping, setDumping] = useState(false);
  const [sel, setSel] = useState<El | null>(null);
  const [hover, setHover] = useState<El | null>(null);
  const [input, setInput] = useState("");
  const [typed, setTyped] = useState("");                                           // 고른 입력칸에 칠 글자
  const [rec, setRec] = useState<{ started: number } | null>(null);                 // 녹화 중
  const [now, setNow] = useState(Date.now());
  const [capMsg, setCapMsg] = useState<string | null>(null);
  const [result, setResult] = useState<{ step: string; res?: DoResult; error?: string; running?: boolean } | null>(null);
  const [steps, setSteps] = useState<{ steps: string[]; fromLaunch: boolean; prev?: Prev[] } | null>(null);
  const [cursor, setCursor] = useState(() => stored("qakit-cursor", true));      // 손가락 커서·탭 표시
  const [clickTap, setClickTap] = useState(() => stored("qakit-click-tap", false)); // 화면을 누르면 바로 탭
  const [pt, setPt] = useState<{ x: number; y: number } | null>(null);              // 마우스 위치 (%)
  const [down, setDown] = useState(false);
  const [direct, setDirect] = useState(() => stored("qakit-direct-touch", false));   // 손 조작을 직접 터치로 (H4, 실험)
  useEffect(() => store("qakit-direct-touch", direct), [direct]);
  const press = useRef<{ x: number; y: number; t: number } | null>(null);              // 직접 터치: 누른 자리·때 (0~1)
  const overlay = useRef<HTMLDivElement>(null);
  const urlRef = useRef<string | null>(null);

  useEffect(() => { store("qakit-live", streaming); store("qakit-live-ms", interval); store("qakit-boxes", boxes); store("qakit-screen-mode", mode);
    store("qakit-cursor", cursor); store("qakit-click-tap", clickTap); }, [streaming, interval, boxes, cursor, clickTap, mode]);

  const shot = useCallback(async () => {
    try {
      const r = await fetch(screenUrl(), { cache: "no-store" });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error ?? String(r.status));
      const url = URL.createObjectURL(await r.blob());
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
      urlRef.current = url; setImg(url); setShotError(null);
    } catch (e) { setShotError((e as Error).message); }
  }, []);
  const liveOn = mode === "stream" && streaming;
  useEffect(() => {   // 스크린샷 방식 화면 갱신: 끝난 뒤 간격만큼 쉬고 다시 (겹치지 않게). 실시간이면 멈춤 때 한 장만
    if (liveOn) return;
    let alive = true, t: ReturnType<typeof setTimeout>;
    const loop = async () => { await shot(); if (alive && streaming) t = setTimeout(loop, interval); };
    loop();
    return () => { alive = false; clearTimeout(t); };
  }, [shot, streaming, interval, liveOn]);
  // 화면 구조 자동 갱신: 실시간 화면이 바뀌었다가 0.8초 멈추면(애니메이션 끝) 다시 읽는다.
  // AI 조작·시나리오 실행·직접 실행 중엔 하지 않음 (실행기를 같이 쓰면 그쪽이 늦어짐)
  const seenChange = useRef(0), serverNow = useRef(0), canAuto = useRef(false), loadElsRef = useRef<() => Promise<void>>(async () => {});
  // 화면 구조가 지금 화면 것인가 — 직접 터치 뒤·화면이 바뀐 뒤엔 다시 읽기 전까지 아님 (옛 화면 요소로 단계를 기록하지 않게)
  const elsSeq = useRef(0), elsFresh = useRef(false);
  useEffect(() => {   // 실시간: 상태(초당 장수)를 보고, 도구가 멈췄으면 스크린샷으로 돌아간다
    if (!liveOn) { setFps(0); return; }
    let alive = true, n = 0;
    const t = setInterval(async () => {
      try {
        const st = await get<{ running: boolean; error: string | null; fps: number; changedAt: number | null; now: number }>("/api/stream-status");
        if (!alive) return;
        serverNow.current = st.now;
        if (n++ % 3 === 0) setFps(st.fps);
        if (!st.running && st.error) { setMode("shot"); setStreamNote(`실시간 화면 멈춤 (${st.error}) — 스크린샷으로 봅니다`); return; }
        const c = st.changedAt ?? 0;
        if (seenChange.current && c > seenChange.current) elsFresh.current = false;
        if (!seenChange.current) seenChange.current = c;   // 열었을 때는 이미 읽음
        else if (c > seenChange.current && st.now - c >= 0.8 && canAuto.current) {
          seenChange.current = c;
          loadElsRef.current();
        }
      } catch { /* 다음에 */ }
    }, 600);
    return () => { alive = false; clearInterval(t); };
  }, [liveOn]);

  const loadEls = useCallback(async () => {
    setDumping(true);
    const seq = elsSeq.current, from = serverNow.current;
    try {
      const d = await get<Elements>("/api/elements");
      setEls(d);
      if (from) seenChange.current = Math.max(seenChange.current, from);   // 읽기 시작 전 변화는 반영됨
      elsFresh.current = seq === elsSeq.current;
      setSel((s) => (s ? d.elements.find((e) => e.id === s.id && e.labelRaw === s.labelRaw && e.type === s.type) ?? null : null));
    } catch (e) { setShotError(`화면 구조: ${(e as Error).message}`); }
    setDumping(false);
  }, []);
  const loadSteps = useCallback(() => { get<{ steps: string[]; fromLaunch: boolean; prev: Prev[] }>("/api/do-steps").then(setSteps).catch(() => {}); }, []);
  const restore = async (name: string) => {
    try { await post("/api/do-steps/restore", { name }); loadSteps(); }
    catch (e) { setCapMsg(`되살리지 못함: ${(e as Error).message}`); }
  };
  loadElsRef.current = loadEls;
  useEffect(() => { loadEls(); loadSteps(); }, [loadEls, loadSteps]);
  const wasAi = useRef(false);
  useEffect(() => {   // AI 세션이 끝나면 화면 구조·기록을 한 번 다시 읽는다 (세션 중에는 상자를 숨김)
    if (wasAi.current && !ai.active) { loadEls(); loadSteps(); }
    wasAi.current = !!ai.active;
  }, [ai.active, loadEls, loadSteps]);
  const wasBusy = useRef(false);
  const jobBusy = !!job?.running;
  const jobIsRun = jobBusy && !!job?.args && !job?.draft;
  const prevRun = useRef(jobIsRun), prevAi = useRef(!!ai.active);
  useEffect(() => {   // 시나리오 실행이 시작되면 그 탭으로, AI가 조작을 시작하면 AI 탭으로
    if (jobIsRun && !prevRun.current) setTab("run");
    prevRun.current = jobIsRun; prevAi.current = !!ai.active;
  }, [jobIsRun, ai.active]);
  useEffect(() => {   // 재생(시나리오 실행)이 끝나면 화면 구조·기록을 다시 읽는다. AI 조작 사이에는 읽지 않음 (실행기를 같이 쓰면 AI 조작이 늦어짐)
    if (wasBusy.current && !jobBusy) { loadEls(); loadSteps(); }
    wasBusy.current = jobBusy;
  }, [jobBusy, loadEls, loadSteps]);

  const doStep = async (step: string, record = true) => {
    if (!step) return;
    setResult({ step: record ? step : `${step}  (기록 안 함)`, running: true });
    try { setResult({ step, res: await post<DoResult>("/api/do", { step, record }) }); }
    catch (e) { setResult({ step, error: (e as Error).message }); }
    if (!liveOn) await shot();
    await loadEls(); loadSteps();
    seenChange.current = Math.max(seenChange.current, serverNow.current);   // 이 조작으로 바뀐 화면은 방금 읽었음
  };

  // 캡처: 사진은 지금 화면(원래 해상도)을 내 컴퓨터로, 녹화는 results/recordings/에 남기고 내려받기
  const download = (href: string, name?: string) => { const a = document.createElement("a"); a.href = href; if (name) a.download = name; document.body.appendChild(a); a.click(); a.remove(); };
  const saveShot = async () => {
    try {
      const r = await fetch(screenUrl(), { cache: "no-store" });
      if (!r.ok) throw new Error(String(r.status));
      const url = URL.createObjectURL(await r.blob());
      const ts = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
      download(url, `qakit-${ts}.jpg`); setTimeout(() => URL.revokeObjectURL(url), 5000);
      setCapMsg("사진을 내려받았습니다");
    } catch (e) { setCapMsg(`사진 저장 실패: ${(e as Error).message}`); }
  };
  useEffect(() => { if (!capMsg || rec) return; const t = setTimeout(() => setCapMsg(null), 6000); return () => clearTimeout(t); }, [capMsg, rec]);
  useEffect(() => { setTyped(""); }, [sel]);
  useEffect(() => { get<{ recording: boolean; started: number | null }>("/api/record").then((r) => setRec(r.recording && r.started ? { started: r.started } : null)).catch(() => {}); }, []);
  useEffect(() => { if (!rec) return; const t = setInterval(() => setNow(Date.now()), 500); return () => clearInterval(t); }, [rec]);
  const toggleRec = async () => {
    try {
      if (!rec) { const r = await post<{ started: number }>("/api/record/start"); setRec({ started: r.started }); setCapMsg("녹화 중 — 다시 누르면 멈추고 내려받습니다"); return; }
      setCapMsg("녹화 마무리 중…");
      const r = await post<{ dir: string; name: string; bytes: number }>("/api/record/stop");
      setRec(null);
      download(`${fileUrl(r.dir, r.name)}&download=1`);
      setCapMsg(`녹화 저장: results/${r.dir}/${r.name} (${(r.bytes / 1e6).toFixed(1)}MB)`);
    } catch (e) { setRec(null); setCapMsg(`녹화 실패: ${(e as Error).message}`); }
  };

  const hit = (ev: React.MouseEvent) => {
    const scr = els?.screen;
    if (!scr || !overlay.current) return null;
    const r = overlay.current.getBoundingClientRect();
    const x = ((ev.clientX - r.left) / r.width) * scr.w, y = ((ev.clientY - r.top) / r.height) * scr.h;
    const inside = els.elements.filter((e) => x >= e.x && x <= e.x + e.w && y >= e.y && y <= e.y + e.h);
    const pick = inside.some((e) => PREFER.has(e.type)) ? inside.filter((e) => PREFER.has(e.type)) : inside;
    return [...pick].sort((a, b) => a.w * a.h - b.w * b.h || b.depth - a.depth)[0] ?? null;
  };
  const pos = (ev: React.MouseEvent) => {
    const r = overlay.current!.getBoundingClientRect();
    return { x: ((ev.clientX - r.left) / r.width) * 100, y: ((ev.clientY - r.top) / r.height) * 100 };
  };
  const frac = (ev: React.MouseEvent) => {
    const r = overlay.current!.getBoundingClientRect();
    return { x: Math.min(Math.max((ev.clientX - r.left) / r.width, 0), 1), y: Math.min(Math.max((ev.clientY - r.top) / r.height, 0), 1) };
  };
  /** 직접 터치 (실험): 마우스를 뗄 때 — 거의 안 움직였으면 탭(0.5초 넘게 누르면 길게 누르기), 움직였으면 그 길로 끌기.
   *  탭이 요소 위면 그 단계로 기록 (시나리오로 옮길 수 있게, 재생은 XCUITest) */
  const directRelease = async (ev: React.MouseEvent) => {
    const p = press.current; press.current = null;
    if (!p || working || !overlay.current) return;
    const q = frac(ev), held = (Date.now() - p.t) / 1000;
    const moved = Math.hypot(q.x - p.x, (q.y - p.y) * ((scr?.h ?? 2) / (scr?.w ?? 1))) > 0.03;
    const h = hit(ev);
    const fresh = !!els && elsFresh.current;
    const sel_ = h && fresh ? selectorFor(h, els!.elements, els!.platform === "android") : null;
    const step = !moved && sel_ ? (held < 0.5 ? `tap: ${sel_}` : `long-press: { on: ${sel_}, seconds: ${Math.min(held, 5).toFixed(1)} }`)
      : moved && fresh && clickTap ? swipeStep(p.x, p.y, q.x - p.x, q.y - p.y, els!) : null;   // 끌기는 기록 모드일 때만 단계로
    elsSeq.current++; elsFresh.current = false;
    const body = moved ? { kind: "swipe", x: p.x, y: p.y, x2: q.x, y2: q.y, seconds: Math.min(Math.max(held, 0.15), 2), step }
      : held >= 0.5 ? { kind: "press", x: p.x, y: p.y, seconds: Math.min(held, 5), step } : { kind: "tap", x: p.x, y: p.y, step };
    const label = `직접 터치 · ${moved ? "끌기" : held >= 0.5 ? `길게 누르기 ${held.toFixed(1)}초` : "탭"} @${(p.x * 100).toFixed(0)}%,${(p.y * 100).toFixed(0)}%${step ? ` → ${step}` : ""}`;
    if (h && !moved) setSel(h);
    setResult({ step: label, running: true });
    try {
      const r = await post<{ ms: number; reply: string; recorded: boolean }>("/api/touch", body);
      setResult({ step: label, res: { code: 0, output: `✅ ${r.ms}ms${r.recorded ? " · 단계 기록" : moved && !clickTap ? " · 기록 안 함 (끌기는 기록 모드에서 swipe로)" : " · 기록 안 함 (요소 위가 아니거나 화면 구조를 다시 읽기 전)"}` } });
    } catch (e) { setResult({ step: label, error: (e as Error).message }); }
    if (!liveOn) await shot();
    loadSteps();
    setTimeout(() => { if (!elsFresh.current) loadElsRef.current(); }, 1200);   // 화면이 안 바뀌는 터치여도 다시 읽어 둔다
  };
  const scr = els?.screen;
  // 가로 화면(안드로이드 태블릿·가로 고정 앱, 아이패드 가로): 화면 구조의 크기, 없으면 받은 그림 크기로 판단
  const landscape = scr ? scr.w > scr.h : natural ? natural.w > natural.h : false;
  const onImgLoad = (e: React.SyntheticEvent<HTMLImageElement>) => {
    const { naturalWidth: w, naturalHeight: h } = e.currentTarget;
    if (w && h && (!natural || (natural.w > natural.h) !== (w > h))) setNatural({ w, h });
  };
  const selector = sel && els ? selectorFor(sel, els.elements, els.platform === "android") : null;
  const basis = selector ? selectorBasis(selector) : null;
  const working = !!result?.running || busy;
  canAuto.current = !working && !dumping && !ai.active;
  const isInput = !!sel && ["TextField", "SecureTextField", "SearchField", "TextView"].includes(sel.type);
  const actions: [string, string, typeof Hand][] = selector ? [
    ["탭", `tap: ${selector}`, Hand], ["나타날 때까지", `wait: { for: ${selector}, timeout: 10 }`, Timer],
    ["보이는지 확인", `expect: { visible: ${selector} }`, CheckCircle2], ["위로 쓸기", `swipe: { on: ${selector}, dir: up }`, ArrowUp],
    ["아래로 쓸기", `swipe: { on: ${selector}, dir: down }`, ArrowDown]] : [];

  const recSecs = rec ? Math.max(0, Math.floor(now / 1000 - rec.started)) : 0;
  const lock = ai.busy ? `AI(${ai.client ?? "MCP"}) 조작 중 — 조작 잠김` : busy ? "시나리오 실행 중 — 조작 잠김" : null;
  const notice = capMsg ?? streamNote ?? shotError;

  return (
    <>
      <PageHeader title="라이브 세션" description="화면을 눌러 요소를 고르고 실행합니다 (ID 우선, 없으면 라벨). 통과한 단계는 기록돼 시나리오로 저장할 수 있습니다. 기록 모드(도구 막대)를 켜면 누르는 대로 바로 탭·기록됩니다." />
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_400px]">
        <div className="flex items-start justify-center gap-4">
          {/* 세로 도구 막대 */}
          <div className="sticky top-4 z-30 flex flex-col gap-0.5 rounded-xl bg-card p-1 ring-1 ring-line">
            <ToolBtn label={streaming ? "화면 갱신 멈춤" : "화면 갱신 다시"} onClick={() => setStreaming(!streaming)}>
              {streaming ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}</ToolBtn>
            <ToolBtn label={mode === "stream" ? "실시간 → 스크린샷으로" : "스크린샷 → 실시간으로"} active={mode === "stream"}
              onClick={() => { setStreamNote(null); setStreamKey(Date.now()); setMode(mode === "stream" ? "shot" : "stream"); }}>
              {mode === "stream" ? <Radio className="h-4 w-4" /> : <ImageIcon className="h-4 w-4" />}</ToolBtn>
            <Sep />
            <ToolBtn label="앱 다시 켜기" onClick={() => doStep("launch")} disabled={working}><RotateCcw className="h-4 w-4" /></ToolBtn>
            <ToolBtn label="화면 구조 다시 읽기" onClick={loadEls} disabled={dumping}>
              {dumping ? <Loader2 className="h-4 w-4 animate-spin" /> : <ScanLine className="h-4 w-4" />}</ToolBtn>
            <ToolBtn label={boxes ? "요소 상자 숨기기" : "요소 상자 보이기"} active={boxes} onClick={() => setBoxes(!boxes)}>
              {boxes ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}</ToolBtn>
            <Sep />
            <ToolBtn label={`커서 ${cursor ? "끄기" : "켜기"} — 누르는 자리 보기`} active={cursor} onClick={() => setCursor(!cursor)}><MousePointer2 className="h-4 w-4" /></ToolBtn>
            <ToolBtn label={`기록 모드 ${clickTap ? "끄기" : "켜기"} — 누르면 바로 탭하고 단계로 기록 (직접 터치면 끌기도 swipe로)`} active={clickTap} danger={clickTap}
              onClick={() => setClickTap(!clickTap)}><MousePointerClick className="h-4 w-4" /></ToolBtn>
            <ToolBtn label={`직접 터치 ${direct ? "끄기" : "켜기"} (실험) — 손가락처럼 바로: 클릭=탭, 꾹=길게, 끌기=끌기`} active={direct} onClick={() => setDirect(!direct)}><Zap className="h-4 w-4" /></ToolBtn>
            <Sep />
            <ToolBtn label="사진 내려받기" onClick={saveShot}><Camera className="h-4 w-4" /></ToolBtn>
            <ToolBtn label={rec ? "녹화 멈추고 내려받기" : "녹화 시작"} onClick={toggleRec} danger={!!rec}>
              {rec ? <StopIcon className="h-4 w-4 fill-current" /> : <Circle className="h-4 w-4" />}</ToolBtn>
          </div>

          {/* 기기 */}
          <div className={cx("relative w-full bg-neutral-900 shadow-[0_24px_60px_-20px_rgba(0,0,0,0.45)] ring-1 ring-black/50 dark:ring-white/15",
            landscape ? "max-w-[880px] rounded-[30px] p-[9px]" : "max-w-[360px] rounded-[48px] p-[11px]")}>
            <div className={cx("relative overflow-hidden bg-black", landscape ? "rounded-[22px]" : "rounded-[38px]")}>
              {liveOn ? <StreamImg key={streamKey} src={`/api/stream?k=${streamKey}`} alt="시뮬레이터 화면 (실시간)" className="block w-full select-none" draggable={false}
                  onLoad={onImgLoad}
                  style={{ aspectRatio: scr ? `${scr.w} / ${scr.h}` : natural ? `${natural.w} / ${natural.h}` : "9 / 19.5" }}
                  onError={() => { setMode("shot"); setStreamNote("실시간 화면을 열지 못했습니다 — 스크린샷으로 봅니다"); }} />
                : img ? <img src={img} alt="시뮬레이터 화면" className="block w-full select-none" draggable={false} onLoad={onImgLoad} />
                : <div className={cx("flex items-center justify-center text-[13px] text-neutral-400", landscape ? "aspect-[16/10]" : "aspect-[9/19.5]")}>{shotError ?? "화면 불러오는 중…"}</div>}
              {(img || liveOn) && scr && (
                <div ref={overlay} className={cx("absolute inset-0", cursor ? "cursor-none" : "cursor-crosshair")}
                  onMouseMove={(e) => { setHover(hit(e)); setPt(pos(e)); }} onMouseLeave={() => { setHover(null); setPt(null); setDown(false); press.current = null; }}
                  onMouseDown={(e) => { setDown(true); if (direct && e.button === 0) press.current = { ...frac(e), t: Date.now() }; }}
                  onMouseUp={(e) => { setDown(false); if (direct) directRelease(e); }}
                  onClick={(e) => {
                    if (direct) return;   // 직접 터치는 onMouseUp에서
                    const h = hit(e);
                    if (!h) return;
                    setSel(h); setTab("act");
                    if (clickTap && !working && els) doStep(`tap: ${selectorFor(h, els.elements, els.platform === "android")}`);
                  }}>
                  {(ai.active ? [] : els?.elements ?? []).filter((e) => boxes || e === sel || e === hover).map((e, i) => (
                    <div key={i} className={cx("pointer-events-none absolute rounded-[3px] border",
                      e === sel ? "border-2 border-rose-500 bg-rose-500/15" : e === hover ? "border-sky-400 bg-sky-400/15"
                        : hasId(e) ? "border-sky-400/50" : "border-dashed border-amber-400/50")}
                      style={{ left: `${(e.x / scr.w) * 100}%`, top: `${(e.y / scr.h) * 100}%`, width: `${(e.w / scr.w) * 100}%`, height: `${(e.h / scr.h) * 100}%` }} />
                  ))}
                  {cursor && pt && (   // 손가락 커서
                    <div className={cx("pointer-events-none absolute h-9 w-9 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white/90 bg-neutral-900/30 shadow-[0_0_0_1px_rgba(0,0,0,0.35)] transition-transform duration-75",
                      down && "scale-75 bg-neutral-900/50")} style={{ left: `${pt.x}%`, top: `${pt.y}%` }} />)}
                </div>
              )}
              {/* 실행기가 누르는 자리 (라이브 조작·qakit do·시나리오 실행·AI) — 화면 구조와 상관없이 (시나리오 실행 중엔 화면 구조를 못 읽음) */}
              {(img || liveOn) && <RobotCursor enabled={cursor} size="h-7 w-7" />}
            </div>
          </div>

          {/* 상태 카드 */}
          <div className="sticky top-4 hidden w-52 shrink-0 space-y-2 2xl:block">
            <div className="space-y-2 rounded-xl bg-card p-3 text-[12px] ring-1 ring-line">
              <div className="flex items-center gap-1.5">
                <span className={cx("h-2 w-2 rounded-full", !streaming ? "bg-sub" : liveOn ? "bg-ok" : "bg-warn")} />
                <span className="font-medium">{!streaming ? "멈춤" : liveOn ? "실시간" : "스크린샷"}</span>
                {liveOn && <span className="font-mono text-sub" title="화면이 바뀔 때만 보냅니다">{fps} fps</span>}
                {mode === "shot" && (
                  <select value={interval} onChange={(e) => setIntervalMs(Number(e.target.value))} className="ml-auto rounded bg-muted px-1 text-[11px] outline-none">
                    {[500, 1000, 2000, 5000].map((v) => <option key={v} value={v}>{v / 1000}초</option>)}
                  </select>)}
              </div>
              <div className="text-sub">{els ? `요소 ${els.elements.length}개` : "화면 구조 없음"}{boxes ? "" : " · 상자 숨김"}</div>
              {cursor && <div className="text-sub">커서 켬</div>}
              {clickTap && <div className="flex items-center gap-1.5 font-medium text-bad"><span className="h-2 w-2 rounded-full bg-bad" />기록 모드 — 누르면 탭·기록</div>}
              {direct && <div className="text-warn">직접 터치 (실험) — 클릭=탭 · 꾹=길게 · 끌기</div>}
              {rec && <div className="flex items-center gap-1.5 font-medium text-bad"><span className="h-2 w-2 animate-pulse rounded-full bg-bad" />녹화 {recSecs}s</div>}
            </div>
            {lock && <div className="rounded-xl bg-warn/10 p-3 text-[12px] text-warn ring-1 ring-warn/30">{lock}</div>}
            {hover && <div className="rounded-xl bg-card p-3 text-[12px] ring-1 ring-line">
              <div className="text-sub">마우스 아래</div>
              <div className="mt-0.5 break-all font-mono text-[11.5px]">{hover.type}{hasId(hover) ? ` #${hover.id}` : ""}</div>
              {hover.label && <div className="mt-0.5 truncate">"{hover.label}"</div>}
            </div>}
            {notice && <div className="max-h-48 overflow-auto whitespace-pre-wrap rounded-xl bg-card p-3 text-[12px] text-sub ring-1 ring-line [overflow-wrap:anywhere]">{notice}</div>}
          </div>
        </div>

        {/* 오른쪽 패널: 탭 (모두 그려 두고 숨기기만 — 탭을 바꿔도 입력·로그 그대로) */}
        <div className="min-w-0 space-y-3">
          <div className="grid grid-cols-3 gap-0.5 rounded-lg bg-muted p-0.5 text-[12.5px]">
            {TABS.map(([id, label]) => (
              <button key={id} onClick={() => setTab(id)}
                className={cx("relative rounded-md py-1.5", tab === id ? "bg-card font-medium text-fg shadow-[0_1px_2px_rgba(0,0,0,0.06)] ring-1 ring-line" : "text-sub hover:text-fg")}>
                {label}
                {id === "run" && busy && !ai.busy && <span className="absolute right-2 top-2 h-1.5 w-1.5 rounded-full bg-ok" />}
                {id === "save" && (steps?.steps.length ?? 0) > 0 && <span className="ml-1 text-[11px] text-sub">{steps!.steps.length}</span>}
              </button>
            ))}
          </div>
          {lock && <div className="rounded-lg bg-warn/10 px-3 py-2 text-[12px] text-warn ring-1 ring-warn/30 2xl:hidden">{lock}</div>}

          <div className={cx("space-y-3", tab !== "act" && "hidden")}>
            <Card title="고른 요소">
              {!sel ? <Empty>화면을 눌러 요소를 고르세요</Empty> : (
                <div className="space-y-3 p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge>{sel.type}</Badge>{hasId(sel) ? <Mono>#{sel.id}</Mono> : <Badge tone="warn">ID 없음 — 라벨로</Badge>}
                  </div>
                  {sel.label && <div className="text-[13px]">"{sel.label}"</div>}
                  <div className="font-mono text-[11px] text-sub">@{sel.x},{sel.y} {sel.w}×{sel.h}</div>
                  <div className="rounded-md bg-muted px-2.5 py-2">
                    <div className="mb-0.5 flex items-center justify-between text-[11px] text-sub">단계 대상
                      {basis && <Badge tone={basis[1] ? "warn" : "muted"}>{basis[0]}{basis[1] ? " — 화면이 바뀌면 깨지기 쉬움" : ""}</Badge>}</div>
                    <Mono className="break-all">{selector}</Mono></div>
                  {isInput && (
                    <form className="space-y-1.5" onSubmit={(e) => { e.preventDefault(); if (typed) doStep(`type: { into: ${selector}, text: ${JSON.stringify(typed)} }`); }}>
                      <div className="flex gap-1.5">
                        <input value={typed} onChange={(e) => setTyped(e.target.value)} type="text"
                          placeholder={sel.type === "SecureTextField" ? "{secret:PASSWORD} (secrets.txt 키)" : "칠 글자"}
                          className="h-8 min-w-0 flex-1 rounded-md bg-muted px-2.5 text-[12px] outline-none placeholder:text-sub" />
                        <Button type="submit" size="sm" variant="primary" disabled={working || !typed}><Keyboard className="h-3.5 w-3.5" />입력</Button>
                      </div>
                      {sel.type === "SecureTextField" && typed && !/^\{secret:[A-Za-z0-9_-]+\}$/.test(typed) &&
                        <div className="text-[11px] text-warn">비밀번호가 기록·시나리오에 그대로 남습니다 — <Mono>{"{secret:키}"}</Mono>로 쓰세요</div>}
                    </form>
                  )}
                  <div className="grid grid-cols-2 gap-1.5">
                    {actions.map(([label, step, Icon], i) => (
                      <Button key={label} variant={i === 0 ? "primary" : "secondary"} size="sm" disabled={working} onClick={() => doStep(step)}
                        className={i === 0 ? "col-span-2" : ""}><Icon className="h-3.5 w-3.5" />{label}</Button>
                    ))}
                  </div>
                </div>
              )}
            </Card>
            {clickTap && (
              <Card title={<span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-bad" />기록 중인 단계</span>}
                actions={<button className="text-[11px] text-link hover:underline" onClick={() => setTab("save")}>저장하러 가기</button>}>
                <StepList compact steps={steps?.steps ?? []} disabled={working}
                  onChange={(s) => setSteps((p) => ({ steps: s, fromLaunch: p?.fromLaunch ?? false }))} onRun={(s) => doStep(s, false)} />
              </Card>
            )}
            <Card title={<span className="flex items-center gap-1.5"><TerminalSquare className="h-3.5 w-3.5" />단계 직접 실행</span>}>
              <form className="flex gap-2 p-4" onSubmit={(e) => { e.preventDefault(); doStep(input.trim()); }}>
                <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="tap: home_search_button"
                  className="h-8 min-w-0 flex-1 rounded-md bg-muted px-2.5 font-mono text-[12px] outline-none placeholder:text-sub" />
                <Button type="submit" disabled={working || !input.trim()}>실행</Button>
              </form>
              {result && (
                <div className="border-t border-line px-4 py-3 text-[12px]">
                  <Mono className="block break-all text-sub">{result.step}</Mono>
                  {result.running ? <span className="mt-1 flex items-center gap-1.5 text-sub"><Loader2 className="h-3.5 w-3.5 animate-spin" />실행 중…</span>
                    : <pre className={cx("mt-1 whitespace-pre-wrap font-mono", result.res?.code === 0 ? "text-ok" : "text-bad")}>{result.error ?? result.res?.output.trim()}</pre>}
                </div>
              )}
            </Card>
          </div>
          <div className={cx(tab !== "run" && "hidden")}><RunScenario job={job} refreshJob={refreshJob} /></div>
          <div className={cx("space-y-3", tab !== "save" && "hidden")}>
            <Card title="기록된 단계" actions={steps && <span className="text-[11px] text-sub">{steps.fromLaunch ? "앱을 다시 켠 뒤부터" : steps.steps.length ? "다시 켜기 전 것 포함" : ""}</span>}>
              <StepList steps={steps?.steps ?? []} disabled={working}
                onChange={(s) => setSteps((p) => ({ steps: s, fromLaunch: p?.fromLaunch ?? false }))} onRun={(s) => doStep(s, false)} />
            </Card>
            <SaveScenario job={job} refreshJob={refreshJob} stepsCount={steps?.steps.length ?? 0} />
            {(steps?.prev?.length ?? 0) > 0 && (
              <Card title={<span className="flex items-center gap-1.5"><History className="h-3.5 w-3.5" />이전 기록 {steps!.prev!.length}</span>}
                actions={<span className="text-[11px] text-sub">앱을 다시 켜며 비운 기록</span>}>
                <div className="divide-y divide-line">
                  {steps!.prev!.map((p) => (
                    <div key={p.name} className="flex items-start gap-2 px-4 py-2 text-[12px]">
                      <div className="min-w-0 flex-1">
                        <div><span className="font-mono text-sub">{p.name.slice(5, 16).replace("_", " ").replace(/-(\d\d)-(\d\d)$/, ":$1:$2")}</span> · 단계 {p.count}개</div>
                        <div className="truncate font-mono text-[11px] text-sub" title={p.first.join("\n")}>{p.first.join(" → ")}</div>
                      </div>
                      <Button size="sm" variant="secondary" disabled={working}
                        title="이 기록을 지금 기록으로 (지금 기록은 이전 기록으로 남김)"
                        onClick={() => restore(p.name)}>되살리기</Button>
                    </div>
                  ))}
                </div>
              </Card>
            )}
          </div>
          {/* AI가 조작하는 동안만 보인다 (늘 붙여 둬야 조작 잠금이 동작) — 말로 시키는 곳은 AI 화면 */}
          <div className={cx("space-y-1", !ai.active && "hidden")}>
            <AiActivity onBusy={onAiBusy} />
            <div className="px-1 text-[12px] text-sub">AI가 조작 중입니다 — 대화는 <a href="#/ai" className="text-link hover:underline">AI</a> 화면에서</div>
          </div>
        </div>
      </div>
    </>
  );
}

const TABS = [["act", "조작"], ["run", "시나리오 실행"], ["save", "저장"]] as const;
type Tab = (typeof TABS)[number][0];
