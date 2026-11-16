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
  return <img ref={ref} {...props} />;
}
