import { useEffect, useState } from "react";
import { ArrowLeft, FileText } from "lucide-react";
import { fileUrl, get, type Run, type RunDetail as Detail } from "../lib/api";
import { cx, secs, when } from "../lib/util";
import { Button, Card, Empty, Mono, Pre, Spinner, StatusBadge } from "../components/ui";

export function RunDetail({ dir }: { dir: string }) {
  const [d, setD] = useState<Detail | null>(null);
  const [meta, setMeta] = useState<Run | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [file, setFile] = useState<{ name: string; text: string } | null>(null);

  useEffect(() => {
    setD(null); setFile(null);
    get<Detail>(`/api/run?dir=${encodeURIComponent(dir)}`).then(setD).catch((e) => setError(String(e.message)));
    get<Run[]>("/api/runs?limit=300").then((rs) => setMeta(rs.find((r) => r.dir === dir) ?? null)).catch(() => {});
  }, [dir]);

  const openFile = async (name: string) => setFile({ name, text: await fetch(fileUrl(dir, name)).then((r) => r.text()) });
  const max = Math.max(1, ...(d?.timings ?? []).map((t) => t.seconds));

  return (
    <>
      <a href="#/runs" className="mb-4 inline-flex items-center gap-1 text-[13px] text-sub hover:text-fg"><ArrowLeft className="h-3.5 w-3.5" />실행 기록</a>
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold">{meta?.name ?? dir}</h1>
        {meta && <StatusBadge result={meta.result} />}
      </div>
      <div className="mb-6 flex flex-wrap gap-x-5 gap-y-1 text-[12px] text-sub">
        {meta && <span className="font-mono">{when(meta.start)}</span>}
        {meta?.seconds != null && <span className="font-mono">{secs(meta.seconds)}</span>}
        {meta?.via && <span>{meta.via}</span>}
        {meta?.app?.branch && <span className="font-mono">{meta.app.branch}@{meta.app.commit}</span>}
        {meta?.kit && <span className="font-mono">qakit {meta.kit}</span>}
        <span className="font-mono">results/{dir}</span>
      </div>
      {error ? <Card><Empty>불러오지 못함: {error}</Empty></Card> : !d ? <Card><Spinner /></Card> : (
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
          <div className="min-w-0 space-y-5">
            <Card title="요약"><div className="p-4"><Pre>{d.summary || "(요약 없음)"}</Pre></div></Card>
            <Card title="단계별 시간" actions={d.timingHead && <span className="text-[12px] text-sub">{d.timingHead}</span>}>
              {d.timings.length === 0 ? <Empty>단계별 시간이 없습니다 (상주 실행기로 돈 실행에만 남음)</Empty> : (
                <div className="space-y-1 p-4">
                  {d.timings.map((t, i) => (
                    <div key={i} className="grid grid-cols-[56px_minmax(0,1fr)] items-center gap-3 text-[12px]">
                      <span className="text-right font-mono text-sub">{t.seconds.toFixed(1)}s</span>
                      <div style={{ paddingLeft: t.depth * 14 }}>
                        <div className={cx("truncate", t.name.startsWith("▸") && "font-medium")} title={t.name}>
                          <Mono className="text-[12px]">{t.name}</Mono>
                          {t.interrupts > 0 && <span className="ml-1 text-sub">(끼어드는 화면 {t.interrupts}s)</span>}
                        </div>
                        <div className="mt-0.5 h-1 rounded-full bg-muted">
                          <div className={cx("h-1 rounded-full", t.name.startsWith("앱") ? "bg-warn" : "bg-fg/70")} style={{ width: `${(t.seconds / max) * 100}%` }} />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Card>
            {file && <Card title={<Mono>{file.name}</Mono>} actions={<Button size="sm" variant="ghost" onClick={() => setFile(null)}>닫기</Button>}>
              <div className="p-4"><Pre>{file.text}</Pre></div></Card>}
            <Card title="로그 (끝 400줄)"><div className="p-4"><Pre>{d.log || "(로그 없음)"}</Pre></div></Card>
          </div>
          <div className="space-y-5">
            {(d.videos?.length ?? 0) > 0 && (
              <Card title="영상">
                <div className="grid gap-3 p-4">
                  {d.videos!.map((n) => (
                    <div key={n}>
                      <video src={fileUrl(dir, n)} controls playsInline preload="metadata" className="w-full rounded-xl bg-black shadow-e2" />
                      <a href={`${fileUrl(dir, n)}&download=1`} className="mt-1 block text-[11px] text-link hover:underline">{n} 내려받기</a>
                    </div>
                  ))}
                </div>
              </Card>
            )}
            <Card title="스크린샷">
              {d.images.length === 0 ? <Empty>없음</Empty> : (
                <div className="grid gap-3 p-4">
                  {d.images.map((n) => (
                    <a key={n} href={fileUrl(dir, n)} target="_blank" rel="noreferrer" className="block overflow-hidden rounded-xl bg-black p-1.5 shadow-e2">
                      <img src={fileUrl(dir, n)} alt={n} className="w-full rounded-lg" />
                    </a>
                  ))}
                </div>
              )}
            </Card>
            <Card title="화면 구조 · 파일">
              {d.dumps.length === 0 ? <Empty>없음</Empty> : (
                <div className="flex flex-col p-2">
                  {d.dumps.map((n) => (
                    <button key={n} onClick={() => openFile(n)}
                      className={cx("flex items-center gap-2 rounded-md px-2 py-1.5 text-left text-[12px] hover:bg-muted", file?.name === n && "bg-muted")}>
                      <FileText className="h-3.5 w-3.5 text-sub" /><Mono>{n}</Mono>
                    </button>
                  ))}
                </div>
              )}
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
