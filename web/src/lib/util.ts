import { useEffect, useState } from "react";
export { clsx as cx } from "clsx";

export const when = (iso?: string | null) => (iso ? iso.replace("T", " ").slice(5, 16) : "");
export const secs = (s?: number | null) => (s == null ? "" : `${Number(s).toFixed(1)}s`);

/** location.hash 기반 라우팅 (서버는 / 하나만 서빙) */
export function useHash() {
  const [hash, setHash] = useState(location.hash || "#/live");
  useEffect(() => {
    const on = () => setHash(location.hash || "#/live");
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return hash;
}

/** 주기적으로 다시 부르기 (ms가 null이면 멈춤) */
export function useInterval(fn: () => void, ms: number | null) {
  useEffect(() => {
    if (ms == null) return;
    const t = setInterval(fn, ms);
    return () => clearInterval(t);
  }, [fn, ms]);
}

export function stored<T>(key: string, fallback: T): T {
  try { const v = localStorage.getItem(key); return v == null ? fallback : (JSON.parse(v) as T); } catch { return fallback; }
}
export function store(key: string, value: unknown) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* 저장 못 해도 동작 */ }
}
