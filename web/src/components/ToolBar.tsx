import { cx } from "../lib/util";

export function Sep() { return <span className="mx-1.5 my-0.5 h-px bg-line" />; }

/** 세로 도구 막대 버튼: 아이콘만, 마우스를 올리면 오른쪽에 이름 */
export function ToolBtn({ label, onClick, active, danger, disabled, children }:
  { label: string; onClick: () => void; active?: boolean; danger?: boolean; disabled?: boolean; children: React.ReactNode }) {
  return (
    <button onClick={onClick} disabled={disabled} aria-label={label}
      className={cx("group relative flex h-9 w-9 items-center justify-center rounded-lg transition-colors disabled:opacity-40",
        danger ? "bg-bad/10 text-bad" : active ? "bg-muted text-fg" : "text-sub hover:bg-muted hover:text-fg")}>
      {children}
      {/* 이름표는 오른쪽(기기 위)에 — 왼쪽은 창이 좁으면 메뉴 칸에 잘려 글자가 겹쳤다 (맥 앱 창). 도구 막대가 z-30이라 기기 위로 올라온다 */}
      <span className="pointer-events-none absolute left-full top-1/2 z-50 ml-2 -translate-y-1/2 whitespace-nowrap rounded-md bg-fg px-2 py-1 text-[11.5px] text-bg opacity-0 shadow-e3 transition-opacity group-hover:opacity-100">{label}</span>
    </button>
  );
}
