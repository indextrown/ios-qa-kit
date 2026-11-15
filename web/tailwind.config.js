/** 흑백 위주 디자인: 색은 모두 src/index.css의 CSS 변수로 (다크 모드는 변수만 바뀜) */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Inter Variable"', '"Apple SD Gothic Neo"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono Variable"', "ui-monospace", "Menlo", "monospace"],
      },
      colors: {
        bg: "rgb(var(--bg) / <alpha-value>)",
        side: "rgb(var(--side) / <alpha-value>)",
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
        e1: "0 0 0 1px rgb(var(--line))",   // 그림자 없이 경계선만
        e2: "0 0 0 1px rgb(var(--line)), 0 1px 3px rgb(0 0 0 / 0.04)",
        e3: "0 0 0 1px rgb(var(--line)), 0 12px 32px rgb(0 0 0 / 0.12)",
      },
      letterSpacing: { head: "-0.02em" },
    },
  },
  plugins: [],
};
