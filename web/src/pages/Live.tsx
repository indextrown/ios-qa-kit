import { useCallback, useEffect, useRef, useState } from "react";
import { Eye, EyeOff, Hand, MousePointer2, MousePointerClick, Pause, Play, RotateCcw, ScanLine, TerminalSquare, Timer, CheckCircle2, ArrowUp, ArrowDown, Loader2 } from "lucide-react";
import { get, post, screenUrl, type DoResult, type El, type Elements, type Job } from "../lib/api";
import { SaveScenario } from "../components/SaveScenario";
import { RunScenario } from "../components/RunScenario";
import { cx, store, stored } from "../lib/util";
import { Badge, Button, Card, Empty, Mono, PageHeader } from "../components/ui";

// 덤프 종류 → 시나리오 대상 type
const TYPE: Record<string, string> = { Button: "button", StaticText: "text", Text: "text", Image: "image", Cell: "cell", TextField: "textfield",
  SecureTextField: "securetextfield", Switch: "switch", Other: "other", CollectionView: "collectionview", ScrollView: "scrollview", Table: "table" };
const PREFER = new Set(["Button", "Cell", "TextField", "SecureTextField", "Switch", "Link", "SegmentedControl"]);
const hasId = (e: El) => !!e.id && !e.id.startsWith("_Tt");
const yq = (v: string) => (/^[^\s"'{}[\],:#&*!|>%@`-][^{}[\],:#"]*$/.test(v) && !/\s$/.test(v) && !/: /.test(v) ? v : JSON.stringify(v));

/** 고른 요소 → 시나리오 대상: ID 우선, 없으면 종류+라벨 (같은 것이 여럿이면 index, 줄바꿈 라벨은 첫 줄 contains) */
function selectorFor(e: El, all: El[]) {
  if (hasId(e)) {
    const dup = all.filter((x) => x.id === e.id);
    return dup.length > 1 ? `{ id: ${yq(e.id!)}, index: ${dup.indexOf(e)} }` : yq(e.id!);
  }
  const type = TYPE[e.type] ?? "any";
  const raw = e.labelRaw ?? "";
  if (raw.includes("\n")) return `{ type: ${type}, contains: ${yq(raw.split("\n")[0])} }`;
  const dup = all.filter((x) => x.labelRaw === raw && x.type === e.type);
  return `{ type: ${type}, label: ${yq(raw)}${dup.length > 1 ? `, index: ${dup.indexOf(e)}` : ""} }`;
}

export function Live({ job, refreshJob }: { job: Job | null; refreshJob: () => void }) {
  const busy = !!job?.running;
  const [img, setImg] = useState<string | null>(null);
  const [shotError, setShotError] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(() => stored("qakit-live", true));
  const [interval, setIntervalMs] = useState(() => stored("qakit-live-ms", 1000));
  const [boxes, setBoxes] = useState(() => stored("qakit-boxes", true));
  const [els, setEls] = useState<Elements | null>(null);
  const [dumping, setDumping] = useState(false);
  const [sel, setSel] = useState<El | null>(null);
  const [hover, setHover] = useState<El | null>(null);
  const [input, setInput] = useState("");
  const [result, setResult] = useState<{ step: string; res?: DoResult; error?: string; running?: boolean } | null>(null);
  const [steps, setSteps] = useState<{ steps: string[]; fromLaunch: boolean } | null>(null);
  const [cursor, setCursor] = useState(() => stored("qakit-cursor", true));      // 손가락 커서·탭 표시
  const [clickTap, setClickTap] = useState(() => stored("qakit-click-tap", false)); // 화면을 누르면 바로 탭
  const [pt, setPt] = useState<{ x: number; y: number } | null>(null);              // 마우스 위치 (%)
  const [down, setDown] = useState(false);
  const [taps, setTaps] = useState<{ x: number; y: number; k: number }[]>([]);       // 탭한 자리 (%)
  const [lastTap, setLastTap] = useState<{ x: number; y: number; k: number } | null>(null);
  const overlay = useRef<HTMLDivElement>(null);
  const urlRef = useRef<string | null>(null);

  useEffect(() => { store("qakit-live", streaming); store("qakit-live-ms", interval); store("qakit-boxes", boxes);
    store("qakit-cursor", cursor); store("qakit-click-tap", clickTap); }, [streaming, interval, boxes, cursor, clickTap]);
  useEffect(() => {   // 마지막 탭 자리는 몇 초 뒤 지운다
    if (!lastTap) return;
    const t = setTimeout(() => setLastTap(null), 4000);
    return () => clearTimeout(t);
  }, [lastTap]);

  const shot = useCallback(async () => {
    try {
      const r = await fetch(screenUrl(), { cache: "no-store" });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error ?? String(r.status));
      const url = URL.createObjectURL(await r.blob());
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
      urlRef.current = url; setImg(url); setShotError(null);
    } catch (e) { setShotError((e as Error).message); }
  }, []);
  useEffect(() => {   // 화면 갱신: 끝난 뒤 간격만큼 쉬고 다시 (겹치지 않게)
    let alive = true, t: ReturnType<typeof setTimeout>;
    const loop = async () => { await shot(); if (alive && streaming) t = setTimeout(loop, interval); };
    loop();
    return () => { alive = false; clearTimeout(t); };
  }, [shot, streaming, interval]);

  const loadEls = useCallback(async () => {
    setDumping(true);
    try {
      const d = await get<Elements>("/api/elements");
      setEls(d);
      setSel((s) => (s ? d.elements.find((e) => e.id === s.id && e.labelRaw === s.labelRaw && e.type === s.type) ?? null : null));
    } catch (e) { setShotError(`화면 구조: ${(e as Error).message}`); }
    setDumping(false);
  }, []);
  const loadSteps = useCallback(() => { get<{ steps: string[]; fromLaunch: boolean }>("/api/do-steps").then(setSteps).catch(() => {}); }, []);
  useEffect(() => { loadEls(); loadSteps(); }, [loadEls, loadSteps]);
  const wasBusy = useRef(false);
  useEffect(() => {   // 재생(시나리오 실행)이 끝나면 화면 구조·기록을 다시 읽는다
    if (wasBusy.current && !busy) { loadEls(); loadSteps(); }
    wasBusy.current = busy;
  }, [busy, loadEls, loadSteps]);

  /** 탭 단계면 누를 자리(요소 가운데)를 표시. 직접 입력한 단계는 ID·라벨이 맞는 요소를 찾아본다 */
  const markTap = (step: string, target?: El | null) => {
    const scr = els?.screen;
    if (!cursor || !scr || !/^tap\s*:/.test(step)) return;
    let e = target ?? null;
    if (!e && els) {
      const v = step.replace(/^tap\s*:\s*/, "").trim().replace(/^["']|["']$/g, "");
      e = els.elements.find((x) => x.id === v) ?? els.elements.find((x) => x.labelRaw === v || x.label === v) ?? null;
    }
    if (!e) return;
    const p = { x: ((e.x + e.w / 2) / scr.w) * 100, y: ((e.y + e.h / 2) / scr.h) * 100, k: Date.now() };
    setTaps((t) => [...t, p]); setLastTap(p);
    setTimeout(() => setTaps((t) => t.filter((q) => q.k !== p.k)), 800);
  };
  const doStep = async (step: string, target?: El | null) => {
    if (!step) return;
    markTap(step, target);
    setResult({ step, running: true });
    try { setResult({ step, res: await post<DoResult>("/api/do", { step }) }); }
    catch (e) { setResult({ step, error: (e as Error).message }); }
    await shot(); await loadEls(); loadSteps();
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
  const scr = els?.screen;
  const selector = sel && els ? selectorFor(sel, els.elements) : null;
  const working = !!result?.running || busy;
  const actions: [string, string, typeof Hand][] = selector ? [
    ["탭", `tap: ${selector}`, Hand], ["나타날 때까지", `wait: { for: ${selector}, timeout: 10 }`, Timer],
    ["보이는지 확인", `expect: { visible: ${selector} }`, CheckCircle2], ["위로 쓸기", `swipe: { on: ${selector}, dir: up }`, ArrowUp],
    ["아래로 쓸기", `swipe: { on: ${selector}, dir: down }`, ArrowDown]] : [];

  return (
    <>
      <PageHeader title="라이브 세션" description="화면을 눌러 요소를 고르고 실행합니다 ('누르면 탭'을 켜면 바로 탭) (qakit do — ID 우선, 없으면 라벨). 통과한 단계는 기록됩니다."
        actions={busy && <Badge tone="warn">시나리오 실행 중 — 조작 잠김</Badge>} />
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="flex flex-col items-center">
          <div className="mb-3 flex flex-wrap items-center gap-1 rounded-lg bg-card p-1 shadow-e1">
            <Button size="sm" variant="ghost" onClick={() => setStreaming(!streaming)} title="화면 갱신">
              {streaming ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}{streaming ? "일시정지" : "재생"}</Button>
            <select value={interval} onChange={(e) => setIntervalMs(Number(e.target.value))} className="h-7 rounded-md bg-transparent px-1.5 text-[12px] text-sub outline-none hover:bg-muted">
              {[500, 1000, 2000, 5000].map((v) => <option key={v} value={v}>{v / 1000}초</option>)}
            </select>
            <span className="mx-1 h-4 w-px bg-line" />
            <Button size="sm" variant="ghost" onClick={() => doStep("launch")} disabled={working}><RotateCcw className="h-3.5 w-3.5" />앱 다시 켜기</Button>
            <Button size="sm" variant="ghost" onClick={loadEls} loading={dumping}><ScanLine className="h-3.5 w-3.5" />화면 구조</Button>
            <Button size="sm" variant="ghost" onClick={() => setBoxes(!boxes)}>{boxes ? <Eye className="h-3.5 w-3.5" /> : <EyeOff className="h-3.5 w-3.5" />}요소</Button>
            <Button size="sm" variant="ghost" onClick={() => setCursor(!cursor)} title="손가락 커서와 탭한 자리 표시"
              className={cx(!cursor && "text-sub")}><MousePointer2 className="h-3.5 w-3.5" />커서 {cursor ? "켬" : "끔"}</Button>
            <Button size="sm" variant="ghost" onClick={() => setClickTap(!clickTap)} title="켜면 화면을 누르는 즉시 그 요소를 탭합니다 (끄면 고르기만)"
              className={cx(clickTap ? "bg-muted font-medium" : "text-sub")}><MousePointerClick className="h-3.5 w-3.5" />누르면 탭 {clickTap ? "켬" : "끔"}</Button>
          </div>
          <div className="relative w-full max-w-[380px] rounded-[44px] bg-neutral-900 p-3 shadow-e3 ring-1 ring-black/40">
            <div className="relative overflow-hidden rounded-[34px] bg-black">
              {img ? <img src={img} alt="시뮬레이터 화면" className="block w-full select-none" draggable={false} />
                : <div className="flex aspect-[9/19.5] items-center justify-center text-[13px] text-neutral-400">{shotError ?? "화면 불러오는 중…"}</div>}
              {img && scr && (
                <div ref={overlay} className={cx("absolute inset-0", cursor ? "cursor-none" : "cursor-crosshair")}
                  onMouseMove={(e) => { setHover(hit(e)); setPt(pos(e)); }} onMouseLeave={() => { setHover(null); setPt(null); setDown(false); }}
                  onMouseDown={() => setDown(true)} onMouseUp={() => setDown(false)}
                  onClick={(e) => {
                    const h = hit(e);
                    if (!h) return;
                    setSel(h);
                    if (clickTap && !working && els) doStep(`tap: ${selectorFor(h, els.elements)}`, h);
                  }}>
                  {(els?.elements ?? []).filter((e) => boxes || e === sel || e === hover).map((e, i) => (
                    <div key={i} className={cx("pointer-events-none absolute rounded-[3px] border",
                      e === sel ? "border-2 border-rose-500 bg-rose-500/15" : e === hover ? "border-sky-400 bg-sky-400/15"
                        : hasId(e) ? "border-sky-400/50" : "border-dashed border-amber-400/50")}
                      style={{ left: `${(e.x / scr.w) * 100}%`, top: `${(e.y / scr.h) * 100}%`, width: `${(e.w / scr.w) * 100}%`, height: `${(e.h / scr.h) * 100}%` }} />
                  ))}
                  {cursor && lastTap && (   // 마지막으로 탭한 자리
                    <div className="pointer-events-none absolute h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-rose-500 ring-2 ring-white/80"
                      style={{ left: `${lastTap.x}%`, top: `${lastTap.y}%` }} />)}
                  {cursor && taps.map((t) => (
                    <div key={t.k} className="qakit-ripple pointer-events-none absolute h-10 w-10 rounded-full border-2 border-rose-500 bg-rose-500/25"
                      style={{ left: `${t.x}%`, top: `${t.y}%` }} />))}
                  {cursor && pt && (   // 손가락 커서
                    <div className={cx("pointer-events-none absolute h-9 w-9 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white/90 bg-neutral-900/30 shadow-[0_0_0_1px_rgba(0,0,0,0.35)] transition-transform duration-75",
                      down && "scale-75 bg-neutral-900/50")} style={{ left: `${pt.x}%`, top: `${pt.y}%` }} />)}
                </div>
              )}
            </div>
          </div>
          <p className="mt-2 h-4 text-[12px] text-sub">
            {hover ? <span className="font-mono">{hover.type} {hasId(hover) ? `#${hover.id}` : ""} {hover.label ? `"${hover.label}"` : ""}</span>
              : shotError ? shotError : els ? `요소 ${els.elements.length}개` : ""}</p>
        </div>

        <div className="space-y-4">
          <RunScenario job={job} refreshJob={refreshJob} />
          <Card title="고른 요소">
            {!sel ? <Empty>화면을 눌러 요소를 고르세요</Empty> : (
              <div className="space-y-3 p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge>{sel.type}</Badge>{hasId(sel) ? <Mono>#{sel.id}</Mono> : <Badge tone="warn">ID 없음 — 라벨로</Badge>}
                </div>
                {sel.label && <div className="text-[13px]">"{sel.label}"</div>}
                <div className="font-mono text-[11px] text-sub">@{sel.x},{sel.y} {sel.w}×{sel.h}</div>
                <div className="rounded-md bg-muted px-2.5 py-2"><div className="mb-0.5 text-[11px] text-sub">단계 대상</div><Mono className="break-all">{selector}</Mono></div>
                <div className="grid grid-cols-2 gap-1.5">
                  {actions.map(([label, step, Icon], i) => (
                    <Button key={label} variant={i === 0 ? "primary" : "secondary"} size="sm" disabled={working} onClick={() => doStep(step, i === 0 ? sel : null)}
                      className={i === 0 ? "col-span-2" : ""}><Icon className="h-3.5 w-3.5" />{label}</Button>
                  ))}
                </div>
              </div>
            )}
          </Card>
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
          <SaveScenario job={job} refreshJob={refreshJob} stepsCount={steps?.steps.length ?? 0} />
          <Card title="기록된 단계" actions={steps && <span className="text-[11px] text-sub">{steps.fromLaunch ? "앱을 다시 켠 뒤부터" : steps.steps.length ? "다시 켜기 전 것 포함" : ""}</span>}>
            {!steps?.steps.length ? <Empty>통과한 단계가 여기에 쌓입니다</Empty> : (
              <ol className="space-y-1 p-4 pl-9 text-[12px] [list-style:decimal]">
                {steps.steps.map((s, i) => <li key={i}><Mono className="break-all">{s}</Mono></li>)}
              </ol>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}
