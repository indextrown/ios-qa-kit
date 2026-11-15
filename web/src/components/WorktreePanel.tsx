import { useCallback, useEffect, useRef, useState } from "react";
import { GitBranch, GitMerge, RefreshCw, X, AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";
import { get, post } from "../lib/api";
import { cx } from "../lib/util";
import { Button } from "./ui";

interface Wt {
  worktree: boolean; base?: string; ref?: string | null; branch?: string; behind?: number; configured?: string; mode?: "auto" | "warn" | "off";
  dirty?: boolean; incoming?: { hash: string; subject: string; author: string; when: string }[];
  head?: { hash: string; subject: string; when: string }; branches?: { name: string; when: string }[]; appDir?: string;
}

const MODE: Record<string, string> = { auto: "실행 전에 자동으로", warn: "알리기만", off: "끔 (버튼으로만)" };

/** QA 브랜치(qa/workspace)를 기준 브랜치(develop 등)의 최신 커밋으로 — 병합만, push 안 함 (qakit worktree-update).
 *  왼쪽 아래 브랜치 표시를 누르면 열린다. QA 워크트리가 아니면 예전처럼 브랜치만 보여 준다. */
export function WorktreePanel({ fallback }: { fallback: React.ReactNode }) {
  const [wt, setWt] = useState<Wt | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [base, setBase] = useState("");
  const [out, setOut] = useState<{ ok: boolean; text: string } | null>(null);
  const box = useRef<HTMLDivElement>(null);

  const load = useCallback(async (fetch = false) => {
    const w = await get<Wt>(`/api/worktree${fetch ? "?fetch=1" : ""}`);
    setWt(w); if (w.configured) setBase(w.configured);
    return w;
  }, []);
  useEffect(() => { load().catch(() => {}); const t = setInterval(() => load(true).catch(() => {}), 10 * 60 * 1000); return () => clearInterval(t); }, [load]);
  useEffect(() => {   // 바깥을 누르면 닫기
    if (!open) return;
    const f = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", f); return () => document.removeEventListener("mousedown", f);
  }, [open]);

  const act = async (label: string, fn: () => Promise<void>) => {
    setBusy(label); setOut(null);
    try { await fn(); } catch (e) { setOut({ ok: false, text: (e as Error).message }); }
    setBusy(null);
  };
  const check = () => act("check", async () => { await load(true); });
  const update = () => act("update", async () => {
    const r = await post<{ ok: boolean; output: string; status: Wt }>("/api/worktree/update");
    setOut({ ok: r.ok, text: r.output }); setWt(r.status);
  });
  const saveConfig = (body: { base?: string; mode?: string }) => act("config", async () => { setWt(await post<Wt>("/api/worktree/config", body)); });

  if (!wt?.worktree) return <>{fallback}</>;
  const behind = wt.behind ?? 0;
  return (
    <div ref={box} className="relative">
      <button onClick={() => { setOpen(!open); if (!open) check(); }} title="QA 브랜치 최신화"
        className="flex w-full items-center gap-1.5 rounded px-1 py-0.5 text-left font-mono hover:bg-muted hover:text-fg">
        <GitBranch className="h-3.5 w-3.5 shrink-0" /><span className="truncate">{wt.branch}@{wt.head?.hash}</span>
        {behind > 0 ? <span className="ml-auto shrink-0 rounded bg-warn/15 px-1 font-sans text-[10px] font-medium text-warn">{behind} 뒤처짐</span>
          : <span className="ml-auto shrink-0 font-sans text-[10px] text-ok">최신</span>}
      </button>
      {open && (
        <div className="absolute bottom-full left-0 z-50 mb-2 w-[440px] rounded-lg bg-card text-fg shadow-e3 ring-1 ring-line">
          <div className="flex items-center gap-2 border-b border-line px-4 py-2.5">
            <GitMerge className="h-4 w-4" /><span className="text-[13px] font-semibold">QA 브랜치 최신화</span>
            <button onClick={() => setOpen(false)} className="ml-auto rounded p-1 text-sub hover:bg-muted"><X className="h-3.5 w-3.5" /></button>
          </div>
          <div className="space-y-3 p-4 text-[12px]">
            <div className="text-sub">기준 브랜치의 새 커밋을 QA 브랜치로 <b className="text-fg">병합</b>합니다. push하지 않고, 다음 실행 때 앱을 다시 빌드합니다.</div>
            <div className="grid grid-cols-[64px_minmax(0,1fr)] items-center gap-x-2 gap-y-2">
              <span className="text-sub">QA 브랜치</span>
              <span className="truncate font-mono">{wt.branch} @{wt.head?.hash} <span className="font-sans text-sub">· {wt.head?.subject} ({wt.head?.when})</span></span>
              <span className="text-sub">기준</span>
              <span className="flex gap-1.5">
                <input list="qakit-branches" value={base} onChange={(e) => setBase(e.target.value)} placeholder="develop · main · release/*"
                  className="h-7 min-w-0 flex-1 rounded-md bg-muted px-2 font-mono text-[12px] outline-none" />
                <datalist id="qakit-branches">{(wt.branches ?? []).map((b) => <option key={b.name} value={b.name}>{b.when}</option>)}</datalist>
                <Button size="sm" disabled={!base.trim() || base === wt.configured || !!busy} loading={busy === "config"} onClick={() => saveConfig({ base: base.trim() })}>저장</Button>
              </span>
              <span className="text-sub">자동</span>
              <select value={wt.mode} onChange={(e) => saveConfig({ mode: e.target.value })} disabled={!!busy}
                className="h-7 rounded-md bg-muted px-2 text-[12px] outline-none">
                {Object.entries(MODE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </div>
            {wt.base !== wt.configured && <div className="text-[11px] text-sub">패턴 {wt.configured} → 지금은 {wt.base}</div>}

            <div className={cx("flex items-center gap-1.5 rounded-md px-3 py-2", behind ? "bg-warn/10 text-warn" : "bg-ok/10 text-ok")}>
              {busy === "check" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : behind ? <AlertTriangle className="h-3.5 w-3.5" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
              {wt.ref ? (behind ? `${wt.ref}보다 ${behind}커밋 뒤처짐` : `${wt.ref} 기준 최신`) : `기준 브랜치 '${wt.base}'를 찾지 못함`}
            </div>
            {behind > 0 && (
              <div className="max-h-40 space-y-1 overflow-auto">
                <div className="text-[11px] text-sub">가져올 커밋{behind > (wt.incoming?.length ?? 0) ? ` (최근 ${wt.incoming?.length}개)` : ""}</div>
                {(wt.incoming ?? []).map((c) => (
                  <div key={c.hash} className="flex gap-2"><span className="shrink-0 font-mono text-sub">{c.hash}</span>
                    <span className="min-w-0 flex-1 truncate" title={c.subject}>{c.subject}</span><span className="shrink-0 text-[11px] text-sub">{c.when}</span></div>
                ))}
              </div>
            )}
            {wt.dirty && <div className="flex items-start gap-1.5 text-warn"><AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />앱 소스에 커밋하지 않은 변경이 있어 최신화할 수 없습니다 (커밋하거나 정리한 뒤)</div>}
            {out && <pre className={cx("max-h-32 overflow-auto whitespace-pre-wrap rounded-md bg-muted p-2 font-mono text-[11px]", out.ok ? "text-fg" : "text-bad")}>{out.text}</pre>}
            <div className="flex justify-end gap-2">
              <Button size="sm" variant="ghost" onClick={check} loading={busy === "check"} disabled={!!busy && busy !== "check"}><RefreshCw className="h-3.5 w-3.5" />다시 확인</Button>
              <Button size="sm" variant="primary" onClick={update} loading={busy === "update"} disabled={!behind || !!wt.dirty || (!!busy && busy !== "update")}>
                <GitMerge className="h-3.5 w-3.5" />최신화 (병합)</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
