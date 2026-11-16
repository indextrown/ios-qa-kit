import { useState } from "react";
import { ArrowDown, ArrowUp, Check, Pencil, Play, Trash2, X } from "lucide-react";
import { post } from "../lib/api";
import { cx } from "../lib/util";
import { Empty } from "./ui";

/** 기록된 단계 고치기: 글자 고치기·지우기·순서 바꾸기·이 단계만 실행(기록 안 함). 바뀌면 서버 기록(do-steps)을 바로 바꾼다 */
export function StepList({ steps, onChange, onRun, disabled, compact }:
  { steps: string[]; onChange: (s: string[]) => void; onRun: (step: string) => void; disabled?: boolean; compact?: boolean }) {
  const [edit, setEdit] = useState<{ i: number; text: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const save = async (next: string[]) => {
    setError(null);
    try { const r = await post<{ steps: string[] }>("/api/do-steps", { steps: next }); onChange(r.steps); }
    catch (e) { setError((e as Error).message); }
  };
  const move = (i: number, d: number) => { const n = [...steps]; [n[i], n[i + d]] = [n[i + d], n[i]]; save(n); };
  const commit = () => {
    if (!edit) return;
    const t = edit.text.trim();
    setEdit(null);
    if (t && t !== steps[edit.i]) save(steps.map((s, j) => (j === edit.i ? t : s)));
  };

  if (!steps.length) return <Empty>통과한 단계가 여기에 쌓입니다</Empty>;
  const btn = "flex h-6 w-6 items-center justify-center rounded text-sub hover:bg-muted hover:text-fg disabled:opacity-30";
  return (
    <div className={cx("overflow-auto p-2", compact ? "max-h-48" : "max-h-80")}>
      <ol className="space-y-0.5 text-[12px]">
        {steps.map((s, i) => (
          <li key={`${i}-${s}`} className="group flex items-start gap-1.5 rounded-md px-1.5 py-1 hover:bg-muted/60">
            <span className="mt-0.5 w-5 shrink-0 text-right font-mono text-[11px] text-sub">{i + 1}</span>
            {edit?.i === i ? (
              <form className="flex min-w-0 flex-1 gap-1" onSubmit={(e) => { e.preventDefault(); commit(); }}>
                <input autoFocus value={edit.text} onChange={(e) => setEdit({ i, text: e.target.value })}
                  onKeyDown={(e) => { if (e.key === "Escape") setEdit(null); }}
                  className="h-6 min-w-0 flex-1 rounded bg-card px-1.5 font-mono text-[11.5px] outline-none ring-1 ring-line" />
                <button type="submit" className={btn} aria-label="고친 글 저장"><Check className="h-3.5 w-3.5" /></button>
                <button type="button" className={btn} onClick={() => setEdit(null)} aria-label="취소"><X className="h-3.5 w-3.5" /></button>
              </form>
            ) : (
              <>
                <code className="min-w-0 flex-1 cursor-text break-all font-mono text-[11.5px]" onDoubleClick={() => setEdit({ i, text: s })}>{s}</code>
                <span className="flex shrink-0 opacity-0 transition-opacity group-hover:opacity-100">
                  <button className={btn} disabled={disabled} onClick={() => onRun(s)} title="이 단계만 실행 (기록 안 함)"><Play className="h-3 w-3" /></button>
                  <button className={btn} onClick={() => setEdit({ i, text: s })} title="고치기 (두 번 눌러도 됨)"><Pencil className="h-3 w-3" /></button>
                  <button className={btn} disabled={i === 0} onClick={() => move(i, -1)} title="위로"><ArrowUp className="h-3 w-3" /></button>
                  <button className={btn} disabled={i === steps.length - 1} onClick={() => move(i, 1)} title="아래로"><ArrowDown className="h-3 w-3" /></button>
                  <button className={cx(btn, "hover:text-bad")} onClick={() => save(steps.filter((_, j) => j !== i))} title="지우기"><Trash2 className="h-3 w-3" /></button>
                </span>
              </>
            )}
          </li>
        ))}
      </ol>
      {error && <div className="px-2 pt-1 text-[11.5px] text-bad">{error}</div>}
    </div>
  );
}
