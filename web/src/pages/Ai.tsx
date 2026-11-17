import { useCallback, useEffect, useState } from "react";
import { Camera, Layers, Loader2, MonitorSmartphone, MousePointer2, RefreshCw } from "lucide-react";
import { get, screenUrl, type AiSession, type El, type Elements } from "../lib/api";
import { Sep, ToolBtn } from "../components/ToolBar";
import { aiSecs, aiWhen } from "./AiSession";
import { cx, store, stored } from "../lib/util";
import { AiActivity } from "../components/AiActivity";
import { AiChat } from "../components/AiChat";
import { RobotCursor } from "../components/RobotCursor";
import { Badge, Card, Empty, PageHeader } from "../components/ui";
import { StreamImg } from "../components/StreamImg";

const noop = () => {};

/** AI: 기기 화면 + 한 대화. 대화(바로 답) · 맡기기(혼자 QA → 보고서) · 시나리오로(확인한 흐름 저장). 지난 대화·작업은 아래 목록 */
export function Ai() {
  const [cursor, setCursor] = useState(() => stored("qakit-ai-cursor", true));
  useEffect(() => store("qakit-ai-cursor", cursor), [cursor]);
  const [wide, setWide] = useState(false);
  // 화면 구조 레이어 (라이브 세션과 같은 상자): AI가 조작하지 않을 때만 읽는다 (실행기를 같이 쓰면 AI가 느려짐)
  const [layer, setLayer] = useState(() => stored("qakit-ai-layer", false));
  useEffect(() => store("qakit-ai-layer", layer), [layer]);
  const [els, setEls] = useState<Elements | null>(null);
  const [reading, setReading] = useState(false);
  const [hover, setHover] = useState<El | null>(null);
  const [aiRunning, setAiRunning] = useState(false);
  const readEls = useCallback(async () => {
    setReading(true);
    try { setEls(await get<Elements>("/api/elements")); } catch { /* 다음에 */ }
    setReading(false);
  }, []);
  useEffect(() => {   // AI가 도는지 (끝나면 레이어를 다시 읽는다)
    let alive = true, t: ReturnType<typeof setTimeout>;
    const loop = async () => {
      try { const st = await get<{ running: boolean }>("/api/ai/job?since=1000000"); if (alive) setAiRunning(st.running); } catch { /* 다음에 */ }
      if (alive) t = setTimeout(loop, 2500);
    };
    loop();
    return () => { alive = false; clearTimeout(t); };
  }, []);
  useEffect(() => { if (layer && !aiRunning) readEls(); }, [layer, aiRunning, readEls]);
  const [note, setNote] = useState<string | null>(null);
  useEffect(() => { if (!note) return; const t = setTimeout(() => setNote(null), 5000); return () => clearTimeout(t); }, [note]);
  const saveShot = async () => {   // 지금 화면을 내 컴퓨터로 (라이브 세션과 같음)
    try {
      const r = await fetch(screenUrl(), { cache: "no-store" });
      if (!r.ok) throw new Error(String(r.status));
      const url = URL.createObjectURL(await r.blob());
      const a = document.createElement("a"); a.href = url; a.download = `qakit-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.jpg`;
      document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 5000);
      setNote("사진을 내려받았습니다");
    } catch (e) { setNote(`사진 저장 실패: ${(e as Error).message}`); }
  };
  const [past, setPast] = useState<AiSession[] | null>(null);
  const loadPast = useCallback(() => { get<AiSession[]>("/api/ai/sessions").then(setPast).catch(() => {}); }, []);
  useEffect(() => { loadPast(); const t = setInterval(loadPast, 15000); return () => clearInterval(t); }, [loadPast]);

  return (
    <>
      <PageHeader title="AI" description="말로 시키면 AI(Claude Code)가 qakit 도구로 앱을 직접 조작합니다. 짧은 건 대화로, 오래 걸리는 QA는 맡기기로, 확인한 흐름은 시나리오로 남깁니다. 사용량은 그 AI 계정에서 씁니다." />
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_460px]">
        <div className="min-w-0 space-y-4">
          <div className="flex items-start justify-center gap-4">
            {/* 세로 도구 막대 (라이브 세션과 같은 모양) */}
            <div className="sticky top-4 z-30 flex flex-col gap-0.5 rounded-xl bg-card p-1 ring-1 ring-line">
              <ToolBtn label={`레이어 ${layer ? "끄기" : "켜기"} — 화면 요소 상자 (파랑: ID 있음, 노랑 점선: ID 없음)`} active={layer} onClick={() => setLayer(!layer)}>
                <Layers className="h-4 w-4" /></ToolBtn>
              <ToolBtn label={aiRunning ? "AI가 조작하는 동안은 끝나면 다시 읽습니다" : "화면 구조 다시 읽기"} onClick={() => { setLayer(true); readEls(); }} disabled={reading || aiRunning}>
                {reading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}</ToolBtn>
              <Sep />
              <ToolBtn label={`커서 ${cursor ? "끄기" : "켜기"} — AI가 누르는 자리`} active={cursor} onClick={() => setCursor(!cursor)}>
                <MousePointer2 className="h-4 w-4" /></ToolBtn>
              <Sep />
              <ToolBtn label="사진 내려받기" onClick={saveShot}><Camera className="h-4 w-4" /></ToolBtn>
              <ToolBtn label="라이브 세션에서 직접 조작" onClick={() => { location.hash = "#/live"; }}><MonitorSmartphone className="h-4 w-4" /></ToolBtn>
            </div>
            <div className="w-full min-w-0 space-y-2">
          <div className={cx("mx-auto w-full bg-neutral-900 shadow-e3 ring-1 ring-black/40", wide ? "max-w-[880px] rounded-[30px] p-[9px]" : "max-w-[360px] rounded-[44px] p-[11px]")}>
            <div className={cx("relative overflow-hidden bg-black", wide ? "rounded-[22px]" : "rounded-[34px]")}>
              <StreamImg src="/api/stream?k=ai" alt="기기 화면 (실시간)" className="block w-full" style={{ aspectRatio: wide ? undefined : "9 / 19.5" }}
                onLoad={(e) => { const { naturalWidth: w, naturalHeight: h } = e.currentTarget; if (w && h && (w > h) !== wide) setWide(w > h); }} />
              {layer && els?.screen && (() => { const scr = els.screen; return (
                <div className={cx("absolute inset-0", aiRunning && "opacity-40")} onMouseLeave={() => setHover(null)}>
                  {els.elements.map((e, i) => (
                    <div key={i} onMouseEnter={() => setHover(e)}
                      className={cx("absolute rounded-[3px] border", e === hover ? "border-sky-400 bg-sky-400/15"
                        : e.id && !e.id.startsWith("_Tt") ? "border-sky-400/50" : "border-dashed border-amber-400/50")}
                      style={{ left: `${(e.x / scr.w) * 100}%`, top: `${(e.y / scr.h) * 100}%`, width: `${(e.w / scr.w) * 100}%`, height: `${(e.h / scr.h) * 100}%` }} />
                  ))}
                </div>); })()}
              <RobotCursor enabled={cursor} />
            </div>
          </div>
          {layer && <div className="min-h-[1.25rem] text-center text-[11.5px] text-sub">
            {hover ? <><code className="font-mono">{hover.type}{hover.id ? ` #${hover.id}` : ""}</code>{hover.label ? ` "${hover.label}"` : ""}</>
              : aiRunning ? "AI가 조작하는 중 — 끝나면 레이어를 다시 읽습니다" : els ? `요소 ${els.elements.length}개 · 상자에 마우스를 올리면 이름` : "화면 구조 읽는 중…"}
          </div>}
          {note && <div className="text-center text-[11.5px] text-sub">{note}</div>}
            </div>
          </div>
          <AiActivity onBusy={noop} />
          <Card title="지난 대화·작업" actions={<span className="text-[11px] text-sub">results/ai/</span>}>
            {past == null ? <Empty>불러오는 중…</Empty> : past.length === 0 ? <Empty>아직 없습니다 (터미널의 Claude Code·Codex가 qakit mcp로 한 것도 여기에 쌓입니다)</Empty> : (
              <div className="max-h-80 divide-y divide-line overflow-auto">
                {past.map((s) => (
                  <a key={s.name} href={`#/${s.dir}`} className="flex items-center gap-3 px-4 py-2.5 hover:bg-muted/50">
                    <span className="w-24 shrink-0 font-mono text-[11px] text-sub">{aiWhen(s.started)}</span>
                    <span className="min-w-0 flex-1">
                      <span className="flex min-w-0 items-center gap-1.5"><span className="truncate text-[13px]">{s.goal ?? "(터미널에서 연결)"}</span>
                        {s.mode === "scenario" && <Badge>시나리오</Badge>}{(s.mode as string) === "chat" && <Badge>대화</Badge>}</span>
                      <span className="text-[11px] text-sub">{s.client ?? "AI"} · 도구 {s.calls}번{s.seconds != null ? ` · ${aiSecs(s.seconds)}` : ""}{s.saved.length ? ` · 시나리오 ${s.saved.length}개 저장` : ""}</span>
                    </span>
                    {s.issues > 0 ? <Badge tone="bad">문제 {s.issues}</Badge> : s.report ? <Badge>보고서</Badge> : null}
                  </a>
                ))}
              </div>
            )}
          </Card>
        </div>
        <div className="xl:sticky xl:top-4 xl:self-start"><AiChat /></div>
      </div>
    </>
  );
}
