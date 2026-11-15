import { useEffect, useMemo, useRef, useState } from "react";
import { Play, Square, ListChecks, CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { get, post, type Job, type Scenario } from "../lib/api";
import { cx, store, stored } from "../lib/util";
import { Button, Card } from "./ui";

const field = "h-8 w-full rounded-md bg-muted px-2.5 text-[13px] outline-none placeholder:text-sub";

/** 라이브 세션에서 만들어 둔 시나리오를 골라 실행 — 왼쪽 라이브 화면으로 진행을 본다 */
export function RunScenario({ job, refreshJob }: { job: Job | null; refreshJob: () => void }) {
  const [list, setList] = useState<Scenario[]>([]);
  const [text, setText] = useState("");
  const [name, setName] = useState(() => stored("qakit-live-scenario", ""));
  const [reuse, setReuse] = useState(() => stored("qakit-reuse", true));
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const logRef = useRef<HTMLPreElement>(null);

  useEffect(() => { get<Scenario[]>("/api/scenarios").then(setList).catch((e) => setError(String(e.message))); }, []);
  useEffect(() => { store("qakit-live-scenario", name); store("qakit-reuse", reuse); }, [name, reuse]);
  useEffect(() => { logRef.current?.scrollTo(0, logRef.current.scrollHeight); }, [job?.lines.length]);

  const shown = useMemo(() => list.filter((s) => !text
    || `${s.name} ${s.title} ${s.tags.join(" ")}`.toLowerCase().includes(text.toLowerCase())), [list, text]);
  const picked = list.find((s) => s.name === name);
  const mine = !!job?.args && !job.draft;   // 시나리오 실행 (초안 재생은 저장 칸에서 보여 줌)

  const run = async () => {
    setStarting(true); setError(null);
    try { await post("/api/run", { scenarios: [name], options: { reuse, stop: null, precheck: false } }); refreshJob(); }
    catch (e) { setError((e as Error).message); }
    setStarting(false);
  };

  return (
    <Card title={<span className="flex items-center gap-1.5"><ListChecks className="h-3.5 w-3.5" />시나리오 실행</span>}
      actions={<span className="text-[11px] text-sub">화면에서 진행을 봅니다</span>}>
      <div className="space-y-2.5 p-4">
        <input className={field} placeholder="이름·제목·태그 검색" value={text} onChange={(e) => setText(e.target.value)} />
        <select className={cx(field, "font-mono text-[12px]")} value={name} onChange={(e) => setName(e.target.value)}>
          <option value="">시나리오 고르기 ({shown.length}개)</option>
          {shown.map((s) => <option key={s.name} value={s.name}>{s.name} — {s.title}</option>)}
        </select>
        {picked?.description && <div className="text-[12px] text-sub">{picked.description}</div>}
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-[12px]"><input type="checkbox" checked={reuse} onChange={(e) => setReuse(e.target.checked)} />
            앱 재사용 <span className="font-mono text-[11px] text-sub">--reuse-app</span></label>
          <span className="flex-1" />
          {job?.running
            ? <Button size="sm" variant="danger" onClick={() => post("/api/job/stop").then(refreshJob)}><Square className="h-3.5 w-3.5" />멈춤</Button>
            : <Button size="sm" variant="primary" onClick={run} loading={starting} disabled={!picked}><Play className="h-3.5 w-3.5" />실행</Button>}
        </div>
        {error && <div className="text-[12px] text-bad">{error}</div>}
        {mine && (
          <div className="rounded-md bg-muted">
            <div className={cx("flex items-center gap-1.5 px-3 pt-2 text-[12px] font-medium",
              job!.running ? "text-sub" : job!.code === 0 ? "text-ok" : "text-bad")}>
              {job!.running ? <><Loader2 className="h-3.5 w-3.5 animate-spin" />실행 중…</>
                : job!.code === 0 ? <><CheckCircle2 className="h-3.5 w-3.5" />통과</>
                  : <><XCircle className="h-3.5 w-3.5" />실패 (종료 코드 {job!.code}) — 실행 기록에서 원인 보기</>}
            </div>
            <pre ref={logRef} className="max-h-40 overflow-auto whitespace-pre-wrap p-3 font-mono text-[11px] leading-relaxed text-sub">{job!.lines.slice(-60).join("\n")}</pre>
          </div>
        )}
      </div>
    </Card>
  );
}
