import type { ReactNode } from "react";
import { History, ListChecks, MonitorSmartphone, Smartphone, GitBranch, Loader2, FileCode2 } from "lucide-react";
import { cx } from "../lib/util";
import type { Info } from "../lib/api";

const NAV = [
  { id: "live", href: "#/live", label: "라이브 세션", icon: MonitorSmartphone },
  { id: "scenarios", href: "#/scenarios", label: "시나리오", icon: ListChecks },
  { id: "edit", href: "#/edit", label: "편집", icon: FileCode2 },
  { id: "runs", href: "#/runs", label: "실행 기록", icon: History },
];

export function Layout({ active, info, running, children }: { active: string; info: Info | null; running: boolean; children: ReactNode }) {
  return (
    <div className="flex h-full">
      <aside className="flex w-60 shrink-0 flex-col border-r border-line bg-card">
        <div className="flex h-14 items-center gap-2 border-b border-line px-4">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-primary-fg">
            <Smartphone className="h-4 w-4" />
          </div>
          <div className="leading-tight">
            <div className="text-[14px] font-semibold tracking-head">qakit</div>
            <div className="max-w-[160px] truncate text-[11px] text-sub">{info?.name ?? "…"}</div>
          </div>
        </div>
        <nav className="flex flex-1 flex-col gap-0.5 p-2">
          {NAV.map(({ id, href, label, icon: Icon }) => (
            <a key={id} href={href}
              className={cx("flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[13px] transition-colors",
                active === id ? "bg-muted font-medium text-fg" : "text-sub hover:bg-muted/60 hover:text-fg")}>
              <Icon className="h-4 w-4" />
              {label}
              {id === "scenarios" && running && <Loader2 className="ml-auto h-3.5 w-3.5 animate-spin text-sub" />}
            </a>
          ))}
        </nav>
        <div className="space-y-1.5 border-t border-line p-3 text-[11px] text-sub">
          <div className="flex items-center gap-1.5"><MonitorSmartphone className="h-3.5 w-3.5" />{info?.device ? `실기기 ${info.device}` : info?.simulator ?? "…"}</div>
          {info?.app?.branch && (
            <div className="flex items-center gap-1.5 font-mono"><GitBranch className="h-3.5 w-3.5" />{info.app.branch}@{info.app.commit}
              {info.app.dirtyFiles ? <span className="text-warn">±{info.app.dirtyFiles}</span> : null}</div>
          )}
          <div className="font-mono">qakit {info?.kit ?? ""}</div>
        </div>
      </aside>
      <main className="min-w-0 flex-1 overflow-auto">
        <div className="mx-auto max-w-[1400px] px-8 py-7">{children}</div>
      </main>
    </div>
  );
}
