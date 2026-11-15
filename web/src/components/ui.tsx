import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { cx } from "../lib/util";
import type { Result } from "../lib/api";

type Variant = "primary" | "secondary" | "ghost" | "danger";
const VARIANT: Record<Variant, string> = {
  primary: "bg-primary text-primary-fg hover:opacity-90",
  secondary: "bg-card text-fg shadow-e1 hover:bg-muted",
  ghost: "text-sub hover:text-fg hover:bg-muted",
  danger: "bg-bad text-white hover:opacity-90",
};

export function Button({ variant = "secondary", size = "md", loading, className, children, ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md"; loading?: boolean }) {
  return (
    <button
      {...rest}
      disabled={rest.disabled || loading}
      className={cx("inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors",
        "disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fg/30",
        size === "sm" ? "h-7 px-2.5 text-xs" : "h-8 px-3 text-[13px]", VARIANT[variant], className)}
    >
      {loading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
      {children}
    </button>
  );
}

export function Card({ className, children, title, actions }: { className?: string; children: ReactNode; title?: ReactNode; actions?: ReactNode }) {
  return (
    <section className={cx("rounded-lg bg-card shadow-e1", className)}>
      {(title || actions) && (
        <div className="flex items-center justify-between gap-2 border-b border-line px-4 py-2.5">
          <h3 className="text-[13px] font-semibold">{title}</h3>
          <div className="flex items-center gap-1.5">{actions}</div>
        </div>
      )}
      {children}
    </section>
  );
}

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold">{title}</h1>
        {description && <p className="mt-1 text-[13px] text-sub">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

const LABEL: Record<string, string> = { Passed: "통과", Failed: "실패", unknown: "알 수 없음" };
export function StatusBadge({ result }: { result: Result }) {
  const tone = result === "Passed" ? "text-ok bg-ok/10" : result === "Failed" ? "text-bad bg-bad/10" : "text-sub bg-muted";
  return (
    <span className={cx("inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium", tone)}>
      <span className={cx("h-1.5 w-1.5 rounded-full", result === "Passed" ? "bg-ok" : result === "Failed" ? "bg-bad" : "bg-sub")} />
      {LABEL[result] ?? result}
    </span>
  );
}

export function Badge({ children, tone = "muted", className }: { children: ReactNode; tone?: "muted" | "warn" | "bad" | "mono"; className?: string }) {
  return (
    <span className={cx("inline-flex items-center rounded px-1.5 py-0.5 text-[11px]",
      tone === "warn" ? "bg-warn/15 text-warn font-medium" : tone === "bad" ? "bg-bad/10 text-bad font-medium" : "bg-muted text-sub", tone === "mono" && "font-mono", className)}>
      {children}
    </span>
  );
}

export function Mono({ children, className }: { children: ReactNode; className?: string }) {
  return <code className={cx("font-mono text-[12px]", className)}>{children}</code>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="px-4 py-10 text-center text-[13px] text-sub">{children}</div>;
}

export function Spinner({ label }: { label?: string }) {
  return <div className="flex items-center gap-2 px-4 py-10 text-[13px] text-sub"><Loader2 className="h-4 w-4 animate-spin" />{label ?? "불러오는 중…"}</div>;
}

export function Pre({ children, className }: { children: ReactNode; className?: string }) {
  return <pre className={cx("max-h-[480px] overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted p-3 font-mono text-[12px] leading-relaxed", className)}>{children}</pre>;
}

export const th = "px-4 py-2 text-left text-[12px] font-medium text-sub";
export const td = "px-4 py-2.5 align-top";
