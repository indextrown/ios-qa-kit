import { useCallback, useEffect, useRef, useState } from "react";
import { get, type Info, type Job } from "./lib/api";
import { useHash } from "./lib/util";
import { Layout } from "./components/Layout";
import { Runs } from "./pages/Runs";
import { RunDetail } from "./pages/RunDetail";
import { Scenarios } from "./pages/Scenarios";
import { Live } from "./pages/Live";
import { AiQa } from "./pages/AiQa";
import { AiSession } from "./pages/AiSession";
import { Coverage } from "./pages/Coverage";
import { Editor } from "./pages/Editor";
import { post } from "./lib/api";

export function App() {
  const hash = useHash();
  const [info, setInfo] = useState<Info | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const from = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => { get<Info>("/api/info").then(setInfo).catch(() => {}); }, []);

  // 실행 상태: 실행 중이면 1초, 아니면 5초마다 (새 출력 줄만 받아 붙인다)
  const pollJob = useCallback(async () => {
    clearTimeout(timer.current);
    try {
      const st = await get<Job>(`/api/job?from=${from.current}`);
      setJob((prev) => {
        const restarted = prev?.started !== st.started;
        const lines = restarted ? st.lines : [...(prev?.lines ?? []), ...st.lines];
        return { ...st, lines };
      });
      from.current = st.total;
      timer.current = setTimeout(pollJob, st.running ? 1000 : 5000);
    } catch { timer.current = setTimeout(pollJob, 5000); }
  }, []);
  useEffect(() => { pollJob(); return () => clearTimeout(timer.current); }, [pollJob]);
  const refreshJob = useCallback(() => { from.current = 0; setJob(null); pollJob(); }, [pollJob]);

  const active = hash.startsWith("#/run/") ? "runs" : hash.slice(2).split("/")[0] || "live";   // 처음 열면 라이브 세션
  let page;
  if (hash.startsWith("#/run/")) page = <RunDetail dir={decodeURIComponent(hash.slice(6))} />;
  else if (active === "ai") page = hash.startsWith("#/ai/") ? <AiSession name={decodeURIComponent(hash.slice(5))} job={job} refreshJob={refreshJob} /> : <AiQa />;
  else if (active === "coverage") page = <Coverage />;
  else if (active === "scenarios") page = <Scenarios job={job} refreshJob={refreshJob} />;
  else if (active === "live" || !hash.slice(2)) page = <Live job={job} refreshJob={refreshJob} />;
  else if (active === "edit") page = <Editor route={hash} runScenario={async (name) => {
    try { await post("/api/run", { scenarios: [name], options: { reuse: false, precheck: false } }); refreshJob(); location.hash = "#/scenarios"; }
    catch (e) { alert(`실행하지 못함: ${(e as Error).message}`); }
  }} />;
  else page = <Runs />;
  return <Layout active={active} info={info} running={!!job?.running}>{page}</Layout>;
}
