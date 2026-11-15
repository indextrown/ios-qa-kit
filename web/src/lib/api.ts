// qakit ui 서버(bin/qakit cmd_ui) API. 쿠키로 인증, 실행 요청은 X-Qakit-UI 헤더.
export type Result = "Passed" | "Failed" | "unknown" | string;
export interface Info { name: string; simulator: string | null; device: string | null; bundleId: string; kit: string; precheck: string | null;
  app: { branch?: string; commit?: string; dirtyFiles?: number } }
export interface Run { dir: string; kind: string; name: string; device: string | null; start: string; result: Result;
  seconds: number | null; via: string | null; app: Info["app"] | null; kit: string | null; screenshot: boolean }
export interface Timing { depth: number; seconds: number; name: string; interrupts: number }
export interface RunDetail { dir: string; summary: string | null; log: string; timingHead: string | null; timings: Timing[];
  images: string[]; dumps: string[]; files: string[] }
export interface Scenario { name: string; title: string; description: string; tags: string[]; recent: ("pass" | "fail" | "env")[];
  last: { result: Result; at: string; dir?: string } | null; flaky: boolean }
export interface Job { running: boolean; args: string[] | null; started: number | null; ended: number | null; code: number | null;
  total: number; lines: string[]; draft?: string | null }
export interface El { type: string; id: string | null; label: string | null; labelRaw: string | null; value: string | null;
  x: number; y: number; w: number; h: number; depth: number }
export interface Elements { screen: { w: number; h: number } | null; elements: El[] }
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
