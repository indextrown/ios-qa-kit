import { useCallback, useEffect, useRef, useState } from "react";
import { Bot, ChevronDown, ChevronRight, ClipboardList, FileCheck2, Loader2, MessageSquare, MessageSquarePlus, Play, Send, Square, Wrench, XCircle } from "lucide-react";
import { AI_EFFORTS, AI_MODELS, fileUrl, get, post } from "../lib/api";
import { cx, store, stored } from "../lib/util";
import { Button, Card } from "./ui";

interface Ev { kind: "user" | "info" | "text" | "tool" | "result" | "error"; text: string; t: number; why?: string }
interface Job {
  running: boolean; started: number | null; ended: number | null; total: number; events: Ev[]; chat?: boolean; run?: string | null;
  dir: string | null; stopped: string | null; limit: number | null; goal: string | null;
  result: { text: string; cost: number | null; turns: number | null; error: boolean } | null;
}
type Mode = "chat" | "task" | "scenario";

const MODES: [Mode, string, typeof MessageSquare, string][] = [
  ["chat", "대화", MessageSquare, "짧게 시키고 바로 답을 받습니다. 지금 화면에서 이어서."],
  ["task", "맡기기", ClipboardList, "목표와 시간을 주면 AI가 혼자 QA하고 보고서를 대화에 붙입니다."],
  ["scenario", "시나리오로", FileCheck2, "지금까지 대화에서 확인한 흐름을 시나리오로 저장합니다 (재생 통과해야 저장)."],
];
const EXAMPLES: Record<Mode, string[]> = {
  chat: ["지금 화면에 뭐가 보이는지 알려줘", "설정 화면으로 가서 어떤 항목이 있는지 정리해줘", "이 토글이 꺼지는 조건을 소스에서 찾아줘"],
  task: ["로그인 화면 QA: 빈 값, 잘못된 형식, 틀린 비밀번호, 뒤로 가기까지", "설정 화면의 모든 항목을 한 번씩 열어 보고 정상으로 열리고 돌아오는지"],
  scenario: ["지금까지 확인한 흐름", "홈에서 설정을 열고 첫 항목 화면이 열리는지"],
};
const field = "h-7 rounded-md bg-muted px-1.5 text-[11.5px] outline-none";

/** 대화 안에 연달아 나온 도구 호출은 한 묶음으로 접는다 (맡기기는 도구를 수십 번 부른다) */
type Item = { ev: Ev } | { tools: Ev[] };
function group(evs: Ev[]): Item[] {
  const out: Item[] = [];
  for (const e of evs) {
    if (e.kind === "info" || e.kind === "result") continue;
    const last = out[out.length - 1];
    if (e.kind === "tool" && last && "tools" in last) last.tools.push(e);
    else out.push(e.kind === "tool" ? { tools: [e] } : { ev: e });
  }
  return out;
}

function Tools({ tools, open: open0 }: { tools: Ev[]; open: boolean }) {
  const [open, setOpen] = useState(open0);
  useEffect(() => setOpen(open0), [open0]);
  return (
    <div className="pl-1 text-[11.5px] text-sub">
      <button onClick={() => setOpen(!open)} className="flex items-center gap-1 hover:text-fg">
        {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}<Wrench className="h-3 w-3" />
        도구 {tools.length}번{!open && tools[tools.length - 1]?.why ? ` — ${tools[tools.length - 1].why}` : ""}</button>
      {open && <div className="ml-4 mt-1 space-y-1 border-l border-line pl-2">
        {tools.map((e, i) => <div key={i}><div className="truncate font-mono" title={e.text}>{e.text}</div>{e.why && <div>— {e.why}</div>}</div>)}
      </div>}
    </div>
  );
}

/** AI 화면의 대화: 대화(바로 답) · 맡기기(혼자 QA → 보고서) · 시나리오로(대화에서 확인한 흐름 저장)가 한 대화에 이어진다 */
export function AiChat() {
  const [events, setEvents] = useState<Ev[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [mode, setMode] = useState<Mode>(() => stored<Mode>("qakit-ai-chat-mode", "chat"));
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [model, setModel] = useState(() => stored("qakit-ai-model", ""));
  const [effort, setEffort] = useState(() => stored("qakit-ai-effort", ""));
  const [minutes, setMinutes] = useState(() => stored("qakit-ai-minutes", 10));
  const [save, setSave] = useState(() => stored("qakit-ai-save", false));
  const [scName, setScName] = useState("");
  const [scStart, setScStart] = useState(() => stored("qakit-ai-start", ""));
  const [readSource, setReadSource] = useState(() => stored("qakit-ai-readsrc", true));
  const [stepFiles, setStepFiles] = useState<string[]>([]);
  const [saved, setSaved] = useState<string[]>([]);
  const [now, setNow] = useState(Date.now());
  useEffect(() => { store("qakit-ai-model", model); store("qakit-ai-effort", effort); store("qakit-ai-chat-mode", mode); store("qakit-ai-minutes", minutes);
    store("qakit-ai-save", save); store("qakit-ai-start", scStart); store("qakit-ai-readsrc", readSource); }, [model, effort, mode, minutes, save, scStart, readSource]);
  useEffect(() => { get<string[]>("/api/steps-files").then(setStepFiles).catch(() => {}); }, []);
  useEffect(() => {   // 다른 화면(커버리지)에서 넘긴 모드·글 — 한 번만
    const h = stored<{ mode: Mode; text: string } | null>("qakit-ai-handoff", null);
    if (h) { setMode(h.mode); setText(h.text); store("qakit-ai-handoff", null); }
  }, []);
  const since = useRef(0), started = useRef<number | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const poll = useCallback(async () => {
    const st = await get<Job>(`/api/ai/job?since=${since.current}`);
    if (st.started !== started.current) { started.current = st.started; since.current = 0; setEvents(st.events); setSaved([]); }
    else if (st.events.length) setEvents((e) => [...e, ...st.events]);
    since.current = st.total;
    setJob(st);
    return st;
  }, []);
  useEffect(() => {
    let alive = true, t: ReturnType<typeof setTimeout>;
    const loop = async () => {
      let st: Job | null = null;
      try { st = await poll(); } catch { /* 다음에 */ }
      if (alive) t = setTimeout(loop, st?.running ? 700 : 3000);
    };
    loop();
    return () => { alive = false; clearTimeout(t); };
  }, [poll]);
  useEffect(() => { listRef.current?.scrollTo(0, listRef.current.scrollHeight); }, [events.length, job?.running]);
  useEffect(() => { if (!job?.running) return; const i = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(i); }, [job?.running]);
  const wasRunning = useRef(false);
  useEffect(() => {   // 시나리오로 남기기가 끝나면 저장된 시나리오
    if (wasRunning.current && !job?.running && job?.run === "scenario" && job.dir)
      get<{ saved: string[] }>(`/api/ai/session?dir=${encodeURIComponent(job.dir)}`).then((d) => setSaved(d.saved)).catch(() => {});
    wasRunning.current = !!job?.running;
  }, [job?.running, job?.run, job?.dir]);

  const running = !!job?.running;
  const busy = running || sending;
  const common = { model: model || null, effort: effort || null };
  const send = async (msg = text) => {
    const m = msg.trim();
    if (busy || (!m && mode !== "scenario")) return;
    setSending(true); setError(null);
    try {
      if (mode === "chat") await post("/api/ai/chat", { message: m, readSource, ...common });
      else if (mode === "task") await post("/api/ai/start", { goal: m, mode: "qa", minutes, turns: 80, save, inChat: true, readSource, ...common });
      else await post("/api/ai/start", { goal: m || "지금까지 대화에서 확인한 흐름", mode: "scenario", minutes, turns: 80, inChat: true,
        name: scName.trim() || null, start: scStart || null, readSource, ...common });
      setText(""); if (mode !== "chat") setMode("chat");
      await poll();
    } catch (e) { setError((e as Error).message); }
    setSending(false);
  };
  const stop = async () => { try { await post("/api/ai/stop"); } catch (e) { setError((e as Error).message); } };
  const newChat = async () => {
    try { await post("/api/ai/chat/new"); setEvents([]); setSaved([]); await poll(); } catch (e) { setError((e as Error).message); }
  };
  const runSaved = async (name: string) => {
    try { await post("/api/run", { scenarios: [name], options: { reuse: false, precheck: false } }); location.hash = "#/scenarios"; }
    catch (e) { setError((e as Error).message); }
  };

  const items = group(events);
  const elapsed = job?.started && running ? Math.round(now / 1000 - (job.started ?? 0)) : 0;
  const runLabel = job?.run === "qa" ? "맡긴 일 하는 중" : job?.run === "scenario" ? "시나리오 만드는 중" : "AI가 하는 중";
  const modeInfo = MODES.find((m) => m[0] === mode)!;
  return (
    <Card className="flex flex-col" title={<span className="flex items-center gap-1.5"><Bot className="h-3.5 w-3.5" />대화</span>}
      actions={<>
        <select value={model} onChange={(e) => setModel(e.target.value)} disabled={busy} title="모델 (다음 말부터)" className={field}>
          {AI_MODELS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <select value={effort} onChange={(e) => setEffort(e.target.value)} disabled={busy} title="추론 정도 (높을수록 꼼꼼하지만 느리고 사용량이 큼)" className={field}>
          {AI_EFFORTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <label className="flex items-center gap-1 text-[11.5px] text-sub" title="AI가 화면만으로 모호할 때 앱 소스를 찾아 봅니다 (읽기 전용 · 비밀값 파일은 막힘). 근거를 파일:줄로 붙입니다">
          <input type="checkbox" checked={readSource} onChange={(e) => setReadSource(e.target.checked)} disabled={busy} />소스</label>
        {job?.dir && job.chat && <a href={fileUrl(job.dir, "chat.md")} target="_blank" rel="noreferrer" className="text-[11px] text-link hover:underline">기록</a>}
        <Button size="sm" variant="ghost" disabled={busy || !events.length} onClick={newChat} title="새 대화 (AI가 앞 대화를 잊음)">
          <MessageSquarePlus className="h-3.5 w-3.5" />새 대화</Button>
      </>}>
      <div ref={listRef} className="min-h-[18rem] flex-1 space-y-2 overflow-auto px-3 py-3 text-[12.5px] xl:max-h-[calc(100vh-24rem)]">
        {items.length === 0 && (
          <div className="space-y-2 py-6 text-center text-[12px] text-sub">
            <div>말로 시키면 AI가 화면을 읽고 조작한 뒤 답합니다. 대화는 이어집니다.</div>
            <div className="flex flex-wrap justify-center gap-1.5">
              {EXAMPLES[mode].map((x) => <button key={x} onClick={() => setText(x)} className="rounded-full bg-muted px-2.5 py-1 text-[11.5px] hover:text-fg">{x}</button>)}
            </div>
          </div>
        )}
        {items.map((it, i) => "tools" in it ? <Tools key={i} tools={it.tools} open={running && i === items.length - 1} /> : (() => {
          const e = it.ev;
          if (e.kind === "user") {
            const task = /^\[(맡김|시나리오로)/.test(e.text);
            return <div key={i} className="flex justify-end"><div className={cx("max-w-[85%] whitespace-pre-wrap break-words rounded-2xl rounded-br-md px-3 py-2",
              task ? "bg-warn/15 ring-1 ring-warn/30" : "bg-primary text-primary-fg")}>{e.text}</div></div>;
          }
          if (e.kind === "text") return <div key={i} className="max-w-[94%] whitespace-pre-wrap break-words rounded-2xl rounded-bl-md bg-muted px-3 py-2">{e.text}</div>;
          if (e.kind === "error") return <div key={i} className="flex items-start gap-1.5 text-[11.5px] text-bad"><XCircle className="mt-0.5 h-3 w-3 shrink-0" /><span className="break-words">{e.text}</span></div>;
          return null;
        })())}
        {running && <div className="flex items-center gap-1.5 pl-1 text-[12px] text-sub"><Loader2 className="h-3.5 w-3.5 animate-spin" />{runLabel}
          {job?.run !== "chat" && job?.limit ? ` · ${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, "0")} / ${job.limit / 60}분` : ""}</div>}
        {saved.length > 0 && !running && (
          <div className="space-y-1 rounded-lg bg-ok/10 p-2 text-[12px] ring-1 ring-ok/30">
            <div className="font-medium text-ok">저장된 시나리오 (재생 통과)</div>
            {saved.map((n) => <div key={n} className="flex items-center gap-2"><code className="flex-1 font-mono">{n}</code>
              <a href={`#/edit/scenario/${encodeURIComponent(n)}`} className="text-link hover:underline">편집</a>
              <Button size="sm" onClick={() => runSaved(n)}><Play className="h-3 w-3" />실행</Button></div>)}
          </div>
        )}
        {job?.result?.cost != null && !running && <div className="text-right text-[10.5px] text-sub">마지막 응답 ${job.result.cost.toFixed(2)}</div>}
      </div>
      <div className="border-t border-line p-3">
        <div className="mb-2 inline-flex rounded-md bg-muted p-0.5">
          {MODES.map(([v, l, Icon]) => (
            <button key={v} onClick={() => setMode(v)} className={cx("flex items-center gap-1 rounded px-2.5 py-0.5 text-[12px]",
              mode === v ? "bg-card font-medium shadow-e1" : "text-sub hover:text-fg")}><Icon className="h-3 w-3" />{l}</button>))}
        </div>
        <div className="mb-2 text-[11px] text-sub">{modeInfo[3]}</div>
        {mode === "task" && <div className="mb-2 flex flex-wrap items-center gap-2 text-[11.5px]">
          <select value={minutes} onChange={(e) => setMinutes(Number(e.target.value))} className={field}>
            {[3, 5, 10, 20, 30].map((m) => <option key={m} value={m}>{m}분까지</option>)}</select>
          <label className="flex items-center gap-1.5"><input type="checkbox" checked={save} onChange={(e) => setSave(e.target.checked)} />확인한 경로를 시나리오로 저장</label>
        </div>}
        {mode === "scenario" && <div className="mb-2 grid grid-cols-2 gap-1.5 text-[11.5px]">
          <input value={scName} onChange={(e) => setScName(e.target.value)} placeholder="이름 (비우면 AI가 정함)" className={cx(field, "font-mono")} />
          <select value={scStart} onChange={(e) => setScStart(e.target.value)} className={field} title="앱을 켠 뒤 먼저 밟을 공통 단계">
            <option value="">시작 단계: AI가 고름</option>
            {stepFiles.map((x) => <option key={x} value={x}>use: {x}</option>)}</select>
        </div>}
        {error && <div className="mb-2 text-[11.5px] text-bad">{error}</div>}
        <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); send(); }}>
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2}
            placeholder={mode === "chat" ? "무엇을 해 볼까요? (Enter 보내기, Shift+Enter 줄바꿈)" : mode === "task" ? "맡길 목표 (예: 로그인 화면 QA — 빈 값·틀린 비밀번호·뒤로 가기)" : "어떤 흐름을 시나리오로 (비우면 지금까지 대화에서 확인한 흐름)"}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(); } }}
            className="min-h-[2.5rem] flex-1 resize-y rounded-md bg-muted px-2.5 py-1.5 text-[12.5px] outline-none placeholder:text-sub" />
          {running
            ? <Button type="button" variant="danger" onClick={stop}><Square className="h-3.5 w-3.5 fill-current" />멈춤</Button>
            : <Button type="submit" variant="primary" disabled={busy || (!text.trim() && mode !== "scenario")} loading={sending}>
                <Send className="h-3.5 w-3.5" />{mode === "chat" ? "보내기" : mode === "task" ? "맡기기" : "남기기"}</Button>}
        </form>
        <div className="mt-1.5 text-[11px] text-sub">Claude Code 계정 사용량이 듭니다 · AI는 qakit 도구만 쓰고, 되돌릴 수 없는 일(삭제·결제 등)은 분명히 시킬 때만 합니다</div>
      </div>
    </Card>
  );
}
