import { useEffect, useState, type ReactNode } from "react";
import { ChartPie, Bot, History, ListChecks, MonitorSmartphone, Smartphone, GitBranch, Loader2, FileCode2, PanelLeft, Sun, Moon, Monitor, ChevronRight, BookOpen } from "lucide-react";
import { cx, store, stored } from "../lib/util";
import type { Info } from "../lib/api";
import { getTheme, setTheme, type Theme } from "../lib/theme";
import { WorktreePanel } from "./WorktreePanel";

type NavItem = { id: string; href: string; label: string; icon: typeof Bot };
const GROUPS: { label: string; items: NavItem[] }[] = [
  { label: "QA", items: [
    { id: "live", href: "#/live", label: "라이브 세션", icon: MonitorSmartphone },
    { id: "ai", href: "#/ai", label: "AI", icon: Bot },
  ] },
  { label: "시나리오", items: [
    { id: "scenarios", href: "#/scenarios", label: "시나리오", icon: ListChecks },
    { id: "coverage", href: "#/coverage", label: "커버리지", icon: ChartPie },
    { id: "edit", href: "#/edit", label: "편집", icon: FileCode2 },
  ] },
  { label: "결과", items: [
    { id: "runs", href: "#/runs", label: "실행 기록", icon: History },
  ] },
];
export const NAV_LABEL: Record<string, string> = Object.fromEntries(GROUPS.flatMap((g) => g.items.map((i) => [i.id, i.label])));

const THEMES: { id: Theme; icon: typeof Sun; label: string }[] = [
  { id: "light", icon: Sun, label: "밝게" }, { id: "dark", icon: Moon, label: "어둡게" }, { id: "system", icon: Monitor, label: "시스템" },
];

function ThemeSwitch() {
  const [t, setT] = useState<Theme>(getTheme);
  return (
    <div className="flex items-center rounded-md p-0.5 ring-1 ring-line" role="radiogroup" aria-label="테마">
      {THEMES.map(({ id, icon: Icon, label }) => (
        <button key={id} role="radio" aria-checked={t === id} title={label} onClick={() => { setTheme(id); setT(id); }}
          className={cx("rounded p-1", t === id ? "bg-muted text-fg" : "text-sub hover:text-fg")}><Icon className="h-3.5 w-3.5" /></button>
      ))}
    </div>
  );
}

/** 틀: 왼쪽 메뉴(그룹·접기) + 위쪽 머리 줄(위치 경로·실행 중·테마) */
export function Layout({ active, info, running, crumbs, children }:
  { active: string; info: Info | null; running: boolean; crumbs: string[]; children: ReactNode }) {
  const [narrow, setNarrow] = useState(() => stored("qakit-side-narrow", false));
  useEffect(() => store("qakit-side-narrow", narrow), [narrow]);
  return (
    <div className="flex h-full">
      <aside className={cx("flex shrink-0 flex-col border-r border-line bg-side transition-[width] duration-150", narrow ? "w-[56px]" : "w-60")}>
        <div className={cx("flex h-12 items-center gap-2", narrow ? "justify-center" : "px-4")}>
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-fg"><Smartphone className="h-4 w-4" /></div>
          {!narrow && <div className="min-w-0 leading-tight">
            <div className="text-[14px] font-semibold tracking-head">qakit</div>
            <div className="truncate text-[11px] text-sub">{info?.name ?? "…"}</div>
          </div>}
        </div>
        <nav className="flex flex-1 flex-col gap-4 overflow-y-auto px-2 py-3">
          {GROUPS.map((g) => (
            <div key={g.label}>
              {!narrow && <div className="mb-1 px-2.5 text-[11px] font-medium text-sub">{g.label}</div>}
              <div className="flex flex-col gap-0.5">
                {g.items.map(({ id, href, label, icon: Icon }) => (
                  <a key={id} href={href} title={narrow ? label : undefined}
                    className={cx("flex items-center gap-2.5 rounded-md py-1.5 text-[13px] transition-colors", narrow ? "justify-center px-0" : "px-2.5",
                      active === id ? "bg-muted font-medium text-fg" : "text-sub hover:bg-muted/60 hover:text-fg")}>
                    <Icon className="h-4 w-4 shrink-0" />
                    {!narrow && label}
                    {!narrow && id === "scenarios" && running && <Loader2 className="ml-auto h-3.5 w-3.5 animate-spin text-sub" />}
                  </a>
                ))}
              </div>
            </div>
          ))}
        </nav>
        {!narrow && (
          <div className="space-y-1.5 border-t border-line p-3 text-[11px] text-sub">
            <div className="flex items-center gap-1.5 px-1"><MonitorSmartphone className="h-3.5 w-3.5" />{info?.device ? `실기기 ${info.device}` : info?.simulator ?? "…"}</div>
            <WorktreePanel fallback={info?.app?.branch && (
              <div className="flex items-center gap-1.5 px-1 font-mono"><GitBranch className="h-3.5 w-3.5" />{info.app.branch}@{info.app.commit}
                {info.app.dirtyFiles ? <span className="text-warn">±{info.app.dirtyFiles}</span> : null}</div>
            )} />
            <div className="px-1 font-mono">qakit {info?.kit ?? ""}</div>
          </div>
        )}
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 shrink-0 items-center gap-2 border-b border-line px-4">
          <button onClick={() => setNarrow(!narrow)} title={narrow ? "메뉴 펼치기" : "메뉴 접기"} className="rounded-md p-1.5 text-sub hover:bg-muted hover:text-fg">
            <PanelLeft className="h-4 w-4" /></button>
          <nav className="flex min-w-0 items-center gap-1 text-[13px]" aria-label="위치">
            {crumbs.map((c, i) => (
              <span key={i} className="flex min-w-0 items-center gap-1">
                {i > 0 && <ChevronRight className="h-3.5 w-3.5 shrink-0 text-sub/60" />}
                <span className={cx("truncate", i === crumbs.length - 1 ? "font-medium text-fg" : "text-sub")}>{c}</span>
              </span>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            {running && <a href="#/live" className="flex items-center gap-1.5 rounded-full bg-muted px-2.5 py-1 text-[12px] text-fg hover:bg-line">
              <span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-ok opacity-60" /><span className="relative inline-flex h-2 w-2 rounded-full bg-ok" /></span>
              실행 중</a>}
            <ThemeSwitch />
            <a href="https://github.com/indextrown/qa-kit#readme" target="_blank" rel="noreferrer" title="qakit 문서 (README)" className="rounded-md p-1.5 text-sub hover:bg-muted hover:text-fg"><BookOpen className="h-4 w-4" /></a>
          </div>
        </header>
        <main className="min-w-0 flex-1 overflow-auto">
          <div className="mx-auto max-w-[1440px] px-8 py-7">{children}</div>
        </main>
      </div>
    </div>
  );
}
