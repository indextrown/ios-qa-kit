import { useEffect, useRef, useState } from "react";
import { MousePointer2 } from "lucide-react";
import { get } from "../lib/api";

interface Touch { t: number; kind: string; x: number; y: number; w: number; h: number; sw: number; sh: number }
type Mark = { x: number; y: number; kind: string; k: number };

const at = (n: Touch): Omit<Mark, "k"> => ({ x: ((n.x + n.w / 2) / n.sw) * 100, y: ((n.y + n.h / 2) / n.sh) * 100, kind: n.kind });
const RECENT = 3;      // 화면을 연 직후에도 이 초 안의 탭은 보여 준다 (시나리오 실행을 누르고 넘어오는 사이)

/** 실행기가 누르는 자리(.qakit/taps.jsonl)로 움직이는 커서 — 화면 위에 absolute로 겹쳐 그린다.
 *  실행기는 누르기 직전("tap"·"swipe-…")과 직후("tap-done")를 남긴다 → 직전에 커서를 옮기고, 직후에 누름 표시.
 *  기다리는 줄 없이 들어오는 대로 (늦게 보여 주면 화면은 이미 넘어갔는데 커서가 이전 자리를 누르는 것처럼 보임). */
export function RobotCursor({ enabled, size = "h-6 w-6" }: { enabled: boolean; size?: string }) {
  const [robot, setRobot] = useState<Mark | null>(null);
  const [ripples, setRipples] = useState<Mark[]>([]);
  const [dot, setDot] = useState<Mark | null>(null);
  const pending = useRef<number | null>(null);   // tap-done이 안 오는 옛 실행기용 대비

  useEffect(() => {
    if (!enabled) return;
    let alive = true, offset = 0, first = true, t: ReturnType<typeof setTimeout>;
    const press = (p: Omit<Mark, "k">) => {
      const m = { ...p, k: Date.now() + Math.random() };
      setRipples((q) => [...q, m]); setDot(m);
      setTimeout(() => setRipples((q) => q.filter((x) => x.k !== m.k)), 800);
    };
    const handle = (n: Touch) => {
      const p = at(n);
      if (n.kind === "tap-done" || n.kind === "press-done") {
        if (pending.current) { clearTimeout(pending.current); pending.current = null; }
        setRobot({ ...p, kind: "tap", k: Date.now() });
        press(p);
        return;
      }
      if (n.kind === "drag-done") { setRobot({ ...p, kind: "drag", k: Date.now() }); return; }   // 직접 터치 끌기: 시작 → 끝으로 미끄러짐
      setRobot({ ...p, k: Date.now() });
      if (n.kind === "tap" || n.kind === "press") {
        if (pending.current) clearTimeout(pending.current);
        pending.current = window.setTimeout(() => { pending.current = null; if (alive) press(p); }, 3000);   // tap-done이 안 오는 옛 실행기만
      }
    };
    const poll = async () => {
      try {
        const r = await get<{ offset: number; taps: Touch[] }>(`/api/taps?since=${offset}`);
        const now = Date.now() / 1000;
        const fresh = first ? r.taps.filter((x) => now - x.t < RECENT) : r.taps;
        first = false;
        offset = r.offset;
        fresh.slice(-6).forEach((n, i) => (i ? setTimeout(() => alive && handle(n), i * 120) : handle(n)));
      } catch { /* 다음에 */ }
      if (alive) t = setTimeout(poll, 150);
    };
    poll();
    return () => { alive = false; clearTimeout(t); if (pending.current) clearTimeout(pending.current); };
  }, [enabled]);
  useEffect(() => { if (!robot) return; const t = setTimeout(() => setRobot(null), 1500); return () => clearTimeout(t); }, [robot]);
  useEffect(() => { if (!dot) return; const t = setTimeout(() => setDot(null), 1500); return () => clearTimeout(t); }, [dot]);

  if (!enabled) return null;
  return (
    <div className="pointer-events-none absolute inset-0">
      {dot && <div className="absolute h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-rose-500 ring-2 ring-white/80" style={{ left: `${dot.x}%`, top: `${dot.y}%` }} />}
      {ripples.map((r) => <div key={r.k} className="qakit-ripple absolute h-10 w-10 rounded-full border-2 border-rose-500 bg-rose-500/25" style={{ left: `${r.x}%`, top: `${r.y}%` }} />)}
      {robot && (
        <div className={`absolute z-10 transition-[left,top] ease-out ${robot.kind === "drag" ? "duration-500" : "duration-200"}`} style={{ left: `${robot.x}%`, top: `${robot.y}%` }}>
          <MousePointer2 className={`${size} -translate-x-[18%] -translate-y-[18%] fill-neutral-900 text-white drop-shadow-[0_1px_2px_rgba(0,0,0,0.5)]`} strokeWidth={1.5} />
          {(robot.kind === "press" || robot.kind === "drag") && <span className="absolute left-5 top-4 whitespace-nowrap rounded bg-neutral-900/80 px-1.5 py-0.5 text-[10px] text-white">
            {robot.kind === "press" ? "길게 누르기" : "끌기"}</span>}
          {robot.kind.startsWith("swipe") && <span className="absolute left-5 top-4 whitespace-nowrap rounded bg-neutral-900/80 px-1.5 py-0.5 text-[10px] text-white">
            쓸기 {({ "swipe-up": "↑", "swipe-down": "↓", "swipe-left": "←", "swipe-right": "→" } as Record<string, string>)[robot.kind] ?? ""}</span>}
        </div>
      )}
    </div>
  );
}
