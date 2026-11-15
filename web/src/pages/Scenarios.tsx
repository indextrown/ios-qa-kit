import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Play, Square, Search, CheckSquare, XSquare, Tag, ChevronDown, ChevronRight, Pencil, Bot } from "lucide-react";
import { get, post, type Job, type Scenario } from "../lib/api";
import { cx, store, stored, when } from "../lib/util";
import { Badge, Button, Card, Empty, PageHeader, Spinner, StatusBadge } from "../components/ui";

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
  const [goLive, setGoLive] = useState(() => stored("qakit-run-golive", true));   // 실행하면 라이브 세션으로 (화면·커서로 진행 보기)
  useEffect(() => store("qakit-run-golive", goLive), [goLive]);
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

  const [fold, setFold] = useState<Set<string>>(() => new Set(stored<string[]>("qakit-fold", [])));
  useEffect(() => store("qakit-fold", [...fold]), [fold]);
  const visible = useMemo(() => (list ?? []).filter((s) => !text
    || `${s.name} ${s.title} ${s.description}`.toLowerCase().includes(text.toLowerCase())), [list, text]);
  // 이름 앞부분(alert-01 → alert)으로 묶는다
  const groups = useMemo(() => {
    const m = new Map<string, Scenario[]>();
    for (const s of visible) { const g = s.name.split("-")[0] || s.name; m.set(g, [...(m.get(g) ?? []), s]); }
    return [...m.entries()];
  }, [visible]);
  const tags = useMemo(() => [...new Set((list ?? []).flatMap((s) => s.tags))].sort(), [list]);
  const chosen = (list ?? []).filter((s) => sel.has(s.name)).map((s) => s.name);
  const toggle = (n: string) => setSel((p) => { const s = new Set(p); if (s.has(n)) s.delete(n); else s.add(n); return s; });
  const add = (names: string[]) => setSel((p) => new Set([...p, ...names]));

  const run = async () => {
    setStarting(true);
    try {
      await post("/api/run", { scenarios: chosen, options: { reuse, stop: stop || null, precheck } });
      refreshJob();
      if (goLive) location.hash = "#/live";
    } catch (e) { alert(`실행하지 못함: ${(e as Error).message}`); }
    setStarting(false);
  };
  const runOne = async (name: string) => {
    try { await post("/api/run", { scenarios: [name], options: { reuse, stop: null, precheck: false } }); refreshJob(); if (goLive) location.hash = "#/live"; }
    catch (e) { alert(`실행하지 못함: ${(e as Error).message}`); }
  };
  const aiCreate = () => { store("qakit-ai-mode", "scenario"); location.hash = "#/ai"; };
  const elapsed = job?.started ? Math.round(((job.ended ?? Date.now() / 1000) - job.started)) : 0;

  return (
    <>
      <PageHeader title="시나리오" description="골라서 실행합니다. 최근 10번 결과는 왼쪽이 오래된 것 (회색: 환경 실패). 통과·실패가 섞이면 불안정."
        actions={job?.running
          ? <Button variant="danger" onClick={() => post("/api/job/stop").then(refreshJob)}><Square className="h-3.5 w-3.5" />멈춤</Button>
          : <div className="flex gap-2"><Button onClick={aiCreate} title="흐름을 말로 적으면 AI가 앱을 눌러 보며 시나리오를 만든다"><Bot className="h-3.5 w-3.5" />AI로 만들기</Button>
            <Button variant="primary" onClick={run} loading={starting} disabled={!chosen.length}><Play className="h-3.5 w-3.5" />선택한 {chosen.length}개 실행</Button></div>} />

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
          <label className="flex items-center gap-2" title="실행하면 라이브 세션으로 넘어가 실시간 화면·커서로 진행을 봅니다 (로그는 오른쪽 '시나리오 실행')">
            <input type="checkbox" checked={goLive} onChange={(e) => setGoLive(e.target.checked)} />실행하면 라이브 세션으로</label>
        </div>
      </Card>

      {job?.args && (
        <Card className="mb-4" title={<span className="flex items-center gap-2">실행 {job.running ? <span className="text-sub">· 실행 중 {elapsed}s</span>
          : <span className={cx(job.code === 0 ? "text-ok" : "text-bad")}>· 끝 ({CODE[String(job.code)] ?? `종료 코드 ${job.code}`}, {elapsed}s)</span>}</span>}
          actions={<span className="font-mono text-[11px] text-sub">{job.args.join(" ")}</span>}>
          <pre ref={logRef} className="max-h-72 overflow-auto whitespace-pre-wrap p-4 font-mono text-[12px] leading-relaxed">{job.lines.join("\n")}</pre>
        </Card>
      )}

      {error ? <Card><Empty>불러오지 못함: {error}</Empty></Card> : list == null ? <Card><Spinner /></Card> : visible.length === 0 ? <Card><Empty>맞는 시나리오가 없습니다</Empty></Card> : (
        <div className="space-y-3">
          {groups.map(([g, items]) => {
            const folded = fold.has(g);
            const allSel = items.every((x) => sel.has(x.name));
            const passed = items.filter((x) => x.last?.result === "Passed").length;
            const failed = items.filter((x) => x.last?.result === "Failed").length;
            return (
              <Card key={g}>
                <div className="flex items-center gap-3 px-4 py-2.5">
                  <input type="checkbox" checked={allSel} onChange={() => setSel((p) => { const n = new Set(p); items.forEach((x) => (allSel ? n.delete(x.name) : n.add(x.name))); return n; })}
                    aria-label={`${g} 묶음 선택`} />
                  <button onClick={() => setFold((p) => { const n = new Set(p); if (n.has(g)) n.delete(g); else n.add(g); return n; })} className="flex flex-1 items-center gap-2 text-left">
                    {folded ? <ChevronRight className="h-3.5 w-3.5 text-sub" /> : <ChevronDown className="h-3.5 w-3.5 text-sub" />}
                    <span className="font-mono text-[13px] font-semibold">{g}</span>
                    <span className="text-[12px] text-sub">{items.length}개</span>
                    {failed > 0 && <Badge tone="bad">실패 {failed}</Badge>}
                    {failed === 0 && passed === items.length && <span className="text-[11px] text-ok">모두 통과</span>}
                  </button>
                </div>
                {!folded && (
                  <div className="divide-y divide-line border-t border-line">
                    {items.map((s) => (
                      <div key={s.name} onClick={() => toggle(s.name)}
                        className={cx("group grid cursor-pointer grid-cols-[20px_minmax(0,1fr)_auto] items-center gap-x-4 px-4 py-2.5 md:grid-cols-[20px_minmax(0,1fr)_150px_200px_64px]",
                          sel.has(s.name) ? "bg-muted/70" : "hover:bg-muted/40")}>
                        <input type="checkbox" readOnly checked={sel.has(s.name)} aria-label={`${s.name} 선택`} />
                        <div className="min-w-0">
                          <div className="flex min-w-0 items-center gap-2">
                            <span className="truncate text-[13.5px] font-medium">{s.title || s.name}</span>
                            {s.flaky && <Badge tone="warn">불안정</Badge>}
                          </div>
                          <div className="mt-0.5 flex min-w-0 items-center gap-2 text-[11.5px] text-sub">
                            <span className="shrink-0 font-mono">{s.name}</span>
                            {s.tags.map((t) => <span key={t} className="shrink-0 rounded bg-muted px-1.5 font-mono text-[10.5px] text-fg/80">{t}</span>)}
                            {s.description && <span className="truncate" title={s.description}>· {s.description}</span>}
                          </div>
                        </div>
                        <div className="hidden md:block">
                          {s.recent.length ? <div className="flex gap-[3px]" title="최근 결과 (왼쪽이 오래된 것)">{s.recent.map((r, i) => (
                            <span key={i} title={r === "pass" ? "통과" : r === "env" ? "환경 실패" : "실패"}
                              className={cx("h-3 w-2 rounded-[2px]", r === "pass" ? "bg-ok" : r === "env" ? "bg-sub/50" : "bg-bad")} />))}</div>
                            : <span className="text-[11.5px] text-sub">기록 없음</span>}
                        </div>
                        <div className="hidden items-center gap-2 whitespace-nowrap text-[12px] md:flex" onClick={(e) => e.stopPropagation()}>
                          {s.last ? <>
                            <StatusBadge result={s.last.result} />
                            {s.last.dir ? <a href={`#/run/${s.last.dir}`} className="font-mono text-sub hover:text-link hover:underline" title="실행 상세">{when(s.last.at)}</a>
                              : <span className="font-mono text-sub">{when(s.last.at)}</span>}
                          </> : null}
                        </div>
                        <div className="flex items-center justify-end gap-0.5 opacity-60 group-hover:opacity-100" onClick={(e) => e.stopPropagation()}>
                          <button title="이것만 실행" disabled={!!job?.running} onClick={() => runOne(s.name)}
                            className="rounded p-1.5 text-sub hover:bg-muted hover:text-fg disabled:opacity-30"><Play className="h-3.5 w-3.5" /></button>
                          <a title="편집" href={`#/edit/scenario/${encodeURIComponent(s.name)}`} className="rounded p-1.5 text-sub hover:bg-muted hover:text-fg"><Pencil className="h-3.5 w-3.5" /></a>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      )}
    </>
  );
}
