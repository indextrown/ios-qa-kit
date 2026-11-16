import { useCallback, useEffect, useRef, useState } from "react";
import { Bot, Loader2, MessageSquarePlus, Send, Square, Wrench, XCircle } from "lucide-react";
import { fileUrl, get, post } from "../lib/api";
import { Button, Card } from "./ui";

interface Ev { kind: "user" | "info" | "text" | "tool" | "result" | "error"; text: string; t: number; why?: string }
interface Job {
  running: boolean; started: number | null; total: number; events: Ev[]; mode?: string | null; chat?: boolean;
  dir: string | null; stopped: string | null;
  result: { text: string; cost: number | null; turns: number | null; error: boolean } | null;
}

const EXAMPLES = ["지금 화면에 뭐가 보이는지 알려줘", "설정 화면으로 가서 어떤 항목이 있는지 정리해줘", "로그인 화면에서 빈 칸으로 로그인 눌러 보고 결과 알려줘"];

/** AI 채팅창: 말로 시키면 AI(Claude Code)가 qakit 도구로 기기를 조작하고 답한다. 한 마디 = AI 한 차례, 대화는 이어진다 */
export function AiChat() {
  const [events, setEvents] = useState<Ev[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [text, setText] = useState("");
  const [fresh, setFresh] = useState(false);   // 다음 말은 새 대화로
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const since = useRef(0), started = useRef<number | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const poll = useCallback(async () => {
    const st = await get<Job>(`/api/ai/job?since=${since.current}`);
    if (st.started !== started.current) { started.current = st.started; since.current = 0; setEvents(st.events); }
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

  const isChat = !!job?.chat && !fresh;
  const otherAi = !!job?.running && !job?.chat;   // AI QA(목표 한 줄)가 도는 중
  const busy = !!job?.running || sending;
  const send = async (msg = text) => {
    const m = msg.trim();
    if (!m || busy) return;
    setSending(true); setError(null);
    try {
      await post("/api/ai/chat", { message: m, new: !isChat });
      setText(""); setFresh(false);
      await poll();
    } catch (e) { setError((e as Error).message); }
    setSending(false);
  };
  const stop = async () => { try { await post("/api/ai/stop"); } catch (e) { setError((e as Error).message); } };

  const shown = isChat ? events : [];
  return (
    <Card title={<span className="flex items-center gap-1.5"><Bot className="h-3.5 w-3.5" />AI 채팅</span>}
      actions={<>
        {job?.result?.cost != null && isChat && <span className="text-[11px] text-sub">${job.result.cost.toFixed(2)}</span>}
        {isChat && job?.dir && <a href={fileUrl(job.dir, "chat.md")} target="_blank" rel="noreferrer" className="text-[11px] text-link hover:underline">기록</a>}
        <Button size="sm" variant="ghost" disabled={busy || !isChat} onClick={() => { setFresh(true); setEvents([]); }} title="새 대화 (AI가 앞 대화를 잊음)">
          <MessageSquarePlus className="h-3.5 w-3.5" />새 대화</Button>
      </>}>
      <div ref={listRef} className="max-h-[52vh] min-h-40 space-y-2 overflow-auto px-3 py-3 text-[12.5px]">
        {shown.length === 0 && (
          <div className="space-y-2 py-2 text-center text-[12px] text-sub">
            <div>말로 시키면 AI가 화면을 읽고 조작한 뒤 답합니다. 대화는 이어집니다.</div>
            <div className="flex flex-wrap justify-center gap-1.5">
              {EXAMPLES.map((x) => <button key={x} onClick={() => setText(x)} className="rounded-full bg-muted px-2.5 py-1 text-[11.5px] hover:text-fg">{x}</button>)}
            </div>
          </div>
        )}
        {shown.map((e, i) => e.kind === "user" ? (
          <div key={i} className="flex justify-end"><div className="max-w-[85%] whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-primary px-3 py-2 text-primary-fg">{e.text}</div></div>
        ) : e.kind === "text" ? (
          <div key={i} className="max-w-[92%] whitespace-pre-wrap break-words rounded-2xl rounded-bl-md bg-muted px-3 py-2">{e.text}</div>
        ) : e.kind === "tool" ? (
          <div key={i} className="flex items-start gap-1.5 pl-1 text-[11.5px] text-sub">
            <Wrench className="mt-0.5 h-3 w-3 shrink-0" />
            <div className="min-w-0"><div className="truncate font-mono" title={e.text}>{e.text}</div>{e.why && <div>— {e.why}</div>}</div>
          </div>
        ) : e.kind === "error" ? (
          <div key={i} className="flex items-start gap-1.5 text-[11.5px] text-bad"><XCircle className="mt-0.5 h-3 w-3 shrink-0" /><span className="break-words">{e.text}</span></div>
        ) : null)}
        {isChat && job?.running && <div className="flex items-center gap-1.5 pl-1 text-[12px] text-sub"><Loader2 className="h-3.5 w-3.5 animate-spin" />AI가 하는 중…</div>}
      </div>
      <div className="border-t border-line p-3">
        {otherAi && <div className="mb-2 text-[11.5px] text-warn">AI QA가 도는 중입니다 — 끝나면 채팅할 수 있습니다</div>}
        {error && <div className="mb-2 text-[11.5px] text-bad">{error}</div>}
        <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); send(); }}>
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} placeholder={isChat ? "이어서 시키기 (Enter 보내기, Shift+Enter 줄바꿈)" : "무엇을 해 볼까요? (Enter 보내기)"}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(); } }}
            className="min-h-[2.5rem] flex-1 resize-y rounded-md bg-muted px-2.5 py-1.5 text-[12.5px] outline-none placeholder:text-sub" />
          {isChat && job?.running
            ? <Button type="button" variant="danger" onClick={stop}><Square className="h-3.5 w-3.5 fill-current" />멈춤</Button>
            : <Button type="submit" variant="primary" disabled={busy || otherAi || !text.trim()} loading={sending}><Send className="h-3.5 w-3.5" />보내기</Button>}
        </form>
        <div className="mt-1.5 text-[11px] text-sub">Claude Code 계정 사용량이 듭니다 · 되돌릴 수 없는 일(삭제·결제 등)은 분명히 시킬 때만 합니다</div>
      </div>
    </Card>
  );
}
