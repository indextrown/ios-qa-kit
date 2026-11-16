import { useCallback, useEffect, useState } from "react";
import { MousePointer2 } from "lucide-react";
import { get, type AiSession } from "../lib/api";
import { aiSecs, aiWhen } from "./AiSession";
import { cx, store, stored } from "../lib/util";
import { AiActivity } from "../components/AiActivity";
import { AiChat } from "../components/AiChat";
import { RobotCursor } from "../components/RobotCursor";
import { Badge, Button, Card, Empty, PageHeader } from "../components/ui";

const noop = () => {};

/** AI: 기기 화면 + 한 대화. 대화(바로 답) · 맡기기(혼자 QA → 보고서) · 시나리오로(확인한 흐름 저장). 지난 대화·작업은 아래 목록 */
export function Ai() {
  const [cursor, setCursor] = useState(() => stored("qakit-ai-cursor", true));
  useEffect(() => store("qakit-ai-cursor", cursor), [cursor]);
  const [wide, setWide] = useState(false);
  const [past, setPast] = useState<AiSession[] | null>(null);
  const loadPast = useCallback(() => { get<AiSession[]>("/api/ai/sessions").then(setPast).catch(() => {}); }, []);
  useEffect(() => { loadPast(); const t = setInterval(loadPast, 15000); return () => clearInterval(t); }, [loadPast]);

  return (
    <>
      <PageHeader title="AI" description="말로 시키면 AI(Claude Code)가 qakit 도구로 앱을 직접 조작합니다. 짧은 건 대화로, 오래 걸리는 QA는 맡기기로, 확인한 흐름은 시나리오로 남깁니다. 사용량은 그 AI 계정에서 씁니다." />
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_460px]">
        <div className="min-w-0 space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-[12px] text-sub">AI가 누르는 자리로 커서가 움직입니다 · 직접 조작은 <a href="#/live" className="text-link hover:underline">라이브 세션</a></span>
            <Button size="sm" variant="ghost" onClick={() => setCursor(!cursor)} className={cx(cursor ? "bg-muted font-medium" : "text-sub")}>
              <MousePointer2 className="h-3.5 w-3.5" />커서 {cursor ? "켬" : "끔"}</Button>
          </div>
          <div className={cx("mx-auto w-full bg-neutral-900 shadow-e3 ring-1 ring-black/40", wide ? "max-w-[880px] rounded-[30px] p-[9px]" : "max-w-[360px] rounded-[44px] p-[11px]")}>
            <div className={cx("relative overflow-hidden bg-black", wide ? "rounded-[22px]" : "rounded-[34px]")}>
              <img src="/api/stream?k=ai" alt="기기 화면 (실시간)" className="block w-full" style={{ aspectRatio: wide ? undefined : "9 / 19.5" }}
                onLoad={(e) => { const { naturalWidth: w, naturalHeight: h } = e.currentTarget; if (w && h && (w > h) !== wide) setWide(w > h); }} />
              <RobotCursor enabled={cursor} />
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
