import { useEffect, useRef, useState } from "react";

const hex = (n: number) => n.toString(16).padStart(2, "0");

/** Annex-B 바이트에서 끝난 NAL들을 꺼낸다 (시작 코드 00 00 01 / 00 00 00 01). 남은 바이트는 다음 조각과 이어 붙인다 */
function splitNals(buf: Uint8Array): [Uint8Array[], Uint8Array] {
  const starts: number[] = [];
  for (let i = 0; i + 2 < buf.length; i++) if (buf[i] === 0 && buf[i + 1] === 0 && buf[i + 2] === 1) { starts.push(i + 3); i += 2; }
  if (starts.length < 2) return [[], buf];
  const out: Uint8Array[] = [];
  for (let k = 0; k + 1 < starts.length; k++) {
    let end = starts[k + 1] - 3;
    while (end > starts[k] && buf[end - 1] === 0) end--;   // 4바이트 시작 코드의 앞 00
    if (end > starts[k]) out.push(buf.subarray(starts[k], end));
  }
  const last = starts[starts.length - 1];
  return [out, buf.slice(last >= 4 && buf[last - 4] === 0 ? last - 4 : last - 3)];
}

const SC = new Uint8Array([0, 0, 0, 1]);
function join(parts: Uint8Array[]) {
  const n = parts.reduce((a, p) => a + p.length, 0);
  const out = new Uint8Array(n);
  let o = 0;
  for (const p of parts) { out.set(p, o); o += p.length; }
  return out;
}

/** 라이브 화면. 안드로이드는 H.264(기기 인코더가 화면 버퍼를 바로 인코딩)를 WebCodecs로 풀어 canvas에 그리고,
 *  안 되면(iOS·WebCodecs 없음·오류) 기존 MJPEG <img>. onSize: 받은 화면 크기 (가로·세로 판단) */
export function LiveScreen({ streamKey, className, style, onSize, onError, alt }:
  { streamKey: string | number; className?: string; style?: React.CSSProperties; onSize?: (w: number, h: number) => void;
    onError?: () => void; alt: string }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [mode, setMode] = useState<"h264" | "mjpeg">(() => ("VideoDecoder" in window ? "h264" : "mjpeg"));
  const sizeRef = useRef(onSize); sizeRef.current = onSize;

  useEffect(() => {
    if (mode !== "h264") return;
    const ctrl = new AbortController();
    let decoder: VideoDecoder | null = null;
    let alive = true;
    const fail = () => { if (alive) setMode("mjpeg"); };
    (async () => {
      try {
        const r = await fetch(`/api/stream.h264?k=${streamKey}`, { signal: ctrl.signal, cache: "no-store" });
        if (!r.ok || !r.body) return fail();   // iOS(404) 등 → MJPEG
        const reader = r.body.getReader();
        let buf: Uint8Array = new Uint8Array(0), sps: Uint8Array | null = null, pps: Uint8Array | null = null, gotKey = false, ts = 0;
        decoder = new VideoDecoder({
          output: (frame) => {
            const c = canvas.current;
            if (c) {
              if (c.width !== frame.displayWidth || c.height !== frame.displayHeight) {
                c.width = frame.displayWidth; c.height = frame.displayHeight;
                sizeRef.current?.(frame.displayWidth, frame.displayHeight);
              }
              c.getContext("2d")?.drawImage(frame, 0, 0);
            }
            frame.close();
          },
          error: () => fail(),
        });
        for (;;) {
          const { value, done } = await reader.read();
          if (done || !alive) break;
          const merged = new Uint8Array(buf.length + value.length);
          merged.set(buf); merged.set(value, buf.length);
          const [nals, rest] = splitNals(merged);
          buf = rest;
          for (const nal of nals) {
            const t = nal[0] & 31;
            if (t === 7) {
              sps = nal.slice();
              if (decoder.state === "unconfigured")
                decoder.configure({ codec: `avc1.${hex(sps[1])}${hex(sps[2])}${hex(sps[3])}`, optimizeForLatency: true });
            } else if (t === 8) pps = nal.slice();
            else if (t === 5 && sps && pps) {
              gotKey = true;
              decoder.decode(new EncodedVideoChunk({ type: "key", timestamp: (ts += 33333), data: join([SC, sps, SC, pps, SC, nal]) }));
            } else if (t === 1 && gotKey) {
              if (decoder.decodeQueueSize > 8) continue;   // 밀리면 버린다 (다음 키 프레임까지 조금 깨질 수 있음)
              decoder.decode(new EncodedVideoChunk({ type: "delta", timestamp: (ts += 33333), data: join([SC, nal]) }));
            }
          }
        }
        if (alive) fail();   // 서버가 끊음 → MJPEG로 (다시 고르면 H.264 다시 시도)
      } catch (e) {
        if ((e as Error).name !== "AbortError") fail();
      }
    })();
    return () => { alive = false; ctrl.abort(); try { decoder?.close(); } catch { /* 이미 닫힘 */ } };
  }, [mode, streamKey]);

  if (mode === "h264") return <canvas ref={canvas} className={className} style={style} aria-label={alt} />;
  return <img key={String(streamKey)} src={`/api/stream?k=${streamKey}`} alt={alt} className={className} draggable={false} style={style}
    onLoad={(e) => { const { naturalWidth: w, naturalHeight: h } = e.currentTarget; if (w && h) onSize?.(w, h); }}
    onError={onError} />;
}
