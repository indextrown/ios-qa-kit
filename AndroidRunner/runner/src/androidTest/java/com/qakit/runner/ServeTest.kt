package com.qakit.runner

import android.os.SystemClock
import android.util.Base64
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONObject
import org.json.JSONTokener
import org.junit.Test
import org.junit.runner.RunWith
import java.io.BufferedInputStream
import java.io.ByteArrayOutputStream
import java.net.InetAddress
import java.net.ServerSocket
import java.net.Socket
import java.net.SocketTimeoutException

/**
 * 상주 실행기 (iOS ScenarioRunner/Tests/ScenarioTests.swift test_serve와 같은 HTTP 명령).
 *
 *   adb shell am instrument -w -e port 7912 -e token <토큰> -e package <앱> -e idle 1800 -e launch 1 \
 *       com.qakit.runner.test/androidx.test.runner.AndroidJUnitRunner
 *   호스트는 adb forward tcp:<로컬> tcp:7912 로 붙는다. 라이브 화면(FrameServer)은 7913 (-e framePort).
 *
 * 명령 (POST, 헤더 X-Qakit-Token): /ping /config /step /dump /run /launch /reset /stop
 * 응답: { ok, message, durationMs, ... } — /dump와 실패 응답의 화면 구조는 uiautomator 형식 XML("xml")로 보내고
 * 호스트(qakit)가 덤프 텍스트로 바꾼다 (형식 코드를 한 곳에 두기 위해).
 * 요청은 이 테스트 스레드 하나에서 차례로 처리한다 (UiAutomator 조작을 한 스레드에서).
 */
@RunWith(AndroidJUnit4::class)
class ServeTest {
    private val args = InstrumentationRegistry.getArguments()

    @Test
    fun serve() {
        val port = args.getString("port", "7912").toInt()
        val token = args.getString("token") ?: error("token 인자가 필요함")
        val pkg = args.getString("package") ?: error("package 인자가 필요함")
        val idle = args.getString("idle", "1800").toLong() * 1000
        val screen = Screen(pkg)
        val app = AppControl(screen, pkg)
        var runner = Scenario(screen, app)
        val frames = FrameServer(screen.ua, args.getString("framePort", "7913").toInt(),
            args.getString("frameSize", "1280").toInt(), args.getString("frameQuality", "75").toInt()).also { it.start() }
        if (args.getString("launch", "1") == "1") app.launch()

        val server = ServerSocket(port, 8, InetAddress.getByName("127.0.0.1"))
        server.soTimeout = 1000
        println("[qakit-serve] ready port=$port")
        var lastRequest = SystemClock.elapsedRealtime()
        var stop = false
        var secrets: Map<String, String> = emptyMap()
        try {
            while (!stop) {
                val socket = try { server.accept() } catch (e: SocketTimeoutException) {
                    if (SystemClock.elapsedRealtime() - lastRequest > idle) {
                        println("[qakit-serve] ${idle / 1000}초 동안 명령이 없어 종료")
                        break
                    }
                    continue
                }
                lastRequest = SystemClock.elapsedRealtime()
                socket.use { s ->
                    val req = readRequest(s) ?: return@use
                    if (req.headers["x-qakit-token"] != token) {
                        respond(s, 403, JSONObject().put("ok", false).put("message", "토큰이 맞지 않음"))
                        return@use
                    }
                    val started = SystemClock.elapsedRealtime()
                    val json = JSONObject()
                    var ok = true
                    var message = ""
                    val body = if (req.body.isBlank()) JSONObject() else JSONTokener(req.body).nextValue()
                    runner.notes.clear()
                    runner.dumpFiles = mutableMapOf()
                    try {
                        when (req.path) {
                            "/ping" -> json.put("appState", app.state())
                            "/config" -> {
                                val o = (body as? JSONObject)?.optJSONObject("secrets") ?: JSONObject()
                                secrets = o.keys().asSequence().associateWith { o.optString(it) }
                                runner.secrets = secrets
                            }
                            "/step" -> {
                                if (!app.isForeground()) {
                                    ok = false
                                    message = "대상 앱이 화면 맨 앞에 없음 (${screen.foreground()}). qakit do launch"
                                } else runner.runStep(body)
                            }
                            "/dump" -> {
                                val settle = (body as? JSONObject)?.optDouble("settle", 0.5) ?: 0.5
                                SystemClock.sleep((settle * 1000).toLong())
                                json.put("xml", screen.xml())
                            }
                            "/run" -> {
                                val r = Scenario(screen, app).also { it.secrets = secrets }
                                try {
                                    r.run(body as JSONObject)
                                } finally {
                                    runner = r
                                    json.put("notes", org.json.JSONArray(r.notes))
                                    json.put("steps", org.json.JSONArray(r.trail.takeLast(8)))
                                    json.put("timings", org.json.JSONArray(r.timings))
                                }
                            }
                            "/launch" -> { app.launch(); runner = Scenario(screen, app).also { it.secrets = secrets } }
                            "/reset" -> runner = Scenario(screen, app).also { it.secrets = secrets }
                            "/stop" -> stop = true
                            else -> {
                                respond(s, 404, JSONObject().put("ok", false).put("message", "알 수 없는 경로: ${req.path}"))
                                return@use
                            }
                        }
                    } catch (e: QAFailure) {
                        ok = false; message = e.message ?: ""
                    } catch (e: Throwable) {
                        ok = false; message = "실행기 오류: ${e.javaClass.simpleName}: ${e.message}"
                    }
                    if (!ok && (req.path == "/step" || req.path == "/run") && app.isRunning()) {
                        runCatching { json.put("xml", screen.xml()) }   // 실패 시점 화면 구조
                        if (req.path == "/run") runCatching {
                            screen.screenshotPng()?.let { json.put("screenshot", Base64.encodeToString(it, Base64.NO_WRAP)) }
                        }
                    }
                    if (runner.dumpFiles.isNotEmpty()) json.put("files", JSONObject(runner.dumpFiles as Map<*, *>))
                    json.put("ok", ok).put("message", message)
                        .put("durationMs", SystemClock.elapsedRealtime() - started)
                        .put("density", screen.density.toDouble())
                        .put("screenW", screen.device.displayWidth).put("screenH", screen.device.displayHeight)
                        .put("package", pkg)
                    respond(s, 200, json)
                }
            }
        } finally {
            frames.running = false
            server.close()
            println("[qakit-serve] stopped")
        }
    }

    private class Request(val path: String, val headers: Map<String, String>, val body: String)

    private fun readRequest(s: Socket): Request? {
        s.soTimeout = 30000
        val input = BufferedInputStream(s.getInputStream())
        val head = ByteArrayOutputStream()
        var last4 = 0
        while (true) {
            val b = input.read()
            if (b < 0) return null
            head.write(b)
            last4 = (last4 shl 8) or b
            if (last4 == 0x0D0A0D0A) break
        }
        val lines = head.toString("UTF-8").split("\r\n")
        val path = lines.first().split(" ").getOrNull(1)?.substringBefore("?") ?: return null
        val headers = lines.drop(1).mapNotNull { l ->
            val i = l.indexOf(':'); if (i <= 0) null else l.substring(0, i).trim().lowercase() to l.substring(i + 1).trim()
        }.toMap()
        val len = headers["content-length"]?.toIntOrNull() ?: 0
        val body = ByteArray(len)
        var read = 0
        while (read < len) {
            val n = input.read(body, read, len - read)
            if (n < 0) break
            read += n
        }
        return Request(path, headers, String(body, 0, read, Charsets.UTF_8))
    }

    private fun respond(s: Socket, status: Int, json: JSONObject) {
        val bytes = json.toString().toByteArray(Charsets.UTF_8)
        val head = "HTTP/1.1 $status OK\r\nContent-Type: application/json; charset=utf-8\r\n" +
            "Content-Length: ${bytes.size}\r\nConnection: close\r\n\r\n"
        s.getOutputStream().apply { write(head.toByteArray()); write(bytes); flush() }
    }
}
