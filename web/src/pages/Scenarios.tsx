import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Play, Square, Search, CheckSquare, XSquare, Tag } from "lucide-react";
import { get, post, type Job, type Scenario } from "../lib/api";
import { cx, store, stored, when } from "../lib/util";
import { Badge, Button, Card, Empty, PageHeader, Spinner, StatusBadge, th, td } from "../components/ui";

const CODE: Record<string, string> = { "0": "모두 통과", "1": "앱 판정 실패가 있음", "2": "실행 환경·설정 문제", "-2": "멈춤", "-15": "멈춤", "130": "멈춤" };
type Stop = "" | "never" | "first";

export function Scenarios({ job, refreshJob }: { job: Job | null; refreshJob: () => void }) {
  const [list, setList] = useState<Scenario[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [sel, setSel] = useState<Set<string>>(() => new Set(stored<string[]>("qakit-sel", [])));
  const [reuse, setReuse] = useState(() => stored("qakit-reuse", true));
  const [stop, setStop] = useState<Stop>(() => stored<Stop>("qakit-stop", ""));
  const [precheck, setPrecheck] = useState(() => stored("qakit-precheck", true));
  const [starting, setStarting] = useState(false);
  const logRef = useRef<HTMLPreElement>(null);

  const load = useCallback(() => { get<Scenario[]>("/api/scenarios").then(setList).catch((e) => setError(String(e.message))); }, []);
  useEffect(load, [load]);
  useEffect(() => store("qakit-sel", [...sel]), [sel]);
  useEffect(() => { store("qakit-reuse", reuse); store("qakit-stop", stop); store("qakit-precheck", precheck); }, [reuse, stop, precheck]);
  const wasRunning = useRef(false);
  useEffect(() => {   // 실행이 끝나면 목록(최근 결과)을 새로 고친다
    if (wasRunning.current && job && !job.running) load();
    wasRunning.current = !!job?.running;
  }, [job, load]);
  useEffect(() => { logRef.current?.scrollTo(0, logRef.current.scrollHeight); }, [job?.lines.length]);

  const visible = useMemo(() => (list ?? []).filter((s) => !text
    || `${s.name} ${s.title} ${s.description}`.toLowerCase().includes(text.toLowerCase())), [list, text]);
  const tags = useMemo(() => [...new Set((list ?? []).flatMap((s) => s.tags))].sort(), [list]);
  const chosen = (list ?? []).filter((s) => sel.has(s.name)).map((s) => s.name);
  const toggle = (n: string) => setSel((p) => { const s = new Set(p); if (s.has(n)) s.delete(n); else s.add(n); return s; });
  const add = (names: string[]) => setSel((p) => new Set([...p, ...names]));

  const run = async () => {
    setStarting(true);
    try {
      await post("/api/run", { scenarios: chosen, options: { reuse, stop: stop || null, precheck } });
      refreshJob();
    } catch (e) { alert(`실행하지 못함: ${(e as Error).message}`); }
    setStarting(false);
  };
  const elapsed = job?.started ? Math.round(((job.ended ?? Date.now() / 1000) - job.started)) : 0;

  return (
    <>
      <PageHeader title="시나리오" description="골라서 실행합니다. 최근 10번 결과는 왼쪽이 오래된 것 (회색: 환경 실패). 통과·실패가 섞이면 불안정."
        actions={job?.running
          ? <Button variant="danger" onClick={() => post("/api/job/stop").then(refreshJob)}><Square className="h-3.5 w-3.5" />멈춤</Button>
          : <Button variant="primary" onClick={run} loading={starting} disabled={!chosen.length}><Play className="h-3.5 w-3.5" />선택한 {chosen.length}개 실행</Button>} />

      <Card className="mb-4">
        <div className="flex flex-wrap items-center gap-2 px-4 py-3">
          <label className="flex h-8 items-center gap-2 rounded-md bg-muted px-2.5">
            <Search className="h-3.5 w-3.5 text-sub" />
            <input value={text} onChange={(e) => setText(e.target.value)} placeholder="이름·설명 검색" className="w-52 bg-transparent text-[13px] outline-none placeholder:text-sub" />
          </label>
          <Button size="sm" variant="ghost" onClick={() => add(visible.map((s) => s.name))}><CheckSquare className="h-3.5 w-3.5" />보이는 것 모두</Button>
          <Button size="sm" variant="ghost" onClick={() => setSel(new Set())}><XSquare className="h-3.5 w-3.5" />해제</Button>
          {tags.length > 0 && <span className="ml-2 flex items-center gap-1 text-[12px] text-sub"><Tag className="h-3.5 w-3.5" />태그로 선택
            {tags.map((t) => <button key={t} onClick={() => add((list ?? []).filter((s) => s.tags.includes(t)).map((s) => s.name))}
              className="rounded-md bg-muted px-2 py-0.5 font-mono text-[11px] text-fg hover:bg-line">{t}</button>)}</span>}
        </div>
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-line px-4 py-2.5 text-[13px]">
          <label className="flex items-center gap-2"><input type="checkbox" checked={reuse} onChange={(e) => setReuse(e.target.checked)} className="accent-current" />앱 재사용 <span className="font-mono text-[11px] text-sub">--reuse-app</span></label>
          <label className="flex items-center gap-2">실패하면
            <select value={stop} onChange={(e) => setStop(e.target.value as Stop)} className="rounded-md bg-muted px-2 py-1 text-[12px] outline-none">
              <option value="">같은 원인 2번이면 멈춤</option><option value="never">끝까지</option><option value="first">첫 실패에서 멈춤</option>
            </select></label>
          <label className="flex items-center gap-2"><input type="checkbox" checked={precheck} onChange={(e) => setPrecheck(e.target.checked)} />사전 확인</label>
        </div>
      </Card>

      {job?.args && (
        <Card className="mb-4" title={<span className="flex items-center gap-2">실행 {job.running ? <span className="text-sub">· 실행 중 {elapsed}s</span>
          : <span className={cx(job.code === 0 ? "text-ok" : "text-bad")}>· 끝 ({CODE[String(job.code)] ?? `종료 코드 ${job.code}`}, {elapsed}s)</span>}</span>}
          actions={<span className="font-mono text-[11px] text-sub">{job.args.join(" ")}</span>}>
          <pre ref={logRef} className="max-h-72 overflow-auto whitespace-pre-wrap p-4 font-mono text-[12px] leading-relaxed">{job.lines.join("\n")}</pre>
        </Card>
      )}

      <Card>
        {error ? <Empty>불러오지 못함: {error}</Empty> : list == null ? <Spinner /> : visible.length === 0 ? <Empty>맞는 시나리오가 없습니다</Empty> : (
          <table className="w-full">
            <thead className="border-b border-line"><tr>
              <th className={cx(th, "w-10")}></th><th className={th}>시나리오</th><th className={th}>태그</th><th className={th}>최근 결과</th><th className={th}>마지막</th>
            </tr></thead>
            <tbody>
              {visible.map((s) => (
                <tr key={s.name} onClick={() => toggle(s.name)}
                  className={cx("cursor-pointer border-b border-line last:border-0", sel.has(s.name) ? "bg-muted/70" : "hover:bg-muted/40")}>
                  <td className={td}><input type="checkbox" readOnly checked={sel.has(s.name)} aria-label={`${s.name} 선택`} /></td>
                  <td className={td}>
                    <div className="flex items-center gap-2"><span className="font-mono text-[12px] font-medium">{s.name}</span>{s.flaky && <Badge tone="warn">불안정</Badge>}</div>
                    <div className="text-[13px]">{s.title}</div>
                    {s.description && <div className="mt-0.5 max-w-2xl text-[12px] text-sub">{s.description}</div>}
                  </td>
                  <td className={td}><div className="flex flex-wrap gap-1">{s.tags.map((t) => <Badge key={t} tone="mono">{t}</Badge>)}</div></td>
                  <td className={td}>
                    {s.recent.length ? <div className="flex gap-1">{s.recent.map((r, i) => (
                      <span key={i} title={r === "pass" ? "통과" : r === "env" ? "환경 실패" : "실패"}
                        className={cx("h-2.5 w-2.5 rounded-sm", r === "pass" ? "bg-ok" : r === "env" ? "bg-sub/50" : "bg-bad")} />))}</div>
                      : <span className="text-[12px] text-sub">기록 없음</span>}
                  </td>
                  <td className={cx(td, "text-[12px]")} onClick={(e) => e.stopPropagation()}>
                    {s.last && <div className="flex items-center gap-2"><StatusBadge result={s.last.result} />
                      <span className="font-mono text-sub">{when(s.last.at)}</span>
                      {s.last.dir && <a href={`#/run/${s.last.dir}`} className="text-link hover:underline">상세</a>}</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
