import { useEffect, useRef, useState } from "react";
import { Check, ChevronsUpDown, FolderOpen, Loader2 } from "lucide-react";
import { get, post } from "../lib/api";
import { cx } from "../lib/util";

interface Ws { path: string; name: string; platform: string; build?: string; last?: string; current: boolean }

const home = (p: string) => p.replace(/^\/Users\/[^/]+/, "~");

/** 왼쪽 위 작업공간 이름 → 눌러서 다른 작업공간으로. 맥 앱 창이면 앱이 그 작업공간 창을 열고(qakit-app://open),
 *  브라우저(터미널 qakit ui)면 서버가 그 작업공간의 qakit ui를 띄워 주소로 넘어간다 */
export function WorkspaceSwitch({ name }: { name: string }) {
  const [open, setOpen] = useState(false);
  const [list, setList] = useState<{ app: boolean; workspaces: Ws[] } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    get<{ app: boolean; workspaces: Ws[] }>("/api/workspaces").then(setList).catch((e) => setError((e as Error).message));
    const close = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const go = async (w: Ws) => {
    if (w.current) return setOpen(false);
    setError(null);
    if (list?.app) { location.href = `qakit-app://open?path=${encodeURIComponent(w.path)}`; setOpen(false); return; }
    setBusy(w.path);
    try {
      const r = await post<{ url: string | null }>("/api/workspaces/open", { path: w.path });
      if (r.url) location.href = r.url;
    } catch (e) { setError((e as Error).message); }
    setBusy(null);
  };

  return (
    <div ref={box} className="relative min-w-0 flex-1">
      <button onClick={() => setOpen(!open)} className="flex w-full min-w-0 items-center gap-1 rounded-md text-left hover:text-fg" title="작업공간 바꾸기">
        <span className="min-w-0 leading-tight">
          <span className="block text-[14px] font-semibold tracking-head">qakit</span>
          <span className="block truncate text-[11px] text-sub">{name}</span>
        </span>
        <ChevronsUpDown className="ml-auto h-3.5 w-3.5 shrink-0 text-sub" />
      </button>
      {open && (
        <div className="absolute left-0 top-full z-50 mt-2 w-72 rounded-xl bg-card p-1.5 text-[12.5px] shadow-e3 ring-1 ring-line">
          <div className="px-2 pb-1 pt-0.5 text-[11px] font-medium text-sub">작업공간</div>
          {!list && !error && <div className="flex items-center gap-1.5 px-2 py-2 text-sub"><Loader2 className="h-3.5 w-3.5 animate-spin" />불러오는 중…</div>}
          {list?.workspaces.map((w) => (
            <button key={w.path} onClick={() => go(w)} disabled={!!busy}
              className={cx("flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left hover:bg-muted", w.current && "bg-muted/60")}>
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-1.5"><span className="truncate font-medium">{w.name}</span>
                  <span className="shrink-0 rounded bg-muted px-1 text-[10.5px] text-sub">{w.platform === "android" ? "Android" : "iOS"}{w.build === "release" ? " · release" : ""}</span></span>
                <span className="block truncate font-mono text-[10.5px] text-sub" title={w.path}>{home(w.path)}</span>
              </span>
              {busy === w.path ? <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" /> : w.current ? <Check className="h-3.5 w-3.5 shrink-0 text-ok" /> : null}
            </button>
          ))}
          {list && list.workspaces.length <= 1 && <div className="px-2 py-1.5 text-[11.5px] text-sub">다른 작업공간은 한 번 열면 여기에 쌓입니다</div>}
          {busy && <div className="px-2 py-1 text-[11px] text-sub">그 작업공간의 화면을 여는 중… (시뮬레이터를 켜야 하면 1~2분)</div>}
          {error && <div className="px-2 py-1 text-[11.5px] text-bad">{error}</div>}
          {list?.app ? (
            <button onClick={() => { location.href = "qakit-app://open-folder"; setOpen(false); }}
              className="mt-1 flex w-full items-center gap-2 rounded-lg border-t border-line px-2 pb-1.5 pt-2 text-left hover:bg-muted">
              <FolderOpen className="h-3.5 w-3.5" />다른 폴더 열기…</button>
          ) : (
            <div className="mt-1 border-t border-line px-2 pt-2 text-[11px] text-sub">목록에 없는 작업공간: 터미널에서 <code className="font-mono">qakit -w &lt;폴더&gt; ui</code></div>
          )}
        </div>
      )}
    </div>
  );
}
