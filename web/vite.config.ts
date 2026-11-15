import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 빌드 결과는 ../ui/dist (저장소에 커밋, qakit ui가 서빙). 개발 중에는 `QAKIT_UI=http://127.0.0.1:<포트> npm run dev`로 API를 넘긴다.
export default defineConfig({
  plugins: [react()],
  base: "/",
  build: { outDir: "../ui/dist", emptyOutDir: true, chunkSizeWarningLimit: 800 },
  server: { proxy: process.env.QAKIT_UI ? { "/api": process.env.QAKIT_UI } : undefined },
});
