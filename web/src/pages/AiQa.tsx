import { useCallback, useEffect, useRef, useState } from "react";
import { Bot, MousePointer2, Play, Square, Loader2, CheckCircle2, XCircle, AlertTriangle, Wrench, MessageSquare, Info, ExternalLink } from "lucide-react";
import { fileUrl, get, post, scenarioFromSession, type AiSession } from "../lib/api";
import { aiSecs, aiWhen } from "./AiSession";
import { cx, store, stored } from "../lib/util";
import { AiActivity } from "../components/AiActivity";
import { RobotCursor } from "../components/RobotCursor";
import { Badge, Button, Card, Empty, PageHeader } from "../components/ui";

interface Engine { id: string; name: string; version?: string; ready: boolean; note: string; tested: boolean }
interface Ev { kind: "info" | "text" | "tool" | "result" | "error"; text: string; t: number; why?: string }
interface AiJob {
  running: boolean; engine: string | null; goal: string | null; started: number | null; ended: number | null; code: number | null;
  limit: number | null; stopped: string | null; dir: string | null; total: number; events: Ev[]; mode?: "qa" | "scenario" | null;
  result: { text: string; cost: number | null; turns: number | null; error: boolean; subtype: string | null } | null;
}

const noop = () => {};
const field = "w-full rounded-md bg-muted px-2.5 text-[13px] outline-none placeholder:text-sub";
type Mode = "qa" | "scenario";
const EXAMPLES: Record<Mode, string[]> = {
  qa: [
    "검색 화면 QA: 빈 검색어, 아주 긴 검색어, 특수문자, 뒤로 가기까지 확인",
    "홈 화면의 모든 버튼을 한 번씩 눌러 보고 화면이 정상으로 열리고 돌아오는지",
    "알림 화면 V2: 키워드 등록·삭제 흐름과 빈 목록 안내 문구",
  ],
  scenario: [
    "홈에서 검색 버튼 → 검색어 입력 → 첫 결과를 눌러 상세가 열리는지",
    "마이 탭에서 프로필 설정 화면이 열리고 닉네임 칸이 보이는지",
    "지도 탭에서 목록 보기로 바꾸고 첫 팝업이 보이는지",
  ],
};

/** A3: 목표를 적으면 로그인된 Claude Code·Codex가 qakit 도구만으로 앱을 QA한다 */
export function AiQa() {
  const [engines, setEngines] = useState<Engine[] | null>(null);
  const [goal, setGoal] = useState(() => stored("qakit-ai-goal", ""));
  const [engine, setEngine] = useState(() => stored("qakit-ai-engine", "claude"));
  const [minutes, setMinutes] = useState(() => stored("qakit-ai-minutes", 10));
  const [turns, setTurns] = useState(() => stored("qakit-ai-turns", 60));
  const [save, setSave] = useState(() => stored("qakit-ai-save", false));
  const [mode, setMode] = useState<Mode>(() => stored<Mode>("qakit-ai-mode", "qa"));   // QA(문제 찾기) · 시나리오 만들기
  const [scName, setScName] = useState("");
  const [scTags, setScTags] = useState("");
  const [scStart, setScStart] = useState(() => stored("qakit-ai-start", ""));
  const [readSource, setReadSource] = useState(() => stored("qakit-ai-readsrc", true));   // 시나리오 만들 때 앱 소스도 (읽기 전용)
  useEffect(() => store("qakit-ai-readsrc", readSource), [readSource]);
  const [stepFiles, setStepFiles] = useState<string[]>([]);
  const [saved, setSaved] = useState<string[]>([]);
  useEffect(() => { store("qakit-ai-mode", mode); store("qakit-ai-start", scStart); }, [mode, scStart]);
  useEffect(() => { get<string[]>("/api/steps-files").then(setStepFiles).catch(() => {}); }, []);
  const [cursor, setCursor] = useState(() => stored("qakit-ai-cursor", true));   // 실행기가 누르는 자리 커서
  const [job, setJob] = useState<AiJob | null>(null);
  const [events, setEvents] = useState<Ev[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [now, setNow] = useState(Date.now());
  const [past, setPast] = useState<AiSession[] | null>(null);
  const since = useRef(0);
  const started = useRef<number | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => { get<Engine[]>("/api/ai/engines").then(setEngines).catch((e) => setError(String(e.message))); }, []);
  const loadPast = useCallback(() => { get<AiSession[]>("/api/ai/sessions").then(setPast).catch(() => {}); }, []);
  useEffect(loadPast, [loadPast]);
  const wasRunning = useRef(false);
  useEffect(() => { if (wasRunning.current && !job?.running) loadPast(); wasRunning.current = !!job?.running; }, [job?.running, loadPast]);
  useEffect(() => { store("qakit-ai-goal", goal); store("qakit-ai-engine", engine); store("qakit-ai-minutes", minutes); store("qakit-ai-turns", turns); store("qakit-ai-save", save); store("qakit-ai-cursor", cursor); },
    [goal, engine, minutes, turns, save, cursor]);

  const poll = useCallback(async () => {
    const st = await get<AiJob>(`/api/ai/job?since=${since.current}`);
    if (st.started !== started.current) { started.current = st.started; since.current = 0; setEvents(st.events); }
    else if (st.events.length) setEvents((e) => [...e, ...st.events]);
    since.current = st.total;
    setJob(st);
    return st;
  }, []);
  useEffect(() => {
    let alive = true, t: ReturnType<typeof setTimeout>;
    const loop = async () => { try { const st = await poll(); if (alive) t = setTimeout(loop, st.running ? 800 : 4000); } catch { if (alive) t = setTimeout(loop, 4000); } };
    loop();
    return () => { alive = false; clearTimeout(t); };
  }, [poll]);
  useEffect(() => { logRef.current?.scrollTo(0, logRef.current.scrollHeight); }, [events.length]);
  useEffect(() => { if (!job?.running) return; const i = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(i); }, [job?.running]);

  const start = async () => {
    setStarting(true); setError(null);
    try {
      await post("/api/ai/start", { goal, engine, minutes, turns, save, mode, name: scName.trim() || null, start: scStart || null, readSource,
        tags: scTags.split(",").map((t) => t.trim()).filter(Boolean) });
      setSaved([]); await poll();
    }
    catch (e) { setError((e as Error).message); }
    setStarting(false);
  };
  const stop = async () => { try { await post("/api/ai/stop"); await poll(); } catch (e) { setError((e as Error).message); } };

  useEffect(() => {   // 끝나면 이번 세션에서 저장된 시나리오
    if (!job?.dir || job.running) return;
    get<{ saved: string[] }>(`/api/ai/session?dir=${encodeURIComponent(job.dir)}`).then((d) => setSaved(d.saved)).catch(() => {});
  }, [job?.dir, job?.running]);
  const runSaved = async (name: string) => {
    try { await post("/api/run", { scenarios: [name], options: { reuse: false, precheck: false } }); location.hash = "#/scenarios"; }
    catch (e) { setError((e as Error).message); }
  };
  const eng = engines?.find((e) => e.id === engine);
  const isSc = mode === "scenario";
  const elapsed = job?.started ? Math.round(((job.ended ?? now / 1000) - job.started)) : 0;
  const mmss = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  const running = !!job?.running;

  return (
    <>
      <PageHeader title="AI QA" description={isSc
          ? "확인할 흐름을 적으면 AI가 앱을 직접 눌러 보며 경로를 찾고, 확인(expect)을 넣어 시나리오로 저장합니다 — 새로 켠 앱에서 재생해 통과해야 저장. 사용량은 그 AI 계정에서 씁니다."
          : "목표를 적으면 로그인해 둔 Claude Code·Codex가 qakit 도구만으로 앱을 직접 눌러 보며 QA합니다. 사용량은 그 AI 계정에서 씁니다."}
        actions={running && <Badge tone="warn">AI QA 중 · {mmss(elapsed)}</Badge>} />
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="min-w-0 space-y-4">
          <Card title={<span className="flex items-center gap-1.5"><Bot className="h-3.5 w-3.5" />{isSc ? "만들 시나리오" : "목표"}</span>}
            actions={<div className="inline-flex rounded-md bg-muted p-0.5">
              {([["qa", "QA (문제 찾기)"], ["scenario", "시나리오 만들기"]] as const).map(([v, l]) => (
                <button key={v} onClick={() => setMode(v)} disabled={running}
                  className={cx("rounded px-2.5 py-0.5 text-[12px]", mode === v ? "bg-card font-medium shadow-e1" : "text-sub hover:text-fg")}>{l}</button>))}
            </div>}>
            <div className="space-y-3 p-4">
              <textarea value={goal} onChange={(e) => setGoal(e.target.value)} disabled={running} rows={3}
                placeholder={isSc ? "어떤 흐름을 확인하는 시나리오인지 (예: 홈 → 검색 → 첫 결과 상세가 열리는지)"
                  : "무엇을 QA할지 한두 문장으로 (예: 검색 화면 QA — 빈 검색어, 긴 검색어, 뒤로 가기까지)"}
                className={cx(field, "py-2 leading-relaxed")} />
              {isSc && (
                <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
                  <input value={scName} onChange={(e) => setScName(e.target.value)} disabled={running} placeholder="이름 (비우면 AI가 정함, 예: search-03-detail)"
                    className={cx(field, "h-8 font-mono text-[12px]")} />
                  <input value={scTags} onChange={(e) => setScTags(e.target.value)} disabled={running} placeholder="태그 (쉼표로: smoke, search)"
                    className={cx(field, "h-8 font-mono text-[12px]")} />
                  <select value={scStart} onChange={(e) => setScStart(e.target.value)} disabled={running} className={cx(field, "h-8")} title="앱을 켠 뒤 먼저 밟을 공통 단계">
                    <option value="">시작 공통 단계: AI가 고름</option>
                    {stepFiles.map((x) => <option key={x} value={x}>use: {x}</option>)}
                  </select>
                </div>
              )}
              <div className="flex flex-wrap gap-1.5">
                {EXAMPLES[mode].map((x) => <button key={x} onClick={() => setGoal(x)} disabled={running}
                  className="rounded-md bg-muted px-2 py-1 text-left text-[11.5px] text-sub hover:bg-line hover:text-fg">{x}</button>)}
              </div>
              <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                <label className="text-[11px] text-sub">AI
                  <select value={engine} onChange={(e) => setEngine(e.target.value)} disabled={running} className={cx(field, "mt-1 h-8 text-fg")}>
                    {(engines ?? []).map((e) => <option key={e.id} value={e.id} disabled={!e.ready}>{e.name}{e.version ? ` ${e.version}` : ""}{e.ready ? "" : " (사용 불가)"}</option>)}
                  </select></label>
                <label className="text-[11px] text-sub">시간 한도
                  <select value={minutes} onChange={(e) => setMinutes(Number(e.target.value))} disabled={running} className={cx(field, "mt-1 h-8 text-fg")}>
                    {[3, 5, 10, 20, 30].map((m) => <option key={m} value={m}>{m}분</option>)}
                  </select></label>
                <label className="text-[11px] text-sub">횟수 한도 (AI 응답)
                  <select value={turns} onChange={(e) => setTurns(Number(e.target.value))} disabled={running} className={cx(field, "mt-1 h-8 text-fg")}>
                    {[20, 40, 60, 100, 200].map((m) => <option key={m} value={m}>{m}번</option>)}
                  </select></label>
                {!isSc && <label className="flex items-end gap-2 pb-1.5 text-[12px]"><input type="checkbox" checked={save} onChange={(e) => setSave(e.target.checked)} disabled={running} />
                  확인한 경로를 시나리오로 저장</label>}
                {isSc && <label className="flex items-end gap-2 pb-1.5 text-[12px]" title="AI가 앱 소스에서 화면 코드·흐름·ID를 확인합니다 (Read·Grep만, 고칠 수 없음)">
                  <input type="checkbox" checked={readSource} onChange={(e) => setReadSource(e.target.checked)} disabled={running} />앱 소스도 읽기 (읽기 전용)</label>}
              </div>
              {eng && <div className={cx("flex items-center gap-1.5 text-[11.5px]", eng.ready ? "text-sub" : "text-warn")}>
                {eng.ready ? <Info className="h-3.5 w-3.5" /> : <AlertTriangle className="h-3.5 w-3.5" />}
                {eng.name}: {eng.note}{!eng.tested && " · qakit에서 아직 시험하지 못한 연결"}</div>}
              <div className="text-[11.5px] text-sub">AI는 qakit 도구(화면 읽기·탭·입력·확인·시나리오){isSc && readSource ? "와 앱 소스 읽기" : ""}만 쓸 수 있습니다 — 셸·파일 수정은 막습니다. 비밀번호는 <code>{"{secret:키}"}</code>로만 칩니다.</div>
              {error && <div className="text-[12px] text-bad">{error}</div>}
              <div className="flex justify-end">
                {running
                  ? <Button variant="danger" onClick={stop}><Square className="h-3.5 w-3.5" />멈춤</Button>
                  : <Button variant="primary" onClick={start} loading={starting} disabled={!goal.trim() || !eng?.ready}><Play className="h-3.5 w-3.5" />{isSc ? "AI로 시나리오 만들기" : "AI QA 시작"}</Button>}
              </div>
            </div>
          </Card>

          <Card title={<span className="flex items-center gap-2">진행
              {job?.started && (running ? <span className="flex items-center gap-1 text-[12px] font-normal text-sub"><Loader2 className="h-3.5 w-3.5 animate-spin" />{mmss(elapsed)}{job.limit ? ` / ${mmss(job.limit)}` : ""}</span>
                : <span className={cx("text-[12px] font-normal", job.result && !job.result.error ? "text-ok" : "text-bad")}>
                  끝 · {mmss(elapsed)}{job.stopped ? ` · ${job.stopped}` : ""}</span>)}</span>}
            actions={job?.result && <span className="font-mono text-[11px] text-sub">{job.result.turns != null && `응답 ${job.result.turns}번`}{job.result.cost != null && ` · $${job.result.cost.toFixed(3)} 상당`}</span>}>
            {!job?.started ? <Empty>목표를 적고 시작하면 AI가 하는 말과 쓰는 도구가 여기에 나옵니다</Empty> : (
              <div ref={logRef} className="max-h-[420px] space-y-2 overflow-auto p-4">
                <div className="text-[12px] text-sub">목표: {job.goal}</div>
                {events.map((e, i) => (
                  <div key={i} className="flex gap-2 text-[12.5px]">
                    <span className="w-10 shrink-0 text-right font-mono text-[11px] text-sub">{Math.round(e.t)}s</span>
                    {e.kind === "tool" ? <Wrench className="mt-0.5 h-3.5 w-3.5 shrink-0 text-sub" /> : e.kind === "text" ? <MessageSquare className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                      : e.kind === "error" ? <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-bad" /> : <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-sub" />}
                    <div className="min-w-0">
                      <div className={cx("whitespace-pre-wrap break-words", e.kind === "tool" && "font-mono text-[11.5px] text-sub", e.kind === "error" && "text-bad", e.kind === "text" && "line-clamp-6")}>{e.text}</div>
                      {e.why && <div className="text-[11.5px] text-sub">— {e.why}</div>}
                    </div>
                  </div>
                ))}
                {running && <div className="flex items-center gap-1.5 pl-12 text-[12px] text-sub"><Loader2 className="h-3.5 w-3.5 animate-spin" />생각하는 중…</div>}
              </div>
            )}
          </Card>

          {!running && saved.length > 0 && (
            <Card title={<span className="flex items-center gap-1.5"><CheckCircle2 className="h-3.5 w-3.5 text-ok" />저장된 시나리오 {saved.length}</span>}
              actions={<span className="text-[11px] text-sub">새로 켠 앱에서 재생 통과</span>}>
              <div className="divide-y divide-line">
                {saved.map((n) => (
                  <div key={n} className="flex items-center gap-3 px-4 py-2.5 text-[13px]">
                    <span className="flex-1 font-mono">{n}</span>
                    <a href={`#/edit/scenario/${encodeURIComponent(n)}`} className="text-[12px] text-link hover:underline">편집에서 보기</a>
                    <Button size="sm" onClick={() => runSaved(n)}><Play className="h-3.5 w-3.5" />실행</Button>
                  </div>
                ))}
              </div>
            </Card>
          )}
          {job?.result?.text && (
            <Card title={<span className="flex items-center gap-1.5">{job.result.error ? <XCircle className="h-3.5 w-3.5 text-bad" /> : <CheckCircle2 className="h-3.5 w-3.5 text-ok" />}보고서</span>}
              actions={job.dir && <span className="flex items-center gap-3 text-[11px]">
                {job.mode !== "scenario" && <button onClick={() => scenarioFromSession(job.dir!, job.goal).catch((e) => setError(String(e.message)))}
                  className="font-medium text-link hover:underline">이 결과로 시나리오 만들기</button>}
                <a href={`#/${job.dir}`} className="text-link hover:underline">상세</a>
                <a href={fileUrl(job.dir, "report.md")} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-link hover:underline">report.md<ExternalLink className="h-3 w-3" /></a></span>}>
              <pre className="whitespace-pre-wrap p-4 font-sans text-[13px] leading-relaxed">{job.result.text}</pre>
            </Card>
          )}
          <Card title="지난 AI QA" actions={<span className="text-[11px] text-sub">results/ai/</span>}>
            {past == null ? <Empty>불러오는 중…</Empty> : past.length === 0 ? <Empty>아직 없습니다 (터미널의 Claude Code·Codex가 qakit mcp로 한 것도 여기에 쌓입니다)</Empty> : (
              <div className="divide-y divide-line">
                {past.map((s) => (
                  <a key={s.name} href={`#/${s.dir}`} className="flex items-center gap-3 px-4 py-2.5 hover:bg-muted/50">
                    <span className="w-24 shrink-0 font-mono text-[11px] text-sub">{aiWhen(s.started)}</span>
                    <span className="min-w-0 flex-1">
                      <span className="flex min-w-0 items-center gap-1.5"><span className="truncate text-[13px]">{s.goal ?? "(터미널에서 연결)"}</span>
                        {s.mode === "scenario" && <Badge>시나리오 만들기</Badge>}</span>
                      <span className="text-[11px] text-sub">{s.client ?? "AI"} · 도구 {s.calls}번{s.seconds != null ? ` · ${aiSecs(s.seconds)}` : ""}{s.saved.length ? ` · 시나리오 ${s.saved.length}개 저장` : ""}</span>
                    </span>
                    {s.issues > 0 ? <Badge tone="bad">문제 {s.issues}</Badge> : s.report ? <Badge>문제 없음</Badge> : <Badge>보고서 없음</Badge>}
                  </a>
                ))}
              </div>
            )}
          </Card>
        </div>

        <div className="space-y-4">
          <div className="flex justify-center">
            <Button size="sm" variant="ghost" onClick={() => setCursor(!cursor)} title="AI가 누르는 자리로 커서가 움직이고 누른 곳에 표시"
              className={cx(cursor ? "bg-muted font-medium" : "text-sub")}><MousePointer2 className="h-3.5 w-3.5" />커서 {cursor ? "켬" : "끔"}</Button>
          </div>
          <div className="mx-auto w-full max-w-[300px] rounded-[38px] bg-neutral-900 p-2.5 shadow-e3 ring-1 ring-black/40">
            <div className="relative overflow-hidden rounded-[30px] bg-black">
              <img src="/api/stream?k=ai" alt="시뮬레이터 화면 (실시간)" className="block aspect-[9/19.5] w-full object-cover" />
              <RobotCursor enabled={cursor} />
            </div>
          </div>
          <div className="text-center text-[11px] text-sub">커서·요소까지 보려면 <a href="#/live" className="text-link hover:underline">라이브 세션</a></div>
          <AiActivity onBusy={noop} />
        </div>
      </div>
    </>
  );
}
