// qakit ui 서버(bin/qakit cmd_ui) API. 쿠키로 인증, 실행 요청은 X-Qakit-UI 헤더.
export type Result = "Passed" | "Failed" | "unknown" | string;
export interface Info { name: string; simulator: string | null; device: string | null; bundleId: string; kit: string; precheck: string | null;
  app: { branch?: string; commit?: string; dirtyFiles?: number } }
export interface Run { dir: string; kind: string; name: string; device: string | null; start: string; result: Result;
  seconds: number | null; via: string | null; app: Info["app"] | null; kit: string | null; screenshot: boolean }
export interface Timing { depth: number; seconds: number; name: string; interrupts: number }
export interface RunDetail { dir: string; summary: string | null; log: string; timingHead: string | null; timings: Timing[];
  images: string[]; videos?: string[]; dumps: string[]; files: string[] }
export interface Scenario { name: string; title: string; description: string; tags: string[]; recent: ("pass" | "fail" | "env")[];
  last: { result: Result; at: string; dir?: string } | null; flaky: boolean }
export interface Job { running: boolean; args: string[] | null; started: number | null; ended: number | null; code: number | null;
  total: number; lines: string[]; draft?: string | null }
export interface El { type: string; id: string | null; label: string | null; labelRaw: string | null; value: string | null;
  x: number; y: number; w: number; h: number; depth: number }
export interface Elements { screen: { w: number; h: number } | null; elements: El[]; platform?: "ios" | "android" }
export interface AiSession { dir: string; name: string; goal: string | null; client: string | null; via: string; started: string | null; mode?: "qa" | "scenario";
  ended: string | null; seconds: number | null; cost: number | null; turns: number | null; code: number | null; calls: number; failed: number;
  issues: number; report: boolean; steps: number; saved: string[] }
export interface DoResult { code: number; output: string }

async function read<T>(r: Response): Promise<T> {
  const text = await r.text();
  let body: unknown = text;
  try { body = JSON.parse(text); } catch { /* 글자 그대로 */ }
  if (!r.ok) throw new Error((body as { error?: string })?.error || text || String(r.status));
  return body as T;
}
export const get = <T,>(path: string) => fetch(path, { cache: "no-store" }).then((r) => read<T>(r));
export const post = <T,>(path: string, body: unknown = {}) =>
  fetch(path, { method: "POST", headers: { "Content-Type": "application/json", "X-Qakit-UI": "1" }, body: JSON.stringify(body) })
    .then((r) => read<T>(r));
export const fileUrl = (dir: string, name: string) => `/api/file?dir=${encodeURIComponent(dir)}&name=${encodeURIComponent(name)}`;
export const screenUrl = () => `/api/screen?ts=${Date.now()}`;

/** AI QA 세션 결과 → AI가 화면·앱 소스를 보며 시나리오로 만든다 (사용량이 든다). 시작하면 AI QA 화면으로. */
export async function scenarioFromSession(dir: string, goal: string | null) {
  const read = <T,>(k: string, d: T): T => { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v) as T; } catch { return d; } };
  if (!window.confirm("이 AI QA 결과를 바탕으로 AI가 앱 화면과 소스를 보며 시나리오를 만듭니다.\nAI 계정 사용량이 듭니다. 시작할까요?")) return false;
  await post("/api/ai/start", {
    goal: `AI QA 결과에서 확인된 흐름을 재사용 시나리오로${goal ? ` (그때 목표: ${goal})` : ""}`,
    mode: "scenario", fromSession: dir, readSource: true,
    engine: read("qakit-ai-engine", "claude"), minutes: read("qakit-ai-minutes", 10), turns: read("qakit-ai-turns", 60),
  });
  try { localStorage.setItem("qakit-ai-mode", JSON.stringify("scenario")); } catch { /* 없어도 됨 */ }
  location.hash = "#/ai";
  return true;
}

/** Claude Code 모델 (claude --model 별칭). 빈 값 = 계정 기본. AI 채팅·AI QA가 같은 선택을 쓴다 (qakit-ai-model) */
export const AI_MODELS: [string, string][] = [["", "계정 기본"], ["opus", "Opus — 가장 꼼꼼함"], ["sonnet", "Sonnet — 빠르고 저렴"], ["haiku", "Haiku — 가장 빠름"]];

