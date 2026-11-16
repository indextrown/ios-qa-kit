import { useEffect, useMemo, useState } from "react";
import { Bot, ChevronDown, ChevronRight, RefreshCw, Search } from "lucide-react";
import { get } from "../lib/api";
import { cx, store } from "../lib/util";
import { Badge, Button, Card, Empty, Mono, PageHeader, Spinner } from "../components/ui";

interface IdUse { id: string; scenarios: string[] }
interface Screen { screen: string; total: number; used: number; ids: IdUse[] }
interface Cov { total: number; used: number; scenarios: number; screens: Screen[]; extra: IdUse[] }

const pct = (u: number, t: number) => (t ? Math.round((u / t) * 100) : 0);

/** 앱 ID(자동 ID) 중 시나리오가 쓰는 것 — 화면별. 빈 화면은 AI QA 목표로 바로 넘긴다 */
export function Coverage() {
  const [c, setC] = useState<Cov | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [onlyGaps, setOnlyGaps] = useState(true);
  const [open, setOpen] = useState<Set<string>>(new Set());
  const load = () => { setC(null); setError(null); get<Cov>("/api/coverage").then(setC).catch((e) => setError(String(e.message))); };
  useEffect(load, []);

  const rows = useMemo(() => (c?.screens ?? []).filter((s) => (!onlyGaps || s.used < s.total)
    && (!text || `${s.screen} ${s.ids.map((x) => x.id).join(" ")}`.toLowerCase().includes(text.toLowerCase()))), [c, onlyGaps, text]);
  const toggle = (k: string) => setOpen((p) => { const s = new Set(p); if (s.has(k)) s.delete(k); else s.add(k); return s; });
  const toAi = (s: Screen, mode: "qa" | "scenario") => {
    const gaps = s.ids.filter((x) => !x.scenarios.length).map((x) => x.id);
    const list = `${gaps.slice(0, 8).join(", ")}${gaps.length > 8 ? " 등" : ""}`;
    // AI 화면 대화창에 모드·글을 넘긴다 (보내기는 사람이)
    if (mode === "scenario") store("qakit-ai-handoff", { mode: "scenario", text: `${s.screen} 화면까지 가서 아직 시나리오가 없는 요소(${list})가 보이고 눌리는지 확인하는 시나리오` });
    else {
      store("qakit-ai-handoff", { mode: "task", text: `${s.screen} 화면 QA — 아직 시나리오가 없는 요소: ${list}. 각 요소를 눌러 보고 화면이 정상으로 열리고 돌아오는지 확인하고, 확인한 경로는 시나리오로 남겨 줘.` });
      store("qakit-ai-save", true);
    }
    location.hash = "#/ai";
  };

  return (
    <>
      <PageHeader title="커버리지" description="앱 ID(자동 ID — 화면타입.프로퍼티) 중 시나리오가 쓰는 것. 빈 화면은 AI QA로 보내 탐색하고 시나리오로 남길 수 있습니다."
        actions={<Button onClick={load}><RefreshCw className="h-3.5 w-3.5" />새로고침</Button>} />
      {error ? <Card><Empty>불러오지 못함: {error}</Empty></Card> : !c ? <Card><Spinner /></Card> : (
        <>
          <div className="mb-4 grid gap-3 sm:grid-cols-3">
            <Card><div className="p-4"><div className="text-[12px] text-sub">앱 ID 중 시나리오가 쓰는 것</div>
              <div className="mt-1 text-2xl font-semibold">{pct(c.used, c.total)}% <span className="text-[13px] font-normal text-sub">{c.used} / {c.total}</span></div>
              <div className="mt-2 h-1.5 rounded-full bg-muted"><div className="h-1.5 rounded-full bg-fg/70" style={{ width: `${pct(c.used, c.total)}%` }} /></div></div></Card>
            <Card><div className="p-4"><div className="text-[12px] text-sub">화면 (시나리오가 하나라도 닿음)</div>
              <div className="mt-1 text-2xl font-semibold">{c.screens.filter((s) => s.used).length} <span className="text-[13px] font-normal text-sub">/ {c.screens.length}</span></div></div></Card>
            <Card><div className="p-4"><div className="text-[12px] text-sub">시나리오 · 앱이 직접 붙인 ID</div>
              <div className="mt-1 text-2xl font-semibold">{c.scenarios} <span className="text-[13px] font-normal text-sub">· {c.extra.length}개 (전체 수는 알 수 없음)</span></div></div></Card>
          </div>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <label className="flex h-8 items-center gap-2 rounded-md bg-card px-2.5 shadow-e1">
              <Search className="h-3.5 w-3.5 text-sub" />
              <input value={text} onChange={(e) => setText(e.target.value)} placeholder="화면·ID 검색" className="w-56 bg-transparent text-[13px] outline-none placeholder:text-sub" />
            </label>
            <label className="flex items-center gap-2 text-[13px]"><input type="checkbox" checked={onlyGaps} onChange={(e) => setOnlyGaps(e.target.checked)} />빈 곳이 있는 화면만</label>
          </div>
          <Card>
            {rows.length === 0 ? <Empty>맞는 화면이 없습니다</Empty> : (
              <div className="divide-y divide-line">
                {rows.map((s) => {
                  const isOpen = open.has(s.screen);
                  return (
                    <div key={s.screen}>
                      <div className="flex items-center gap-3 px-4 py-2.5 hover:bg-muted/40">
                        <button onClick={() => toggle(s.screen)} className="flex min-w-0 flex-1 items-center gap-2 text-left">
                          {isOpen ? <ChevronDown className="h-3.5 w-3.5 shrink-0 text-sub" /> : <ChevronRight className="h-3.5 w-3.5 shrink-0 text-sub" />}
                          <span className="truncate font-mono text-[12.5px]">{s.screen}</span>
                        </button>
                        <div className="h-1.5 w-28 shrink-0 rounded-full bg-muted"><div className={cx("h-1.5 rounded-full", s.used === s.total ? "bg-ok" : s.used ? "bg-warn" : "bg-bad/60")} style={{ width: `${Math.max(4, pct(s.used, s.total))}%` }} /></div>
                        <span className="w-14 shrink-0 text-right font-mono text-[12px] text-sub">{s.used}/{s.total}</span>
                        {s.used < s.total
                          ? <span className="flex shrink-0 gap-0.5">
                              <Button size="sm" variant="ghost" onClick={() => toAi(s, "scenario")} title="이 화면의 빈 요소를 확인하는 시나리오를 AI로 만들기"><Bot className="h-3.5 w-3.5" />AI로 시나리오</Button>
                              <Button size="sm" variant="ghost" onClick={() => toAi(s, "qa")} title="이 화면의 빈 요소를 AI QA 목표로">AI QA</Button></span>
                          : <span className="w-[190px]" />}
                      </div>
                      {isOpen && (
                        <div className="space-y-1 bg-muted/30 px-11 py-2.5">
                          {s.ids.map((x) => (
                            <div key={x.id} className="flex flex-wrap items-center gap-2 text-[12px]">
                              <span className={cx("h-2 w-2 shrink-0 rounded-full", x.scenarios.length ? "bg-ok" : "bg-line")} />
                              <Mono className="text-[12px]">{x.id}</Mono>
                              {x.scenarios.map((n) => <a key={n} href={`#/edit/scenario/${encodeURIComponent(n)}`} className="font-mono text-[11px] text-link hover:underline">{n}</a>)}
                              {!x.scenarios.length && <span className="text-[11px] text-sub">시나리오 없음</span>}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </Card>
          {c.extra.length > 0 && (
            <Card className="mt-4" title="그 밖에 시나리오가 쓰는 ID (앱이 직접 붙인 것)" actions={<Badge>{c.extra.length}</Badge>}>
              <div className="space-y-1 p-4">
                {c.extra.map((x) => (
                  <div key={x.id} className="flex flex-wrap items-center gap-2 text-[12px]"><Mono className="text-[12px]">{x.id}</Mono>
                    <span className="text-[11px] text-sub">{x.scenarios.length}개 시나리오</span></div>
                ))}
              </div>
            </Card>
          )}
        </>
      )}
    </>
  );
}
