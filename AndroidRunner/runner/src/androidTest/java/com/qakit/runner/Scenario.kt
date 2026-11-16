package com.qakit.runner

import android.os.SystemClock
import org.json.JSONArray
import org.json.JSONObject
import org.xmlpull.v1.XmlPullParser
import android.util.Xml
import kotlin.math.abs
import kotlin.math.ln
import kotlin.math.pow

class QAFailure(message: String) : Exception(message)

/**
 * .qa.yml 시나리오(qakit이 JSON으로 바꿈) 실행기 — iOS Sources/QAKit/Scenario/QAScenarioRunner.swift를 옮긴 것.
 * 단계·조건·대상의 의미와 실패 문구를 iOS와 같게 둔다 (qakit의 실패 요약·추천이 문구를 읽는다).
 *
 * 안드로이드에서 다른 점:
 *  - 앱 설정(pref·read-pref·pinch-to)은 SharedPreferences XML (run-as, debuggable 빌드만). DataStore는 읽지 못한다.
 *  - input(입력 알림)은 대화상자의 첫 입력칸, alert-button은 대화상자 버튼 글자(대소문자 무시)로 찾는다.
 *  - 성능 측정(--bench)은 아직 없다.
 */
class Scenario(private val screen: Screen, private val app: AppControl) {
    val trail = mutableListOf<String>()
    val timings = mutableListOf<JSONObject>()
    val notes = mutableListOf<String>()
    var secrets: Map<String, String> = emptyMap()
    var dumpFiles = mutableMapOf<String, String>()

    private var depth = 0
    private val vars = mutableMapOf<String, String>()
    private val snapshots = mutableMapOf<String, String>()
    private var interrupts = listOf<JSONObject>()
    private var handlingInterrupt = false
    private var currentStep = JSONObject()
    private var lastInterruptPoll = 0L

    private fun note(s: String) { notes += s }
    private fun now() = SystemClock.elapsedRealtime()
    private fun sleep(seconds: Double) = SystemClock.sleep((seconds * 1000).toLong())

    // ───────────────────────────── 시나리오 ─────────────────────────────

    fun run(root: JSONObject) {
        mergeVars(root.opt("vars"))
        interrupts = flattenInterrupts(root.optJSONArray("interrupts") ?: JSONArray())
        note("시나리오: ${root.optString("name", "(이름 없음)")}")
        val launch = root.opt("launch")
        if (launch == "reuse") {
            reuseOrLaunch(root.opt("start"))
        } else if (launch != false) {
            val t = now()
            app.launch()
            timings += timing("launch", "앱 실행", t, 0)
        }
        runSteps(root.optJSONArray("steps") ?: JSONArray())
    }

    private fun reuseOrLaunch(start: Any?) {
        val t = now()
        var reason = "start: 조건이 없음"
        if (start != null) {
            if (app.isForeground()) {
                if (evaluate(start, 2.0)) {
                    note("앱 재실행 생략: 시작 화면 확인 (${compact(start)})")
                    timings += timing("launch", "앱 재실행 생략 (시작 화면 확인)", t, 0)
                    return
                }
                reason = "시작 화면이 아님"
            } else reason = "앱이 실행 중이 아님"
        }
        note("앱 다시 실행 ($reason)")
        app.launch()
        timings += timing("launch", "앱 실행 ($reason)", t, 0)
    }

    private fun timing(kind: String, name: String, start: Long, depth: Int) = JSONObject()
        .put("kind", kind).put("name", name).put("seconds", (now() - start) / 1000.0).put("depth", depth)

    fun runStep(raw: Any) {
        val step = raw as? JSONObject ?: throw fail("단계 형식 오류: $raw")
        val started = now()
        var interruptSeconds = 0.0
        if (!step.has("group")) {
            handleInterrupts(step)
            interruptSeconds = (now() - started) / 1000.0
            currentStep = step
        }
        trail += describe(step)
        while (trail.size > 50) trail.removeAt(0)
        val index = timings.size
        timings += JSONObject()
        depth += 1
        try {
            execute(step)
        } finally {
            depth -= 1
            val row = timing(if (step.has("group")) "group" else "step", describe(step), started, depth)
            if (interruptSeconds >= 0.05) row.put("interrupts", interruptSeconds)
            timings[index] = row
        }
    }

    private fun runSteps(steps: JSONArray) {
        for (i in 0 until steps.length()) runStep(steps.get(i))
    }

    // ───────────────────────────── 끼어드는 화면 ─────────────────────────────

    private fun pollInterrupts() {
        if (interrupts.isEmpty() || handlingInterrupt || now() - lastInterruptPoll < 1000) return
        lastInterruptPoll = now()
        handleInterrupts(currentStep)
    }

    private fun flattenInterrupts(items: JSONArray): List<JSONObject> {
        val out = mutableListOf<JSONObject>()
        for (i in 0 until items.length()) {
            val step = items.optJSONObject(i) ?: continue
            if (step.has("group")) out += flattenInterrupts(step.optJSONArray("steps") ?: JSONArray())
            else if (step.has("if") || step.has("unless")) out += step
        }
        return out
    }

    private fun ids(value: Any?): Set<String> = when (value) {
        is String -> if (value.contains(".")) setOf(value) else emptySet()
        is JSONArray -> (0 until value.length()).flatMap { ids(value.get(it)) }.toSet()
        is JSONObject -> value.keys().asSequence().flatMap { ids(value.get(it)) }.toSet()
        else -> emptySet()
    }

    private fun handleInterrupts(current: JSONObject) {
        if (interrupts.isEmpty() || handlingInterrupt) return
        handlingInterrupt = true
        try {
            val currentIds = ids(current)
            for (step in interrupts) {
                if (currentIds.intersect(ids(step)).isNotEmpty()) continue
                val cond = step.opt("if") ?: step.opt("unless")
                var hit = evaluate(cond!!, 0.0)
                if (step.has("unless")) hit = !hit
                if (!hit) continue
                note(step.optString("note").takeIf { it.isNotEmpty() }?.let { text(it) } ?: "끼어든 화면 처리")
                runSteps(step.optJSONArray("then") ?: JSONArray())
                val end = now() + 3000
                while (now() < end) {
                    var still = evaluate(cond, 0.0)
                    if (step.has("unless")) still = !still
                    if (!still) break
                    sleep(0.3)
                }
            }
        } finally {
            handlingInterrupt = false
        }
    }

    // ───────────────────────────── 단계 ─────────────────────────────

    private fun execute(step: JSONObject) {
        when {
            step.has("group") -> {
                mergeVars(step.opt("vars"))
                runSteps(step.optJSONArray("steps") ?: JSONArray())
            }
            step.has("tap") -> {
                val target = step.get("tap")
                waitFor(target, number(step.opt("timeout")) ?: 10.0)
                val effect = step.opt("expect")?.let { frontmost(it) }
                if (effect != null && check(effect)) {
                    throw fail("누르기 전에 이미 기대 효과가 맞음 → 탭의 효과를 확인할 수 없음: ${compact(effect)}")
                }
                val node = waitUntilSettled(target) ?: throw fail("10초 안에 나타나지 않음: ${compact(target)}")
                screen.tap(node)
                if (effect != null && !evaluate(effect, number(step.opt("expect-timeout")) ?: 10.0)) {
                    throw fail("탭 뒤 기대 효과가 나타나지 않음 (탭이 무시됐거나 다른 곳에 닿았을 수 있음): ${compact(effect)}")
                }
            }
            step.optJSONObject("input") != null -> {
                val spec = step.getJSONObject("input")
                spec.opt("tap")?.let { t -> waitFor(t, 10.0); screen.tap(find(t)!!) }
                val field = JSONObject().put("alert-field", true)
                if (!evaluate(JSONObject().put("exists", field), 5.0)) throw fail("입력 알림이 뜨지 않음")
                screen.setText(find(field)!!, text(spec.opt("alert")))
                val confirm = JSONObject().put("alert-button", spec.opt("confirm") ?: "확인")
                waitFor(confirm, 5.0, spec.opt("confirm") ?: "확인")
                screen.tap(find(confirm)!!)
            }
            step.optJSONObject("type") != null -> {
                val spec = step.getJSONObject("type")
                val into = spec.opt("into")
                waitFor(into, number(spec.opt("timeout")) ?: 10.0)   // XCUITest의 암묵적 대기와 같게
                val node = find(into) ?: throw fail("10초 안에 나타나지 않음: ${compact(into)}")
                if (!screen.setText(node, text(spec.opt("text")))) throw fail("글자를 넣지 못함 (입력칸이 아님?): ${compact(into)}")
            }
            step.has("wait") -> {
                val target = step.get("wait")
                val spec = target as? JSONObject
                val what = spec?.opt("for") ?: target
                waitFor(what, number(spec?.opt("timeout")) ?: number(step.opt("timeout")) ?: 10.0)
            }
            step.optJSONObject("wait-any") != null -> {
                val spec = step.getJSONObject("wait-any")
                val cands = spec.optJSONObject("candidates") ?: JSONObject()
                val keys = cands.keys().asSequence().sorted().toList()
                val timeout = number(spec.opt("timeout")) ?: 30.0
                val deadline = now() + (timeout * 1000).toLong()
                var found: String? = null
                do {
                    val tree = screen.tree()
                    found = keys.firstOrNull { find(cands.get(it), tree) != null }
                    if (found != null) break
                    pollInterrupts()
                    sleep(0.5)
                } while (now() < deadline)
                if (found == null) throw fail("${timeout.toInt()}초 안에 아무것도 나타나지 않음: ${keys.joinToString(", ")}")
                spec.optString("as").takeIf { it.isNotEmpty() }?.let { vars[it] = found }
                note("먼저 나타남: $found")
            }
            step.has("if") || step.has("unless") -> {
                var ok = evaluate(step.opt("if") ?: step.opt("unless")!!, number(step.opt("timeout")) ?: 0.0)
                if (step.has("unless")) ok = !ok
                runSteps((if (ok) step.optJSONArray("then") else step.optJSONArray("else")) ?: JSONArray())
            }
            step.optJSONObject("read") != null -> {
                val spec = step.getJSONObject("read")
                val from = spec.opt("from")
                waitFor(from, number(spec.opt("timeout")) ?: 10.0)
                val node = find(from)!!
                val value = extract(node.label.ifEmpty { node.text }, spec.optString("pattern").ifEmpty { null })
                val name = spec.optString("as").ifEmpty { throw fail("read에 as: 가 필요함") }
                vars[name] = value
                note("읽음 $name = $value")
            }
            step.optJSONObject("scroll-to") != null -> {
                val spec = step.getJSONObject("scroll-to")
                val target = spec.opt("target")
                val max = (number(spec.opt("max")) ?: 8.0).toInt()
                var count = 0
                while (find(target)?.let { screen.isVisible(it) } != true && count < max) {
                    val container = find(spec.opt("in")) ?: throw fail("10초 안에 나타나지 않음: ${compact(spec.opt("in"))}")
                    screen.swipe(container, spec.optString("dir", "up"))
                    sleep(0.4)
                    count += 1
                }
                if (spec.opt("required") != false && find(target) == null) {
                    throw fail("${max}번 스크롤해도 찾지 못함: ${compact(target)}")
                }
            }
            step.optJSONObject("swipe") != null -> {
                val spec = step.getJSONObject("swipe")
                val node = find(spec.opt("on")) ?: throw fail("10초 안에 나타나지 않음: ${compact(spec.opt("on"))}")
                screen.swipe(node, spec.optString("dir", "up"))
            }
            step.has("long-press") -> {
                val raw = step.get("long-press")
                val target = (raw as? JSONObject)?.opt("on") ?: raw
                waitFor(target, number(step.opt("timeout")) ?: 10.0)
                val effect = step.opt("expect")?.let { frontmost(it) }
                if (effect != null && check(effect)) {
                    throw fail("누르기 전에 이미 기대 효과가 맞음 → 길게 누르기의 효과를 확인할 수 없음: ${compact(effect)}")
                }
                val node = waitUntilSettled(target) ?: throw fail("10초 안에 나타나지 않음: ${compact(target)}")
                screen.longPress(node, number((raw as? JSONObject)?.opt("seconds")) ?: number(step.opt("seconds")) ?: 1.0)
                if (effect != null && !evaluate(effect, number(step.opt("expect-timeout")) ?: 10.0)) {
                    throw fail("길게 누른 뒤 기대 효과가 나타나지 않음: ${compact(effect)}")
                }
            }
            step.optJSONObject("drag") != null -> {
                val spec = step.getJSONObject("drag")
                val fromTarget = spec.opt("from") ?: throw fail("drag에 from: 이 필요함")
                waitFor(fromTarget, number(spec.opt("timeout")) ?: 10.0)
                val from = waitUntilSettled(fromTarget) ?: throw fail("10초 안에 나타나지 않음: ${compact(fromTarget)}")
                val to = spec.opt("to")?.let { t -> waitFor(t, 5.0); find(t) ?: throw fail("끝 대상을 찾지 못함: ${compact(t)}") }
                screen.drag(from, to, spec.optString("dir", "up"), number(spec.opt("distance")) ?: 0.3, number(spec.opt("seconds")) ?: 0.5)
                sleep(number(spec.opt("settle")) ?: 0.3)
            }
            step.optJSONObject("pinch") != null -> {
                val spec = step.getJSONObject("pinch")
                waitFor(spec.opt("on"), 5.0)
                screen.pinch(find(spec.opt("on"))!!, number(spec.opt("scale")) ?: 2.0)
                sleep(number(spec.opt("settle")) ?: 0.5)
            }
            step.has("two-finger-tap") -> {
                val raw = step.get("two-finger-tap")
                val spec = raw as? JSONObject
                val target = spec?.opt("on") ?: raw
                waitFor(target, 5.0)
                repeat((number(spec?.opt("count")) ?: 1.0).toInt()) {
                    screen.twoFingerTap(find(target)!!)
                    sleep(number(spec?.opt("settle")) ?: 0.6)
                }
            }
            step.optJSONObject("pinch-to") != null -> pinchTo(step.getJSONObject("pinch-to"))
            step.optJSONObject("snapshot") != null -> {
                val spec = step.getJSONObject("snapshot")
                waitFor(spec.opt("of"), 5.0)
                snapshots[spec.optString("as", "snapshot")] = shotOf(spec.opt("of"))
            }
            step.has("expect") -> {
                val condition = step.get("expect")
                if (!evaluate(condition, number(step.opt("timeout")) ?: 0.0)) {
                    throw fail(step.optString("message").ifEmpty { "기대 조건 실패: ${compact(condition)}" })
                }
                val hold = number(step.opt("hold")) ?: 0.0
                if (hold > 0) {
                    val deadline = now() + (hold * 1000).toLong()
                    while (now() < deadline) {
                        if (!evaluate(condition, 0.0)) {
                            throw fail(step.optString("message").ifEmpty { "조건이 유지되지 않음" } + " (${hold.toInt()}초 유지 필요)")
                        }
                        sleep(0.5)
                    }
                }
            }
            step.has("note") -> note(text(step.get("note")))
            step.has("dump") -> {
                sleep(number(step.opt("settle")) ?: 1.0)
                val name = text(step.get("dump"))
                dumpFiles["dumps/$name.txt"] = "@xml " + screen.xml()   // 호스트가 덤프 텍스트로 바꿔 쓴다
                note("dump $name")
            }
            step.optJSONObject("repeat") != null -> repeatStep(step.getJSONObject("repeat"))
            step.optJSONObject("read-pref") != null -> {
                val spec = step.getJSONObject("read-pref")
                val key = spec.optString("key"); val name = spec.optString("as")
                if (key.isEmpty() || name.isEmpty()) throw fail("read-pref: { key, as } 형식")
                val value = prefValue(key)
                if (value == null) {
                    if (spec.has("default")) {
                        vars[name] = text(spec.get("default"))
                        note("앱 설정 $key 없음 → ${vars[name]}")
                        return
                    }
                    throw fail("앱 설정에 '$key' 값이 없음 (${prefsNote()})")
                }
                vars[name] = formatPref(value)
                note("앱 설정 $key = ${vars[name]}")
            }
            step.has("hide-keyboard") -> {
                // 키보드가 없을 때 뒤로 가기를 보내면 화면이 닫히거나 앱이 내려간다 → 실제로 떠 있을 때만
                if (screen.keyboardShown()) {
                    screen.device.pressBack()
                    val end = now() + 3000
                    while (screen.keyboardShown() && now() < end) sleep(0.2)
                }
            }
            step.has("relaunch") -> app.launch()
            step.has("fail") -> throw fail(text(step.get("fail")))
            else -> throw fail("알 수 없는 단계: ${compact(step)}")
        }
    }

    private fun repeatStep(spec: JSONObject) {
        val max = (number(spec.opt("max")) ?: 5.0).toInt()
        val wait = number(spec.opt("wait")) ?: 3.0
        val until = spec.opt("until") ?: throw fail("repeat에 until: 조건이 필요함")
        val watch = spec.optString("watch").ifEmpty { null }
        var count = 0
        while (!evaluate(until, 0.0) && count < max) {
            count += 1
            val before = watch?.let { prefValue(it) }?.let { formatPref(it) }
            runSteps(spec.optJSONArray("steps") ?: JSONArray())
            if (watch != null) {
                val deadline = now() + (wait * 1000).toLong()
                var last = before
                var lastChange = now()
                while (now() < deadline) {
                    val cur = prefValue(watch)?.let { formatPref(it) }
                    if (cur != last) { last = cur; lastChange = now() }
                    if (last != before && now() - lastChange >= 1000) break
                    sleep(0.2)
                }
                if (evaluate(until, 0.0)) break
            } else if (evaluate(until, wait)) break
        }
        val done = evaluate(until, 0.0)
        note("반복 ${count}번 → 조건 ${if (done) "충족" else "미충족"}: ${compact(until)}")
        if (!done && spec.opt("required") != false) throw fail("${max}번 반복해도 조건을 만족하지 못함: ${compact(until)}")
    }

    private fun pinchTo(spec: JSONObject) {
        val on = spec.opt("on")
        waitFor(on, 5.0)
        val key = spec.optString("pref")
        val target = number(spec.opt("target"))
        val gain = number(spec.opt("gain"))
        if (key.isEmpty() || target == null || gain == null || gain <= 0) throw fail("pinch-to: { on, pref, target, gain } 형식")
        var current = prefValue(key)?.let { numberOf(it) }
        if (current == null) {
            screen.pinch(find(on)!!, 2.0)
            val end = now() + ((number(spec.opt("wait")) ?: 10.0) * 1000).toLong()
            while (current == null && now() < end) { sleep(0.3); current = prefValue(key)?.let { numberOf(it) } }
        }
        val startValue = current ?: throw fail("앱 설정에 '$key' 숫자 값이 없음 (${prefsNote()})")
        val tapOut = spec.optString("out") == "two-finger-tap"
        val gainOut = number(spec.opt("gain-out")) ?: (if (tapOut) 1.0 else gain / 4)
        val perLog2 = gain / (ln(10.0) / ln(2.0))
        var remaining = target - startValue
        val pinches = mutableListOf<Double>()
        val limit = (number(spec.opt("max")) ?: 12.0).toInt()
        while (abs(remaining) > 0.2 && pinches.size < limit) {
            if (remaining > 0) {
                val s = minOf(gain, remaining); pinches += 2.0.pow(s / perLog2); remaining -= s
            } else {
                val s = minOf(gainOut, -remaining); pinches += 0.5.pow(s / gainOut); remaining += s
            }
        }
        for (scale in pinches) {
            val node = find(on) ?: break
            if (scale < 1 && tapOut) {
                if (ln(1 / scale) / ln(2.0) * gainOut >= gainOut / 2) screen.twoFingerTap(node)
                sleep(0.6); continue
            }
            screen.pinch(node, scale, steps = 15)
            sleep(0.2)
        }
        val before = formatPref(startValue)
        var last = before
        var lastChange = now()
        val deadline = now() + ((number(spec.opt("wait")) ?: 10.0) * 1000).toLong()
        while (pinches.isNotEmpty() && now() < deadline) {
            val cur = prefValue(key)?.let { formatPref(it) } ?: last
            if (cur != last) { last = cur; lastChange = now() }
            if (last != before && now() - lastChange >= 1000) break
            sleep(0.2)
        }
        val outCount = pinches.count { it < 1 }
        val inCount = pinches.size - outCount
        val how = if (!(tapOut && outCount > 0)) "핀치 ${pinches.size}번 연달아"
            else if (inCount == 0) "두 손가락 탭 ${outCount}번 연달아" else "핀치 ${inCount}번 + 두 손가락 탭 ${outCount}번 연달아"
        note("$key $before → $last (목표 ${formatPref(target)}, $how)")
    }

    // ───────────────────────────── 조건 ─────────────────────────────

    fun evaluate(raw: Any, timeout: Double): Boolean {
        val deadline = now() + (timeout * 1000).toLong()
        do {
            if (check(raw)) return true
            if (timeout > 0) { pollInterrupts(); sleep(0.3) }
        } while (now() < deadline)
        return false
    }

    private fun check(raw: Any?): Boolean {
        val c = raw as? JSONObject
        val key = c?.keys()?.asSequence()?.firstOrNull() ?: throw fail("조건 형식 오류: ${compact(raw)}")
        val value = c.get(key)
        val tree = screen.tree()
        return when (key) {
            "exists" -> find(value, tree) != null
            "missing" -> find(value, tree) == null
            "visible" -> find(value, tree)?.let { screen.isVisible(it) } == true
            "hidden" -> find(value, tree)?.let { screen.isVisible(it) } != true
            "selected" -> find(value, tree)?.selected == true
            "hittable" -> find(value, tree)?.let { screen.isHittable(it, tree) } == true
            "not-hittable" -> find(value, tree)?.let { screen.isHittable(it, tree) } != true
            "right-of" -> {
                val pair = value as? JSONArray
                if (pair == null || pair.length() != 2) throw fail("right-of: [A, B] 형식")
                val a = find(pair.get(0), tree); val b = find(pair.get(1), tree)
                a != null && b != null && a.bounds.centerX() > b.bounds.centerX()
            }
            "contains" -> {
                val spec = value as? JSONObject ?: throw fail("contains: { target, text } 형식")
                val e = find(spec.opt("target"), tree)
                e != null && e.label.contains(text(spec.opt("text")), ignoreCase = true)
            }
            "equals" -> {
                val pair = value as? JSONArray
                if (pair == null || pair.length() != 2) throw fail("equals: [a, b] 형식")
                text(pair.get(0)) == text(pair.get(1))
            }
            "changed" -> {
                val spec = value as? JSONObject
                val before = spec?.optString("since")?.let { snapshots[it] }
                    ?: throw fail("changed: { of, since: 스냅샷 } — 스냅샷이 없음")
                shotOf(spec.opt("of")) != before
            }
            "pref" -> {
                val spec = value as? JSONObject
                val k = spec?.optString("key")?.ifEmpty { null } ?: throw fail("pref: { key, gte|lte|gt|lt|eq|ne|exists } 형식")
                val actual = prefValue(k)
                if (spec.has("exists")) return (actual != null) == spec.optBoolean("exists")
                if (actual == null) return false
                numberOf(actual)?.let { n ->
                    number(spec.opt("gte"))?.let { return n >= it }
                    number(spec.opt("lte"))?.let { return n <= it }
                    number(spec.opt("gt"))?.let { return n > it }
                    number(spec.opt("lt"))?.let { return n < it }
                }
                if (spec.has("eq")) return formatPref(actual) == text(spec.get("eq")) ||
                    (numberOf(actual) != null && numberOf(actual) == number(spec.get("eq")))
                if (spec.has("ne")) return formatPref(actual) != text(spec.get("ne"))
                throw fail("pref 비교 연산이 없음 (gte/lte/gt/lt/eq/ne/exists)")
            }
            "not" -> !check(value)
            "all" -> (value as? JSONArray)?.let { a -> (0 until a.length()).all { check(a.get(it)) } } ?: true
            "any" -> (value as? JSONArray)?.let { a -> (0 until a.length()).any { check(a.get(it)) } } ?: false
            else -> throw fail("알 수 없는 조건: $key")
        }
    }

    private fun frontmost(raw: Any): Any {
        val c = raw as? JSONObject ?: return raw
        if (c.length() != 1) return raw
        val key = c.keys().next()
        val value = c.get(key)
        return when (key) {
            "visible" -> JSONObject().put("hittable", value)
            "missing", "hidden" -> JSONObject().put("not-hittable", value)
            "all", "any" -> JSONObject().put(key, JSONArray().also { a ->
                val arr = value as? JSONArray ?: JSONArray()
                for (i in 0 until arr.length()) a.put(frontmost(arr.get(i)))
            })
            else -> raw
        }
    }

    // ───────────────────────────── 대상 ─────────────────────────────

    /** 대상 → 지금 화면의 노드 (없으면 null). 매번 새로 찾는다 (XCUIElement처럼 지연 조회). */
    fun find(raw: Any?, tree: Screen.Tree = screen.tree()): Screen.Node? {
        val all = tree.topFirst()
        if (raw is String) {
            val id = text(raw)
            return all.firstOrNull { it.id == id || it.resourceId == id }
        }
        val spec = raw as? JSONObject ?: return null
        spec.opt("alert-button")?.let { b ->
            val label = text(b)
            return all.firstOrNull { it.type == "Button" && it.label.equals(label, ignoreCase = true) }
        }
        if (spec.has("alert-field")) {
            // 맨 위 창(대화상자)의 첫 입력칸
            return all.firstOrNull { it.type == "TextField" || it.type == "SecureTextField" || it.editable }
        }
        spec.opt("segment")?.let { seg ->
            val group = all.firstOrNull { it.id == text(seg) } ?: return null
            val label = text(spec.opt("label") ?: "")
            return group.descendants().firstOrNull { it.label == label }
        }
        var candidates: Sequence<Screen.Node> = all
        spec.opt("in")?.let { scope -> candidates = find(scope, tree)?.descendants() ?: return null }
        // row: 글자 — 그 글자와 같은 줄(세로 가운데가 겹치는)에 있는 요소. ID가 모두 같은 토글 목록(Compose)에서
        // "알림" 줄의 스위치처럼 고를 때: { id: settingSwitch, row: 알림 }
        spec.opt("row")?.let { r ->
            val rowText = text(r)
            val label = candidates.firstOrNull { it.label == rowText || it.text == rowText } ?: return null
            val cy = label.bounds.centerY()
            candidates = candidates.filter { c ->
                c !== label && abs(c.bounds.centerY() - cy) <= maxOf(label.bounds.height(), c.bounds.height()) / 2
            }
        }
        if (spec.has("cell")) {
            val cellId = text(spec.get("cell"))
            var cells = candidates.filter { it.type == "Cell" && (cellId == "*" || it.id == cellId) }
            spec.optJSONObject("has")?.let { has -> cells = cells.filter { c -> c.descendants().any { matches(it, has) } } }
            return pick(cells, spec)
        }
        val type = Screen.typeName(spec.optString("type").ifEmpty { null })
        if (type != null) candidates = candidates.filter { it.type == type }
        return pick(candidates.filter { matches(it, spec) }, spec)
    }

    private fun matches(n: Screen.Node, spec: JSONObject): Boolean {
        spec.opt("id")?.let { val id = text(it); if (n.id != id && n.resourceId != id) return false }
        spec.opt("label")?.let { val l = text(it); if (n.label != l && n.text != l && n.desc != l) return false }
        spec.opt("contains")?.let { val s = text(it); if (!n.label.contains(s, true) && !n.desc.contains(s, true)) return false }
        return true
    }

    private fun pick(seq: Sequence<Screen.Node>, spec: JSONObject): Screen.Node? {
        val index = number(spec.opt("index"))?.toInt() ?: return seq.firstOrNull()
        return seq.drop(index).firstOrNull()
    }

    // ───────────────────────────── 도움 함수 ─────────────────────────────

    private fun waitFor(target: Any?, timeout: Double, what: Any? = target) {
        if (find(target) != null) return
        val deadline = now() + (timeout * 1000).toLong()
        do {
            pollInterrupts()
            sleep(0.5)
            if (find(target) != null) return
        } while (now() < deadline)
        throw fail("${timeout.toInt()}초 안에 나타나지 않음: ${compact(what)}")
    }

    /** 누르기 직전: 위치가 두 번 연달아 같을 때까지 (최대 2초). 마지막에 본 노드를 돌려준다. */
    private fun waitUntilSettled(target: Any?): Screen.Node? {
        val deadline = now() + 2000
        var last = find(target)
        while (now() < deadline) {
            sleep(0.1)
            val cur = find(target)
            if (cur != null && last != null && cur.bounds == last.bounds) return cur
            last = cur
        }
        return last
    }

    private fun shotOf(target: Any?): String {
        val node = find(target) ?: return ""
        return screen.digest(screen.screenshotPng(screen.visibleRect(node)))
    }

    private fun extract(source: String, pattern: String?): String {
        if (pattern == null) return source
        val m = Regex(pattern).find(source) ?: throw fail("'$source'에서 패턴 ${pattern}을 찾지 못함")
        return if (m.groups.size > 1) m.groups[1]?.value ?: "" else m.value
    }

    /** 앱 설정: SharedPreferences XML 전부에서 key를 찾는다 (run-as → debuggable 빌드만). */
    private fun prefValue(key: String): Any? {
        val list = screen.shell("run-as ${app.pkg} ls shared_prefs").lines().filter { it.endsWith(".xml") }
        for (file in list) {
            val xml = screen.shell("run-as ${app.pkg} cat shared_prefs/$file")
            parsePrefs(xml)[key]?.let { return it }
        }
        return null
    }

    private fun parsePrefs(xml: String): Map<String, Any> {
        val out = mutableMapOf<String, Any>()
        try {
            val p = Xml.newPullParser()
            p.setInput(xml.reader())
            var ev = p.eventType
            while (ev != XmlPullParser.END_DOCUMENT) {
                if (ev == XmlPullParser.START_TAG && p.name != "map") {
                    val name = p.getAttributeValue(null, "name")
                    val v = p.getAttributeValue(null, "value")
                    if (name != null) when (p.name) {
                        "int", "long" -> v?.toLongOrNull()?.let { out[name] = it }
                        "float" -> v?.toDoubleOrNull()?.let { out[name] = it }
                        "boolean" -> v?.let { out[name] = it == "true" }
                        "string" -> out[name] = p.nextText()
                    }
                }
                ev = p.next()
            }
        } catch (e: Exception) { /* 깨진 파일은 건너뛴다 */ }
        return out
    }

    private fun prefsNote() = "안드로이드: ${app.pkg}의 SharedPreferences (run-as, debuggable 빌드만)"

    private fun numberOf(v: Any): Double? = when (v) {
        is Boolean -> null
        is Number -> v.toDouble()
        is String -> v.toDoubleOrNull()
        else -> null
    }

    private fun formatPref(v: Any): String {
        val d = numberOf(v) ?: return v.toString()
        return if (d == Math.rint(d)) d.toLong().toString() else "%.2f".format(d)
    }

    private fun mergeVars(raw: Any?) {
        val o = raw as? JSONObject ?: return
        for (k in o.keys()) vars[k] = text(o.get(k))
    }

    private val varRe = Regex("""\{(secret:)?([A-Za-z0-9_\-]+)\}""")

    fun text(raw: Any?): String {
        if (raw == null || raw == JSONObject.NULL) return ""
        val s = raw as? String ?: raw.toString()
        if (!s.contains("{")) return s
        return varRe.replace(s) { m ->
            val key = m.groupValues[2]
            if (m.groupValues[1].isNotEmpty()) secrets[key] ?: "" else vars[key] ?: "{$key}"
        }
    }

    private fun number(raw: Any?): Double? = when (raw) {
        is Number -> raw.toDouble()
        is String -> raw.toDoubleOrNull()
        else -> null
    }

    private fun describe(step: JSONObject): String {
        if (step.has("group")) return "▸ ${step.optString("group")}"
        val skip = setOf("then", "else", "timeout", "hold", "message", "vars", "steps")
        val key = step.keys().asSequence().firstOrNull { it !in skip } ?: "?"
        return "$key ${compact(step.opt(key))}"
    }

    private fun compact(value: Any?): String {
        if (value is String) return value
        val s = when (value) {
            is JSONObject -> sorted(value).toString()
            is JSONArray -> value.toString()
            null -> "null"
            else -> value.toString()
        }
        return if (s.length > 140) s.take(140) + "…" else s
    }

    /** iOS의 sortedKeys JSON과 같은 문구가 나오게 키를 정렬 */
    private fun sorted(o: JSONObject): Any {
        val out = StringBuilder("{")
        o.keys().asSequence().sorted().forEachIndexed { i, k ->
            if (i > 0) out.append(",")
            val v = o.get(k)
            out.append(JSONObject.quote(k)).append(":")
                .append(if (v is JSONObject) sorted(v) else if (v is String) JSONObject.quote(v) else v.toString())
        }
        return out.append("}")
    }

    private fun fail(message: String) = QAFailure(message)
}

/** 대상 앱 실행·상태 */
class AppControl(val screen: Screen, val pkg: String) {
    fun launch() {
        val comp = screen.shell("cmd package resolve-activity --brief -a android.intent.action.MAIN " +
            "-c android.intent.category.LAUNCHER $pkg").trim().lines().lastOrNull()?.trim() ?: ""
        if (!comp.contains("/")) throw QAFailure("$pkg 가 기기에 없거나 실행할 화면이 없음 (qakit build-app)")
        screen.shell("am force-stop $pkg")
        // 다른 앱 화면(설정 검색, 브라우저 로그인 등)이 이 앱 작업 위에 남아 있으면 force-stop으로 안 닫힌다 → 작업째 비우고 시작
        screen.shell("am start -W --activity-clear-task -n $comp")
        val end = SystemClock.elapsedRealtime() + 20000
        while (!isForeground() && SystemClock.elapsedRealtime() < end) SystemClock.sleep(200)
        if (!isForeground()) throw QAFailure("앱이 20초 안에 화면 맨 앞에 뜨지 않음: $pkg")
    }

    fun isForeground() = screen.foreground() == pkg

    fun isRunning() = screen.shell("pidof $pkg").isNotBlank()

    /** iOS XCUIApplication.State 숫자와 맞춘다: 1 꺼짐, 3 뒤, 4 앞 */
    fun state() = if (isForeground()) 4 else if (isRunning()) 3 else 1
}
