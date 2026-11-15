import { useCallback, useEffect, useMemo, useState } from "react";
import { Camera, RefreshCw, Search } from "lucide-react";
import { get, type Run } from "../lib/api";
import { cx, secs, when } from "../lib/util";
import { Button, Card, Empty, PageHeader, Spinner, StatusBadge, Badge, th, td } from "../components/ui";

export function Runs() {
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"" | "Passed" | "Failed">("");
  const [text, setText] = useState("");
  const load = useCallback(() => {
    setError(null);
    get<Run[]>("/api/runs?limit=300").then(setRuns).catch((e) => setError(String(e.message)));
  }, []);
  useEffect(load, [load]);

  const rows = useMemo(() => (runs ?? []).filter((r) => (!filter || r.result === filter)
    && (!text || r.name.toLowerCase().includes(text.toLowerCase()))), [runs, filter, text]);
  const failed = (runs ?? []).filter((r) => r.result === "Failed").length;

  return (
    <>
      <PageHeader title="실행 기록" description="results/ 폴더와 실행 기록(history.jsonl). 행을 누르면 원인·스크린샷·단계별 시간을 봅니다."
        actions={<Button onClick={load}><RefreshCw className="h-3.5 w-3.5" />새로고침</Button>} />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="inline-flex rounded-md bg-card p-0.5 shadow-e1">
          {([["", `전체 ${runs?.length ?? 0}`], ["Failed", `실패 ${failed}`], ["Passed", "통과"]] as const).map(([v, label]) => (
            <button key={v} onClick={() => setFilter(v)}
              className={cx("rounded px-3 py-1 text-[12px]", filter === v ? "bg-muted font-medium" : "text-sub hover:text-fg")}>{label}</button>
          ))}
        </div>
        <label className="flex h-8 items-center gap-2 rounded-md bg-card px-2.5 shadow-e1">
          <Search className="h-3.5 w-3.5 text-sub" />
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder="시나리오 이름" className="w-56 bg-transparent text-[13px] outline-none placeholder:text-sub" />
        </label>
      </div>
      <Card>
        {error ? <Empty>불러오지 못함: {error}</Empty> : runs == null ? <Spinner /> : rows.length === 0 ? <Empty>맞는 실행이 없습니다</Empty> : (
          <table className="w-full">
            <thead className="border-b border-line"><tr>
              <th className={th}>결과</th><th className={th}>시나리오</th><th className={th}>종류</th>
              <th className={th}>시작</th><th className={cx(th, "text-right")}>시간</th><th className={th}>경로</th>
            </tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.dir} onClick={() => { location.hash = `#/run/${r.dir}`; }}
                  className="cursor-pointer border-b border-line last:border-0 hover:bg-muted/50">
                  <td className={td}><span className="inline-flex items-center gap-1.5"><StatusBadge result={r.result} />{r.screenshot && <Camera className="h-3.5 w-3.5 text-sub" />}</span></td>
                  <td className={cx(td, "font-medium")}>{r.name}{r.device && <Badge className="ml-2">{r.device}</Badge>}</td>
                  <td className={cx(td, "text-sub")}>{r.kind}</td>
                  <td className={cx(td, "font-mono text-[12px] text-sub")}>{when(r.start)}</td>
                  <td className={cx(td, "text-right font-mono text-[12px]")}>{secs(r.seconds)}</td>
                  <td className={cx(td, "text-[12px] text-sub")}>{r.via}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
