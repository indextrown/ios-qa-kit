/** 흑백 위주 디자인: 색은 모두 src/index.css의 CSS 변수로 (다크 모드는 변수만 바뀜) */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "media",
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Inter Variable"', '"Apple SD Gothic Neo"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono Variable"', "ui-monospace", "Menlo", "monospace"],
      },
      colors: {
        bg: "rgb(var(--bg) / <alpha-value>)",
        card: "rgb(var(--card) / <alpha-value>)",
        muted: "rgb(var(--muted) / <alpha-value>)",
        fg: "rgb(var(--fg) / <alpha-value>)",
        sub: "rgb(var(--sub) / <alpha-value>)",
        line: "rgb(var(--line) / <alpha-value>)",
        primary: "rgb(var(--primary) / <alpha-value>)",
        "primary-fg": "rgb(var(--primary-fg) / <alpha-value>)",
        ok: "rgb(var(--ok) / <alpha-value>)",
        bad: "rgb(var(--bad) / <alpha-value>)",
        warn: "rgb(var(--warn) / <alpha-value>)",
        link: "rgb(var(--link) / <alpha-value>)",
      },
      boxShadow: {
        e1: "0 0 0 1px rgb(var(--line)), 0 1px 2px rgb(0 0 0 / 0.04)",
        e2: "0 0 0 1px rgb(var(--line)), 0 2px 6px rgb(0 0 0 / 0.06)",
        e3: "0 0 0 1px rgb(var(--line)), 0 8px 24px rgb(0 0 0 / 0.10)",
      },
      letterSpacing: { head: "-0.02em" },
    },
  },
  plugins: [],
};
