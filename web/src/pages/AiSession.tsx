import { useEffect, useState } from "react";
import { ArrowLeft, Bug, CheckCircle2, XCircle, Wrench, MessageSquare, Info, ListChecks, FileText } from "lucide-react";
import { fileUrl, get, type AiSession as Summary, type Job } from "../lib/api";
import { cx } from "../lib/util";
import { SaveScenario } from "../components/SaveScenario";
import { Badge, Card, Empty, Mono, Spinner } from "../components/ui";
import type { AiRow } from "../components/AiActivity";

interface Issue { n: number; title: string; severity: string; steps: string[]; expected: string; actual: string; screenshot: string | null }
interface Detail extends Omit<Summary, "report"> {
  report: string | null; rows: AiRow[]; issueList: Issue[]; events: { kind: string; text: string; why?: string }[];
  stepList: string[]; fromLaunch: boolean;
}

export const aiWhen = (iso: string | null) => (iso ? iso.slice(5, 16).replace("T", " ") : "");
export const aiSecs = (s: number | null) => (s == null ? "" : s >= 60 ? `${Math.floor(s / 60)}분 ${s % 60}초` : `${s}초`);

/** A4: 지난 AI QA 한 번 — 보고서·문제(사진)·진행·활동 기록, 통과한 단계로 시나리오 저장 */
export function AiSession({ name, job, refreshJob }: { name: string; job: Job | null; refreshJob: () => void }) {
  const [d, setD] = useState<Detail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"events" | "rows">("rows");
  useEffect(() => {
    setD(null);
    get<Detail>(`/api/ai/session?dir=${encodeURIComponent(`ai/${name}`)}`).then((x) => { setD(x); setTab(x.events.length ? "events" : "rows"); })
      .catch((e) => setError(String(e.message)));
  }, [name]);

  return (
    <>
      <a href="#/ai" className="mb-4 inline-flex items-center gap-1 text-[13px] text-sub hover:text-fg"><ArrowLeft className="h-3.5 w-3.5" />AI QA</a>
      {error ? <Card><Empty>불러오지 못함: {error}</Empty></Card> : !d ? <Card><Spinner /></Card> : (
        <>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold">{d.goal ?? "AI QA (터미널에서 연결)"}</h1>
            {d.issues > 0 ? <Badge tone="bad">문제 {d.issues}</Badge> : d.report ? <Badge>문제 없음</Badge> : null}
          </div>
          <div className="mb-6 flex flex-wrap gap-x-5 gap-y-1 text-[12px] text-sub">
            <span className="font-mono">{aiWhen(d.started)}</span>
            {d.seconds != null && <span className="font-mono">{aiSecs(d.seconds)}</span>}
            <span>{d.client ?? "AI"} · {d.via}</span>
            <span>도구 {d.calls}번{d.failed ? ` (실패 ${d.failed})` : ""}</span>
            {d.turns != null && <span>AI 응답 {d.turns}번</span>}
            {d.cost != null && <span className="font-mono">${d.cost.toFixed(3)} 상당</span>}
            <span className="font-mono">results/{d.dir}</span>
          </div>
          <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
            <div className="min-w-0 space-y-5">
              <Card title={<span className="flex items-center gap-1.5"><FileText className="h-3.5 w-3.5" />보고서</span>}
                actions={d.report && <a href={fileUrl(d.dir, "report.md")} target="_blank" rel="noreferrer" className="text-[11px] text-link hover:underline">report.md</a>}>
                {d.report ? <pre className="whitespace-pre-wrap p-4 font-sans text-[13px] leading-relaxed">{d.report}</pre>
                  : <Empty>보고서 없음 — 터미널의 AI가 연결했거나, 끝나기 전에 멈췄습니다</Empty>}
              </Card>
              <Card title={<div className="inline-flex rounded-md bg-muted p-0.5">
                  {([["events", `진행 ${d.events.length}`], ["rows", `도구 기록 ${d.rows.length}`]] as const).map(([v, l]) => (
                    <button key={v} onClick={() => setTab(v)} className={cx("rounded px-2.5 py-0.5 text-[12px]", tab === v ? "bg-card font-medium shadow-e1" : "text-sub")}>{l}</button>))}
                </div>}>
                <div className="max-h-[480px] space-y-1.5 overflow-auto p-4">
                  {tab === "events" ? (d.events.length === 0 ? <Empty>AI 출력 기록 없음 (UI에서 시작한 AI QA에만 남음)</Empty> : d.events.map((e, i) => (
                    <div key={i} className="flex gap-2 text-[12.5px]">
                      {e.kind === "tool" ? <Wrench className="mt-0.5 h-3.5 w-3.5 shrink-0 text-sub" /> : e.kind === "text" ? <MessageSquare className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                        : e.kind === "error" ? <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-bad" /> : <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-sub" />}
                      <div className="min-w-0">
                        <div className={cx("whitespace-pre-wrap break-words", e.kind === "tool" && "font-mono text-[11.5px] text-sub", e.kind === "error" && "text-bad")}>{e.text}</div>
                        {e.why && <div className="text-[11.5px] text-sub">— {e.why}</div>}
                      </div>
                    </div>
                  ))) : d.rows.map((r, i) => (
                    <div key={i} className="text-[12px]">
                      <div className="flex items-start gap-1.5">
                        {r.ok ? <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ok" /> : <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-bad" />}
                        <span className="shrink-0 font-mono text-[11px] text-sub">{r.at.slice(11, 19)}</span>
                        <span className="shrink-0 font-medium">{r.tool}</span>
                        <span className="min-w-0 truncate font-mono text-[11px] text-sub" title={JSON.stringify(r.args)}>{JSON.stringify(r.args)}</span>
                        <span className="ml-auto shrink-0 font-mono text-[11px] text-sub">{r.seconds}s</span>
                      </div>
                      {r.why && <div className="ml-5 text-[11.5px] text-sub">— {r.why}</div>}
                      {!r.ok && <div className="ml-5 whitespace-pre-wrap font-mono text-[11px] text-bad">{r.summary.split("\n").slice(0, 3).join("\n")}</div>}
                    </div>
                  ))}
                </div>
              </Card>
            </div>
            <div className="space-y-5">
              <Card title={<span className="flex items-center gap-1.5"><Bug className="h-3.5 w-3.5" />문제 {d.issueList.length}</span>}
                actions={d.issueList.length > 0 && <a href={fileUrl(d.dir, "issues.md")} target="_blank" rel="noreferrer" className="text-[11px] text-link hover:underline">issues.md</a>}>
                {d.issueList.length === 0 ? <Empty>AI가 보고한 문제가 없습니다</Empty> : (
                  <div className="divide-y divide-line">
                    {d.issueList.map((x) => (
                      <div key={x.n} className="space-y-2 p-4">
                        <div className="flex items-center gap-2"><Badge tone={x.severity === "높음" ? "bad" : x.severity === "중간" ? "warn" : undefined}>{x.severity}</Badge>
                          <span className="text-[13px] font-medium">{x.title}</span></div>
                        <ol className="list-decimal space-y-0.5 pl-5 text-[12px]">{x.steps.map((s, i) => <li key={i}><Mono className="break-all text-[11.5px]">{s}</Mono></li>)}</ol>
                        <div className="text-[12px]"><span className="text-sub">기대</span> {x.expected}</div>
                        <div className="text-[12px]"><span className="text-sub">실제</span> {x.actual}</div>
                        {x.screenshot && <a href={fileUrl(d.dir, x.screenshot)} target="_blank" rel="noreferrer" className="block w-40 overflow-hidden rounded-lg bg-black p-1 shadow-e2">
                          <img src={fileUrl(d.dir, x.screenshot)} alt={x.title} className="w-full rounded-md" /></a>}
                      </div>
                    ))}
                  </div>
                )}
              </Card>
              <Card title={<span className="flex items-center gap-1.5"><ListChecks className="h-3.5 w-3.5" />AI가 통과한 단계 {d.stepList.length}</span>}
                actions={<span className="text-[11px] text-sub">{d.fromLaunch ? "마지막 launch부터" : "launch 기록 없음"}</span>}>
                {d.stepList.length === 0 ? <Empty>통과한 조작 단계가 없습니다</Empty> : (
                  <ol className="max-h-56 list-decimal space-y-0.5 overflow-auto p-4 pl-9 text-[12px]">{d.stepList.map((s, i) => <li key={i}><Mono className="break-all text-[11.5px]">{s}</Mono></li>)}</ol>
                )}
                {d.saved.length > 0 && <div className="border-t border-line px-4 py-2 text-[12px]">AI가 저장한 시나리오: {d.saved.map((s) => <a key={s} href={`#/edit/scenario/${encodeURIComponent(s)}`} className="mr-2 font-mono text-link hover:underline">{s}</a>)}</div>}
              </Card>
              {d.stepList.length > 0 && <SaveScenario job={job} refreshJob={refreshJob} stepsCount={d.stepList.length} aiSession={d.dir} hint="AI가 통과한 단계 → 재생 통과해야 저장" />}
            </div>
          </div>
        </>
      )}
    </>
  );
}
