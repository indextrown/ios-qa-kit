import { useEffect, useRef, useState } from "react";
import { Bot, CheckCircle2, XCircle, Loader2, Bug, ChevronDown, ChevronRight } from "lucide-react";
import { fileUrl, get } from "../lib/api";
import { Badge, Card } from "./ui";

export interface AiRow { at: string; tool: string; args: Record<string, unknown>; ok: boolean; seconds: number; summary: string; why?: string }
export interface AiState {
  session: string | null; dir?: string; client?: string | null; active?: boolean; total?: number;
  now?: { tool: string; args: Record<string, unknown>; started: number } | null;
  rows?: AiRow[]; issues?: { n: number; title: string; severity: string; screenshot: string | null }[];
}

const TOOL: Record<string, string> = {
  get_testing_guide: "지침 읽기", launch: "앱 새로 켜기", screen: "화면 읽기", screenshot: "사진 보기", tap: "탭",
  type_text: "입력", swipe: "쓸기", wait_for: "기다림", expect: "확인", step: "단계", recorded_steps: "기록 보기",
  list_scenarios: "시나리오 목록", run_scenario: "시나리오 실행", save_scenario: "시나리오 저장", report_issue: "문제 보고",
};

/** 도구 인자 → 한 줄 (대상·글자·조건 등) */
function what(args: Record<string, unknown>) {
  const pick = args.target ?? args.into ?? args.on ?? args.condition ?? args.name ?? args.yaml ?? args.title;
  const s = (v: unknown) => (typeof v === "string" ? v : JSON.stringify(v));
  let out = pick == null ? "" : s(pick);
  if (args.text != null) out += ` ← "${String(args.text)}"`;
  if (args.dir) out += ` ${args.dir}`;
  if (args.expect) out += ` → ${s(args.expect)}`;
  return out;
}

const clock = (iso: string) => iso.slice(11, 19);

/** A2: AI(qakit mcp)가 하는 일을 라이브 세션에서 본다. 조작 중이면 onBusy(true) */
export function AiActivity({ onBusy }: { onBusy: (busy: boolean, client?: string | null, active?: boolean) => void }) {
  const [ai, setAi] = useState<AiState | null>(null);
  const [rows, setRows] = useState<AiRow[]>([]);
  const [open, setOpen] = useState(true);
  const since = useRef(0);
  const session = useRef<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const [tick, setTick] = useState(Date.now());

  useEffect(() => {
    let alive = true, t: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const st = await get<AiState>(`/api/ai?since=${since.current}`);
        if (!alive) return;
        if (st.session !== session.current) { session.current = st.session; since.current = 0; setRows([]); }
        if (st.rows?.length) { since.current = st.total ?? since.current + st.rows.length; setRows((r) => [...r, ...st.rows!].slice(-200)); }
        else if (st.total != null) since.current = st.total;
        setAi(st);
        onBusy(!!st.now, st.client, !!st.active);
        t = setTimeout(poll, st.active ? 700 : 4000);
      } catch { if (alive) t = setTimeout(poll, 4000); }
    };
    poll();
    return () => { alive = false; clearTimeout(t); };
  }, [onBusy]);
  useEffect(() => { listRef.current?.scrollTo(0, listRef.current.scrollHeight); }, [rows.length, ai?.now?.tool]);
  useEffect(() => { if (!ai?.now) return; const i = setInterval(() => setTick(Date.now()), 500); return () => clearInterval(i); }, [ai?.now]);

  if (!ai?.session) return null;
  const started = ai.session.replace("_", " ").replace(/-(\d\d)-(\d\d)$/, ":$1:$2");
  return (
    <Card title={<button onClick={() => setOpen(!open)} className="flex items-center gap-1.5 whitespace-nowrap">
        {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}<Bot className="h-3.5 w-3.5" />AI 활동
        {ai.active ? <Badge tone="warn">{ai.now ? "조작 중" : "연결됨"}</Badge> : <span className="text-[11px] font-normal text-sub">끝남</span>}
      </button>}
      actions={<span className="truncate text-[11px] text-sub">{ai.client ?? "AI"} · {started} · {ai.total ?? 0}번</span>}>
      {open && (
        <div>
          <div ref={listRef} className="max-h-72 space-y-1.5 overflow-auto px-4 py-3">
            {rows.length === 0 && !ai.now && <div className="py-4 text-center text-[12px] text-sub">아직 도구 호출이 없습니다</div>}
            {rows.map((r, i) => (
              <div key={i} className="text-[12px]">
                <div className="flex items-start gap-1.5">
                  {r.ok ? <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ok" /> : <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-bad" />}
                  <span className="shrink-0 font-mono text-[11px] text-sub">{clock(r.at)}</span>
                  <span className="shrink-0 font-medium">{TOOL[r.tool] ?? r.tool}</span>
                  <span className="min-w-0 truncate font-mono text-[11px] text-sub" title={what(r.args)}>{what(r.args)}</span>
                  <span className="ml-auto shrink-0 font-mono text-[11px] text-sub">{r.seconds}s</span>
                </div>
                {r.why && <div className="ml-5 text-[11.5px] text-sub">— {r.why}</div>}
                {!r.ok && <div className="ml-5 truncate font-mono text-[11px] text-bad" title={r.summary}>{r.summary.split("\n").find((l) => l.includes("❌")) ?? r.summary.split("\n")[0]}</div>}
              </div>
            ))}
            {ai.now && (
              <div className="flex items-center gap-1.5 text-[12px]">
                <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-sub" />
                <span className="font-medium">{TOOL[ai.now.tool] ?? ai.now.tool}</span>
                <span className="min-w-0 truncate font-mono text-[11px] text-sub">{what(ai.now.args)}</span>
                <span className="ml-auto shrink-0 font-mono text-[11px] text-sub">{Math.max(0, Math.round(tick / 1000 - ai.now.started))}s</span>
              </div>
            )}
          </div>
          {(ai.issues?.length ?? 0) > 0 && (
            <div className="border-t border-line px-4 py-3">
              <div className="mb-1.5 flex items-center gap-1.5 text-[12px] font-medium"><Bug className="h-3.5 w-3.5" />보고한 문제 {ai.issues!.length}</div>
              {ai.issues!.map((x) => (
                <div key={x.n} className="flex items-center gap-2 text-[12px]">
                  <Badge tone={x.severity === "높음" ? "bad" : x.severity === "중간" ? "warn" : undefined}>{x.severity}</Badge>
                  <span className="min-w-0 flex-1 truncate">{x.title}</span>
                  {x.screenshot && ai.dir && <a href={fileUrl(ai.dir, x.screenshot)} target="_blank" rel="noreferrer" className="shrink-0 text-[11px] text-link hover:underline">사진</a>}
                </div>
              ))}
              {ai.dir && <a href={fileUrl(ai.dir, "issues.md")} target="_blank" rel="noreferrer" className="mt-1 block text-[11px] text-link hover:underline">results/{ai.dir}/issues.md</a>}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
