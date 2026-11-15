/** 테마: 밝게 · 어둡게 · 시스템. html에 .dark를 붙이고 떼는 것으로 바꾼다 (색은 index.css의 변수). */
export type Theme = "light" | "dark" | "system";
const KEY = "qakit-theme";
const media = () => window.matchMedia("(prefers-color-scheme: dark)");

export function getTheme(): Theme {
  try { const v = localStorage.getItem(KEY); return v === "light" || v === "dark" ? v : "system"; } catch { return "system"; }
}

export function applyTheme(t: Theme = getTheme()) {
  const dark = t === "dark" || (t === "system" && media().matches);
  document.documentElement.classList.toggle("dark", dark);
}

export function setTheme(t: Theme) {
  try { if (t === "system") localStorage.removeItem(KEY); else localStorage.setItem(KEY, t); } catch { /* 저장 못 해도 이번엔 적용 */ }
  applyTheme(t);
}

/** 시작할 때 한 번: 지금 테마 적용 + 시스템 설정이 바뀌면 따라감 */
export function initTheme() {
  applyTheme();
  media().addEventListener("change", () => { if (getTheme() === "system") applyTheme("system"); });
}
