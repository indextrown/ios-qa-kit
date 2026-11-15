import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CheckCircle2, AlertTriangle, XCircle, Save, Play, RotateCcw, Search, Plus, FileCode2, Layers, Tag, X, Loader2 } from "lucide-react";
import { get, post } from "../lib/api";
import { cx } from "../lib/util";
import { Badge, Button, Card, Empty, Mono, PageHeader } from "../components/ui";

type Kind = "scenario" | "step";
interface Check { ok: boolean; problem: string | null; unknownIds: string[]; steps: number; tags?: string[] }
interface Src { text: string; hash: string; path: string }

const NEW_SCENARIO = (name: string) => `name: ${name}\n# 무엇을 확인하는지 1~2줄\ntags: []\nsteps:\n  - use: home\n`;
const NEW_STEP = () => `# 이 공통 단계가 하는 일 1~2줄\nsteps:\n  - wait: { for: , timeout: 10 }\n`;

/** YAML 글에서 tags: 줄을 바꾸거나 steps: 앞에 넣는다 */
function setTags(text: string, tags: string[]) {
  const line = `tags: [${tags.join(", ")}]`;
  if (/^tags:.*$/m.test(text)) return text.replace(/^tags:.*$/m, tags.length ? line : "").replace(/\n\n+/g, "\n");
  return tags.length ? text.replace(/^steps:/m, `${line}\nsteps:`) : text;
}
const readTags = (text: string) => {
  const m = text.match(/^tags:\s*\[(.*)\]/m);
  return m ? m[1].split(",").map((t) => t.trim()).filter(Boolean) : [];
};

export function Editor({ route, runScenario }: { route: string; runScenario: (name: string) => Promise<void> }) {
  const [, kindRaw, nameRaw] = route.split("/").slice(1);   // #/edit/<kind>/<name>
  const kind: Kind = kindRaw === "step" ? "step" : "scenario";
  const name = nameRaw ? decodeURIComponent(nameRaw) : "";
  const [files, setFiles] = useState<{ scenario: string[]; step: string[] } | null>(null);
  const [filter, setFilter] = useState("");
  const [src, setSrc] = useState<Src | null>(null);
  const [text, setText] = useState("");
  const [check, setCheck] = useState<Check | null>(null);
  const [checking, setChecking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [idq, setIdq] = useState("");
  const [ids, setIds] = useState<{ total: number; ids: string[] } | null>(null);
  const [newTag, setNewTag] = useState("");
  const [creating, setCreating] = useState<Kind | null>(null);
  const [newName, setNewName] = useState("");
  const area = useRef<HTMLTextAreaElement>(null);
  const gutter = useRef<HTMLDivElement>(null);
  const dirty = !!src && text !== src.text;

  const loadFiles = useCallback(() => get<{ scenario: string[]; step: string[] }>("/api/src?list=1").then(setFiles).catch(() => {}), []);
  useEffect(() => { loadFiles(); }, [loadFiles]);
  useEffect(() => {
    setSrc(null); setCheck(null); setMsg(null);
    if (!name) return;
    get<Src>(`/api/src?kind=${kind}&name=${encodeURIComponent(name)}`)
      .then((s) => { setSrc(s); setText(s.text); })
      .catch((e) => setMsg({ ok: false, text: (e as Error).message }));
  }, [kind, name]);

  const runCheck = useCallback(async (t: string) => {
    if (!name) return;
    setChecking(true);
    try { setCheck(await post<Check>("/api/src/check", { kind, name, text: t })); } catch (e) { setMsg({ ok: false, text: (e as Error).message }); }
    setChecking(false);
  }, [kind, name]);
  useEffect(() => {   // 고치는 동안 0.8초 쉬면 검사
    if (!src) return;
    const t = setTimeout(() => runCheck(text), 800);
    return () => clearTimeout(t);
  }, [text, src, runCheck]);
  useEffect(() => {
    const t = setTimeout(() => get<{ total: number; ids: string[] }>(`/api/ids?q=${encodeURIComponent(idq)}`).then(setIds).catch(() => {}), 250);
    return () => clearTimeout(t);
  }, [idq]);

  const save = useCallback(async () => {
    if (!src || saving) return;
    setSaving(true); setMsg(null);
    try {
      const r = await post<{ saved: string; hash: string; check: Check }>("/api/src/save", { kind, name, text, baseHash: src.hash });
      const saved = text.endsWith("\n") ? text : text + "\n";
      setSrc({ ...src, text: saved, hash: r.hash }); setText(saved); setCheck(r.check);
      setMsg({ ok: true, text: `${r.saved} 저장${r.check.unknownIds.length ? " (앱에 없는 ID 경고 있음)" : ""}` });
    } catch (e) { setMsg({ ok: false, text: (e as Error).message }); }
    setSaving(false);
  }, [src, saving, kind, name, text]);
  useEffect(() => {
    const on = (e: KeyboardEvent) => { if ((e.metaKey || e.ctrlKey) && e.key === "s") { e.preventDefault(); save(); } };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [save]);

  const insert = (s: string) => {
    const el = area.current;
    if (!el) return;
    const a = el.selectionStart, b = el.selectionEnd;
    const next = text.slice(0, a) + s + text.slice(b);
    setText(next);
    requestAnimationFrame(() => { el.focus(); el.selectionStart = el.selectionEnd = a + s.length; });
  };
  const onKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Tab") { e.preventDefault(); insert("  "); }
  };
  const create = async () => {
    const n = newName.trim();
    if (!creating || !n) return;
    try {
      await post("/api/src/save", { kind: creating, name: n, text: creating === "scenario" ? NEW_SCENARIO(n) : NEW_STEP(), create: true });
      setCreating(null); setNewName(""); await loadFiles();
      location.hash = `#/edit/${creating}/${encodeURIComponent(n)}`;
    } catch (e) { setMsg({ ok: false, text: (e as Error).message }); }
  };

  const tags = useMemo(() => readTags(text), [text]);
  const lines = text.split("\n").length;
  const list = (k: Kind) => (files?.[k] ?? []).filter((n) => !filter || n.toLowerCase().includes(filter.toLowerCase()));

  return (
    <>
      <PageHeader title="편집" description="시나리오·공통 단계 YAML을 고치고 바로 검사·저장·실행합니다. ⌘S 저장, Tab 들여쓰기."
        actions={src && <>
          <Button onClick={() => { setText(src.text); setMsg(null); }} disabled={!dirty}><RotateCcw className="h-3.5 w-3.5" />되돌리기</Button>
          <Button variant="primary" onClick={save} loading={saving} disabled={!dirty}><Save className="h-3.5 w-3.5" />저장</Button>
          {kind === "scenario" && <Button onClick={() => runScenario(name)} disabled={dirty} title={dirty ? "먼저 저장하세요" : ""}><Play className="h-3.5 w-3.5" />실행</Button>}
        </>} />
      <div className="grid gap-5 xl:grid-cols-[220px_minmax(0,1fr)_300px]">
        <Card className="self-start">
          <div className="border-b border-line p-2">
            <label className="flex h-8 items-center gap-2 rounded-md bg-muted px-2.5">
              <Search className="h-3.5 w-3.5 text-sub" />
              <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="파일 찾기" className="w-full bg-transparent text-[12px] outline-none placeholder:text-sub" />
            </label>
          </div>
          {(["scenario", "step"] as Kind[]).map((k) => (
            <div key={k} className="p-2">
              <div className="flex items-center justify-between px-1.5 pb-1 text-[11px] font-medium text-sub">
                <span className="flex items-center gap-1">{k === "scenario" ? <FileCode2 className="h-3.5 w-3.5" /> : <Layers className="h-3.5 w-3.5" />}{k === "scenario" ? "시나리오" : "공통 단계"}</span>
                <button onClick={() => { setCreating(k); setNewName(""); }} className="rounded p-0.5 hover:bg-muted" title="새로 만들기"><Plus className="h-3.5 w-3.5" /></button>
              </div>
              {creating === k && (
                <form className="mb-1 flex gap-1 px-1" onSubmit={(e) => { e.preventDefault(); create(); }}>
                  <input autoFocus value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="이름" className="h-7 min-w-0 flex-1 rounded bg-muted px-2 font-mono text-[11px] outline-none" />
                  <Button size="sm" type="submit">만들기</Button>
                </form>
              )}
              <div className="max-h-[40vh] overflow-auto">
                {list(k).map((n) => (
                  <a key={n} href={`#/edit/${k}/${encodeURIComponent(n)}`}
                    className={cx("block truncate rounded px-2 py-1 font-mono text-[12px]", kind === k && name === n ? "bg-muted font-medium text-fg" : "text-sub hover:bg-muted/60 hover:text-fg")}>{n}</a>
                ))}
              </div>
            </div>
          ))}
        </Card>

        <div className="min-w-0">
          {!name ? <Card><Empty>왼쪽에서 파일을 고르세요</Empty></Card> : !src ? <Card><Empty>{msg?.text ?? "불러오는 중…"}</Empty></Card> : (
            <Card title={<span className="flex items-center gap-2"><Mono>{src.path}</Mono>{dirty && <Badge tone="warn">저장 안 됨</Badge>}</span>}>
              <div className="flex max-h-[70vh] overflow-auto font-mono text-[12.5px] leading-[1.6]">
                <div ref={gutter} className="select-none border-r border-line bg-muted/50 px-2 py-3 text-right text-sub">
                  {Array.from({ length: lines }, (_, i) => <div key={i}>{i + 1}</div>)}
                </div>
                <textarea ref={area} value={text} onChange={(e) => setText(e.target.value)} onKeyDown={onKey} spellCheck={false}
                  style={{ height: `${lines * 1.6 + 1.6}em` }}
                  className="min-h-[300px] flex-1 resize-none whitespace-pre bg-transparent px-3 py-3 outline-none" wrap="off" />
              </div>
            </Card>
          )}
          {msg && <div className={cx("mt-3 text-[12px]", msg.ok ? "text-ok" : "text-bad")}>{msg.text}</div>}
        </div>

        <div className="space-y-4">
          <Card title="검사" actions={checking && <Loader2 className="h-3.5 w-3.5 animate-spin text-sub" />}>
            {!check ? <Empty>파일을 열면 고칠 때마다 검사합니다</Empty> : (
              <div className="space-y-2 p-4 text-[12px]">
                {check.problem ? <div className="flex items-start gap-1.5 text-bad"><XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />{check.problem}</div>
                  : check.unknownIds.length ? <>
                    <div className="flex items-center gap-1.5 text-warn"><AlertTriangle className="h-3.5 w-3.5" />앱에 없는 ID {check.unknownIds.length}개</div>
                    {check.unknownIds.map((i) => <Mono key={i} className="block text-warn">{i}</Mono>)}</>
                    : <div className="flex items-center gap-1.5 text-ok"><CheckCircle2 className="h-3.5 w-3.5" />형식·ID 통과 · 단계 {check.steps}개 (use: 펼침)</div>}
              </div>
            )}
          </Card>
          {kind === "scenario" && src && (
            <Card title={<span className="flex items-center gap-1.5"><Tag className="h-3.5 w-3.5" />태그</span>}>
              <div className="space-y-2 p-4">
                <div className="flex flex-wrap gap-1">
                  {tags.length ? tags.map((t) => (
                    <span key={t} className="inline-flex items-center gap-1 rounded bg-muted px-1.5 py-0.5 font-mono text-[11px]">{t}
                      <button onClick={() => setText(setTags(text, tags.filter((x) => x !== t)))} className="text-sub hover:text-fg"><X className="h-3 w-3" /></button></span>
                  )) : <span className="text-[12px] text-sub">없음</span>}
                </div>
                <form className="flex gap-1" onSubmit={(e) => { e.preventDefault(); const t = newTag.trim(); if (t && !tags.includes(t)) setText(setTags(text, [...tags, t])); setNewTag(""); }}>
                  <input value={newTag} onChange={(e) => setNewTag(e.target.value)} placeholder="태그 추가 (smoke)" className="h-7 min-w-0 flex-1 rounded bg-muted px-2 font-mono text-[11px] outline-none" />
                  <Button size="sm" type="submit">추가</Button>
                </form>
              </div>
            </Card>
          )}
          <Card title="ID 찾기" actions={ids && <span className="text-[11px] text-sub">앱 ID {ids.total}개</span>}>
            <div className="p-2">
              <label className="mb-1 flex h-8 items-center gap-2 rounded-md bg-muted px-2.5">
                <Search className="h-3.5 w-3.5 text-sub" />
                <input value={idq} onChange={(e) => setIdq(e.target.value)} placeholder="home_search, SortButton…" className="w-full bg-transparent font-mono text-[12px] outline-none placeholder:text-sub" />
              </label>
              <div className="max-h-[40vh] overflow-auto">
                {(ids?.ids ?? []).map((i) => (
                  <button key={i} onClick={() => insert(i)} title="커서 위치에 넣기"
                    className="block w-full truncate rounded px-2 py-1 text-left font-mono text-[11.5px] text-sub hover:bg-muted hover:text-fg">{i}</button>
                ))}
              </div>
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}
