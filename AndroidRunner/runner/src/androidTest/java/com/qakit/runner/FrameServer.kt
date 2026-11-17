package com.qakit.runner

import android.app.UiAutomation
import android.graphics.Bitmap
import android.os.SystemClock
import java.io.BufferedOutputStream
import java.io.ByteArrayOutputStream
import java.net.InetAddress
import java.net.ServerSocket
import java.net.SocketTimeoutException

/**
 * 라이브 화면 (qakit ui): 붙은 쪽에 화면 JPEG를 계속 보낸다. 형식은 iOS Tools/simscreen과 같다 —
 * [4바이트 길이(빅엔디안)][JPEG] 반복. 명령 서버(ServeTest)와 다른 스레드라 시나리오가 도는 중에도 화면이 나온다.
 * adb screencap -p는 이 에뮬레이터에서 한 장에 4초 넘게 걸려(PNG 압축) 라이브 화면에 쓸 수 없다.
 */
class FrameServer(private val ua: UiAutomation, private val port: Int, private val maxSide: Int = 1280,
                  private val quality: Int = 75) : Thread("qakit-frames") {
    @Volatile var running = true
    private val fps = 12

    companion object {
        /** 명령(단계·화면 읽기)을 하는 중인가 — 그동안은 초당 4장으로 (화면 캡처가 화면 구조 읽기를 늦춤: 중앙값 0.37→0.50초, 2026-11-17 측정) */
        @Volatile var busy = 0
        const val SLOW_MS = 250L
    }

    init { isDaemon = true }

    override fun run() {
        val server = try { ServerSocket(port, 2, InetAddress.getByName("127.0.0.1")) } catch (e: Exception) {
            println("[qakit-serve] 화면 서버를 열지 못함: ${e.message}"); return
        }
        server.soTimeout = 1000
        server.use {
            while (running) {
                val s = try { server.accept() } catch (e: SocketTimeoutException) { continue }
                s.use { sock ->
                    sock.tcpNoDelay = true
                    val out = BufferedOutputStream(sock.getOutputStream(), 1 shl 16)
                    val buf = ByteArrayOutputStream(1 shl 16)
                    var lastSize = -1
                    var lastHash = 0
                    var still = 0   // 연달아 같은 장면 수 — 화면이 멈춰 있으면 천천히 캡처하고, 같은 장면은 보내지 않는다 (tapflow의 seed 건너뛰기처럼)
                    try {
                        while (running) {
                            val started = SystemClock.elapsedRealtime()
                            val bmp = ua.takeScreenshot()
                            if (bmp != null) {
                                // 긴 변을 maxSide로 (가로 태블릿 2560x1600 → 1280x800, 세로 폰 1080x2400 → 576x1280). 600 고정은
                                // 레티나 화면에서 흐렸다 (2026-11-16). 원본보다 키우지는 않는다
                                val scale = minOf(1.0, maxSide.toDouble() / maxOf(bmp.width, bmp.height))
                                val w = (bmp.width * scale).toInt().coerceAtLeast(1)
                                val h = (bmp.height * scale).toInt().coerceAtLeast(1)
                                val small = if (scale < 1.0) Bitmap.createScaledBitmap(bmp, w, h, true) else bmp
                                buf.reset()
                                small.compress(Bitmap.CompressFormat.JPEG, quality, buf)
                                val n = buf.size()
                                val hash = java.util.Arrays.hashCode(buf.toByteArray())
                                if (n == lastSize && hash == lastHash) still += 1 else {
                                    still = 0; lastSize = n; lastHash = hash
                                    out.write(byteArrayOf((n ushr 24).toByte(), (n ushr 16).toByte(), (n ushr 8).toByte(), n.toByte()))
                                    buf.writeTo(out)
                                    out.flush()
                                }
                                if (small !== bmp) small.recycle()
                                bmp.recycle()
                            }
                            // 받는 쪽이 끊겼는지는 보내기에서만 알 수 있다 → 같은 장면이 오래 이어지면 2초마다 한 번은 보낸다
                            if (still > 0 && still % 8 == 0) { lastSize = -1 }
                            val interval = if (busy > 0 || still >= 6) SLOW_MS else 1000L / fps
                            val wait = interval - (SystemClock.elapsedRealtime() - started)
                            if (wait > 0) SystemClock.sleep(wait)
                        }
                    } catch (e: Exception) {
                        // 받는 쪽이 끊음 → 다음 연결을 기다린다
                    }
                }
            }
        }
    }
}
