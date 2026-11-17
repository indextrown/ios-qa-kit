import { useEffect, useRef } from "react";

/** 실시간 화면(MJPEG). WebKit(맥 앱 창·Safari)은 화면에서 빠진 <img>의 스트림을 끊지 않아, 라이브 세션을 오갈 때마다
 *  연결이 쌓여 서버당 6개 한도를 채우면 화면·API가 모두 멈춘다 → 빠질 때 src를 빈 그림으로 바꿔 직접 끊는다. */
const BLANK = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7";
export function StreamImg(props: React.ImgHTMLAttributes<HTMLImageElement>) {
  const ref = useRef<HTMLImageElement>(null);
  useEffect(() => {
    const el = ref.current;
    const stop = () => { if (el) el.src = BLANK; };
    window.addEventListener("pagehide", stop);
    return () => { window.removeEventListener("pagehide", stop); stop(); };
  }, []);
  // 기기 화면은 사진이 아니다 — 끌면 그림이 따라오는 브라우저 기본 동작·글자 선택을 막는다 (라이브 세션만 막혀 있었고 AI 화면은 끌렸다)
  return <img ref={ref} draggable={false} {...props} className={`select-none ${props.className ?? ""}`}
    onDragStart={(e) => { e.preventDefault(); props.onDragStart?.(e); }} />;
}
