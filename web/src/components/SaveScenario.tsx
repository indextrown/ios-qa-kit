import { useEffect, useRef, useState } from "react";
import { FileCheck2, PlayCircle, Save, AlertTriangle, CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { get, post, type Job } from "../lib/api";
import { cx } from "../lib/util";
import { Button, Card, Mono } from "./ui";

interface Draft { name: string; text: string; merged: number; steps: number; fromLaunch: boolean; unknownIds: string[];
  problem: string | null; exists: boolean }

const field = "h-8 w-full rounded-md bg-muted px-2.5 text-[13px] outline-none placeholder:text-sub";

/** U4: 기록된 단계 → 초안 → 다시 재생(통과해야) → scenarios/에 저장 */
export function SaveScenario({ job, refreshJob, stepsCount, aiSession, hint }:
  { job: Job | null; refreshJob: () => void; stepsCount: number; aiSession?: string; hint?: string }) {
  const [name, setName] = useState("");
  const [title, setTitle] = useState("");
  const [desc, setDesc] = useState("");
  const [tags, setTags] = useState("");
  const [start, setStart] = useState("");
  const [stepFiles, setStepFiles] = useState<string[]>([]);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [overwrite, setOverwrite] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const logRef = useRef<HTMLPreElement>(null);

  useEffect(() => { get<string[]>("/api/steps-files").then(setStepFiles).catch(() => {}); }, []);
  const verifying = !!draft && job?.draft === draft.name;
  const verified = verifying && !job?.running && job?.code === 0;
  useEffect(() => { logRef.current?.scrollTo(0, logRef.current.scrollHeight); }, [job?.lines.length]);

  const act = async (label: string, fn: () => Promise<void>) => {
    setBusy(label); setMsg(null);
    try { await fn(); } catch (e) { setMsg({ ok: false, text: (e as Error).message }); }
    setBusy(null);
  };
  const makeDraft = () => act("draft", async () => {
    const d = await post<Draft>("/api/draft", { name: name.trim(), title, description: desc, start: start || null, aiSession,
      tags: tags.split(",").map((t) => t.trim()).filter(Boolean) });
    setDraft(d); setOverwrite(false);
  });
  const verify = () => act("verify", async () => { await post("/api/draft/verify", { name: draft!.name }); refreshJob(); });
  const publish = () => act("publish", async () => {
    const r = await post<{ saved: string }>("/api/draft/publish", { name: draft!.name, force: overwrite });
    setMsg({ ok: true, text: `${r.saved} 에 저장했습니다` }); setDraft(null);
  });

  const warnings = draft ? [
    draft.problem && `형식 오류: ${draft.problem}`,
    draft.unknownIds.length > 0 && `앱에 없는 ID: ${draft.unknownIds.join(", ")}`,
    !draft.fromLaunch && "앱을 다시 켜기 전의 기록이 섞여 있습니다 — 시나리오는 앱을 새로 켜고 시작합니다",
    draft.exists && `scenarios/${draft.name}.qa.yml 이 이미 있습니다`,
  ].filter(Boolean) as string[] : [];

  return (
    <Card title={<span className="flex items-center gap-1.5"><Save className="h-3.5 w-3.5" />시나리오로 저장</span>}
      actions={<span className="text-[11px] text-sub">{hint ?? "재생해서 통과해야 저장"}</span>}>
      <div className="space-y-2.5 p-4">
        <div className="grid grid-cols-2 gap-2">
          <input className={cx(field, "font-mono")} placeholder="이름 (home-12-banner)" value={name} onChange={(e) => setName(e.target.value)} />
          <select className={field} value={start} onChange={(e) => setStart(e.target.value)} title="맨 앞에 넣을 공통 단계">
            <option value="">시작 단계 없음</option>
            {stepFiles.map((s) => <option key={s} value={s}>use: {s}</option>)}
          </select>
        </div>
        <input className={field} placeholder="제목 (무엇을 확인하나)" value={title} onChange={(e) => setTitle(e.target.value)} />
        <textarea className={cx(field, "h-14 py-1.5")} placeholder="설명 1~2줄 (README 목록에 나옴)" value={desc} onChange={(e) => setDesc(e.target.value)} />
        <input className={cx(field, "font-mono")} placeholder="태그 (쉼표로: smoke, home)" value={tags} onChange={(e) => setTags(e.target.value)} />
        <Button className="w-full" onClick={makeDraft} loading={busy === "draft"} disabled={!name.trim() || stepsCount === 0}>
          <FileCheck2 className="h-3.5 w-3.5" />1. 초안 만들기 ({stepsCount}단계)</Button>

        {draft && (
          <>
            <div className="flex items-center justify-between text-[12px] text-sub">
              <span>단계 {draft.steps}개{draft.merged ? ` · 탭+기다림 ${draft.merged}곳 합침` : ""}</span>
              <Mono className="text-[11px]">.qakit/drafts/{draft.name}.qa.yml</Mono>
            </div>
            <pre className="max-h-56 overflow-auto rounded-md bg-muted p-3 font-mono text-[11.5px] leading-relaxed">{draft.text}</pre>
            {warnings.map((w) => <div key={w} className="flex items-start gap-1.5 text-[12px] text-warn"><AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />{w}</div>)}
            <Button className="w-full" onClick={verify} loading={busy === "verify" || (verifying && !!job?.running)}
              disabled={!!job?.running || !!draft.problem || draft.unknownIds.length > 0}>
              <PlayCircle className="h-3.5 w-3.5" />2. 재생해서 확인 (앱을 새로 켜고)</Button>
            {verifying && (
              <div className="rounded-md bg-muted">
                <div className={cx("flex items-center gap-1.5 px-3 pt-2 text-[12px] font-medium",
                  job?.running ? "text-sub" : job?.code === 0 ? "text-ok" : "text-bad")}>
                  {job?.running ? <><Loader2 className="h-3.5 w-3.5 animate-spin" />재생 중…</>
                    : job?.code === 0 ? <><CheckCircle2 className="h-3.5 w-3.5" />통과 — 저장할 수 있습니다</>
                      : <><XCircle className="h-3.5 w-3.5" />실패 (종료 코드 {job?.code}) — 고친 뒤 다시 기록·초안</>}
                </div>
                <pre ref={logRef} className="max-h-40 overflow-auto whitespace-pre-wrap p-3 font-mono text-[11px] leading-relaxed text-sub">{job?.lines.slice(-60).join("\n")}</pre>
              </div>
            )}
            {draft.exists && <label className="flex items-center gap-2 text-[12px]"><input type="checkbox" checked={overwrite} onChange={(e) => setOverwrite(e.target.checked)} />같은 이름 덮어쓰기</label>}
            <Button variant="primary" className="w-full" onClick={publish} loading={busy === "publish"} disabled={!verified || (draft.exists && !overwrite)}>
              <Save className="h-3.5 w-3.5" />3. scenarios/에 저장</Button>
          </>
        )}
        {msg && <div className={cx("text-[12px]", msg.ok ? "text-ok" : "text-bad")}>{msg.text}{msg.ok && <> · <a href="#/scenarios" className="text-link hover:underline">시나리오 보기</a></>}</div>}
      </div>
    </Card>
  );
}
