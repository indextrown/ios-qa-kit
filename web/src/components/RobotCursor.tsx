import { useEffect, useRef, useState } from "react";
import { MousePointer2 } from "lucide-react";
import { get } from "../lib/api";

interface Touch { t: number; kind: string; x: number; y: number; w: number; h: number; sw: number; sh: number }
type Mark = { x: number; y: number; kind: string; k: number };

/** 실행기가 누르는 자리(.qakit/taps.jsonl)로 움직이는 커서 — 화면 위에 absolute로 겹쳐 그린다. 라이브 세션과 같은 표시. */
export function RobotCursor({ enabled }: { enabled: boolean }) {
  const queue = useRef<Touch[]>([]);
  const [robot, setRobot] = useState<Mark | null>(null);
  const [ripples, setRipples] = useState<Mark[]>([]);
  const [dot, setDot] = useState<Mark | null>(null);

  useEffect(() => {   // 새 기록만 읽어 큐에
    if (!enabled) return;
    let alive = true, offset = -1, t: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const r = await get<{ offset: number; taps: Touch[] }>(`/api/taps?since=${offset}`);
        if (offset >= 0) queue.current.push(...r.taps.slice(-6));
        offset = r.offset;
      } catch { /* 다음에 */ }
      if (alive) t = setTimeout(poll, 300);
    };
    poll();
    return () => { alive = false; clearTimeout(t); queue.current = []; };
  }, [enabled]);
  useEffect(() => {   // 하나씩: 커서 이동 → 누름 표시
    if (!enabled) return;
    let alive = true, t: ReturnType<typeof setTimeout>;
    const step = () => {
      const n = queue.current.shift();
      if (n) {
        const p = { x: ((n.x + n.w / 2) / n.sw) * 100, y: ((n.y + n.h / 2) / n.sh) * 100, kind: n.kind, k: Date.now() };
        setRobot(p);
        if (n.kind === "tap") setTimeout(() => {
          if (!alive) return;
          setRipples((q) => [...q, p]); setDot(p);
          setTimeout(() => setRipples((q) => q.filter((x) => x.k !== p.k)), 800);
        }, 350);
      }
      if (alive) t = setTimeout(step, n ? 650 : 100);
    };
    step();
    return () => { alive = false; clearTimeout(t); };
  }, [enabled]);
  useEffect(() => { if (!robot) return; const t = setTimeout(() => setRobot(null), 1500); return () => clearTimeout(t); }, [robot]);
  useEffect(() => { if (!dot) return; const t = setTimeout(() => setDot(null), 1500); return () => clearTimeout(t); }, [dot]);

  if (!enabled) return null;
  return (
    <div className="pointer-events-none absolute inset-0">
      {dot && <div className="absolute h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-rose-500 ring-2 ring-white/80" style={{ left: `${dot.x}%`, top: `${dot.y}%` }} />}
      {ripples.map((r) => <div key={r.k} className="qakit-ripple absolute h-10 w-10 rounded-full border-2 border-rose-500 bg-rose-500/25" style={{ left: `${r.x}%`, top: `${r.y}%` }} />)}
      {robot && (
        <div className="absolute z-10 transition-[left,top] duration-300 ease-out" style={{ left: `${robot.x}%`, top: `${robot.y}%` }}>
          <MousePointer2 className="h-6 w-6 -translate-x-[3px] -translate-y-[3px] fill-neutral-900 text-white drop-shadow-[0_1px_2px_rgba(0,0,0,0.5)]" strokeWidth={1.5} />
          {robot.kind.startsWith("swipe") && <span className="absolute left-5 top-4 whitespace-nowrap rounded bg-neutral-900/80 px-1.5 py-0.5 text-[10px] text-white">
            쓸기 {({ "swipe-up": "↑", "swipe-down": "↓", "swipe-left": "←", "swipe-right": "→" } as Record<string, string>)[robot.kind] ?? ""}</span>}
        </div>
      )}
    </div>
  );
}
