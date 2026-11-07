//
//  QAScenarioRunner.swift
//  QAKit
//
//  시나리오 파일(.qa.yml → CLI가 JSON으로 변환)을 읽어 단계별로 실행하는 범용 실행기.
//  앱마다 Swift 테스트를 작성·컴파일하지 않고 파일만으로 QA를 돌린다.
//
//  단계(step) — 맵 하나에 동작 키 하나:
//    tap: <대상>                         기다렸다가 탭
//    input: { tap?: <대상>, alert: 글자, confirm: 버튼 }   시스템 입력 알림에 입력
//    type: { into: <대상>, text: 글자 }
//    wait: <대상> | { for: <대상>, timeout: 초 }
//    wait-any: { candidates: { 키: <대상>, … }, as: 변수, timeout: 초 }
//    if: <조건> / unless: <조건>, then: [단계], else: [단계]
//    read: { from: <대상>, pattern: 정규식(첫 그룹), as: 변수 }
//    scroll-to: { target: <대상>, in: <대상>, dir: up, max: 8 }
//    swipe: { on: <대상>, dir: up|down|left|right }
//    pinch: { on: <대상>, scale: 2.5, velocity: 2 }
//    pinch-to: { on: <대상>, pref: 키, target: 값, gain: scale 10 한 번의 변화량, gain-out?: 축소 한 번의 변화량, out?: pinch|two-finger-tap }   필요한 핀치를 계산해 연달아
//    two-finger-tap: <대상> | { on: <대상>, count: 1, settle: 0.6 }   두 손가락 탭 (지도: 가운데 기준 1단계 축소)
//    snapshot: { of: <대상>, as: 이름 }
//    expect: <조건>, timeout?: 초, hold?: 초, message?: 글자
//    hide-keyboard: true (키보드가 버튼을 가릴 때)
//    repeat: { until: <조건>, max: 5, wait: 3, watch?: 설정키, steps: [단계] }   조건이 맞을 때까지 반복
//    read-pref: { key: 키, as: 변수 }      앱 설정(UserDefaults) 값 읽기
//    note: 글자 / relaunch: true / group: 이름 + steps (use: 가 펼쳐진 것) / fail: 글자
//
//  맨 위 interrupts: [ if/unless + then ] — 언제 뜰지 모르는 팝업. 단계마다 실행 전에 확인해 처리
//
//  대상(target):
//    "ID"  |  { id, label, contains, type, in: <대상>, index }
//    { cell: 셀ID, has: { id?, label?, contains? } }     셀 안에 조건에 맞는 요소가 있는 셀
//    { segment: 세그먼트ID, label: 항목 }   { alert-button: 버튼 }   { alert-field: true }
//
//  조건: exists / missing / visible / hidden / selected / hittable: <대상>
//        right-of: [A, B]  contains: { target, text }  equals: [a, b]
//        changed: { of: <대상>, since: 스냅샷 }  pref: { key, gte|lte|gt|lt|eq|ne|exists }  not / all / any
//
//  글자 안의 {변수}, {secret:KEY}는 실행 시 바뀐다. 단계 제목에는 원문({secret:…})만 남는다.
//

import XCTest

@MainActor
public final class QAScenarioRunner {

    private let testCase: QATestCase
    /// false면 실패를 XCTFail로 기록하지 않고 오류로만 던진다 (상주 실행기: 실패해도 테스트가 끝나면 안 됨)
    public var recordsFailures = true
    /// 지나간 단계 이름 (상주 실행기의 실패 요약 "마지막 단계". 일반 실행은 xcresult의 활동 기록을 쓴다)
    public private(set) var trail: [String] = []
    /// 걸린 시간 기록 (상주 실행기 응답 → qakit의 output.log·QAKIT_TIMING). kind: launch / step / group, depth: 묶음 안 깊이
    public private(set) var timings: [[String: Any]] = []
    private var depth = 0
    private var vars: [String: String] = [:]
    private var snapshots: [String: Data] = [:]
    private var app: XCUIApplication { testCase.app }

    public init(testCase: QATestCase) {
        self.testCase = testCase
    }

    /// 시나리오 JSON 파일 실행
    public func run(fileAt path: String) throws {
        try run(json: try Data(contentsOf: URL(fileURLWithPath: path)))
    }

    /// 시나리오 JSON 실행 (실기기: Mac 파일을 읽을 수 없어 qakit이 내용을 base64로 넘긴다)
    public func run(json data: Data) throws {
        guard let root = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw fail("시나리오 형식 오류: 맨 위가 맵이 아님")
        }
        mergeVars(root["vars"])
        interrupts = flattenInterrupts(root["interrupts"] as? [Any] ?? [])
        testCase.note("시나리오: \(root["name"] as? String ?? "(이름 없음)")")
        if (root["launch"] as? String) == "reuse", QAConfig.value("RESET") != "1" {
            try reuseOrLaunch(start: root["start"])
        } else if (root["launch"] as? Bool) != false {
            let t = Date()
            testCase.launchApp()
            timings.append(["kind": "launch", "name": "앱 실행", "seconds": Date().timeIntervalSince(t), "depth": 0])
        }
        try runSteps(root["steps"] as? [Any] ?? [])
        if let signal = QAConfig.value("BENCH_SIGNAL"), let seconds = Double(QAConfig.value("BENCH_SECONDS") ?? "") {
            try benchHold(signal: signal, seconds: seconds)
        }
    }

    /// launch: reuse — 앱이 이미 떠 있고 시작 화면(start: 조건)이 맞으면 다시 켜지 않는다 (앱 실행 몇 초 절약).
    /// 조건이 없거나, 앱이 꺼져 있거나, 시작 화면이 아니면 지금처럼 다시 켠다.
    private func reuseOrLaunch(start: Any?) throws {
        let t = Date()
        var reason = "start: 조건이 없음"
        if let start {
            let candidate = QAApp.make()
            switch candidate.state {
            case .runningForeground, .runningBackground, .runningBackgroundSuspended:
                if candidate.state != .runningForeground { candidate.activate() }
                testCase.app = candidate
                if try evaluate(start, timeout: 2) {
                    testCase.note("앱 재실행 생략: 시작 화면 확인 (\(compact(start)))")
                    timings.append(["kind": "launch", "name": "앱 재실행 생략 (시작 화면 확인)",
                                    "seconds": Date().timeIntervalSince(t), "depth": 0])
                    return
                }
                reason = "시작 화면이 아님"
            default:
                reason = "앱이 실행 중이 아님"
            }
        }
        testCase.note("앱 다시 실행 (\(reason))")
        testCase.launchApp()
        timings.append(["kind": "launch", "name": "앱 실행 (\(reason))", "seconds": Date().timeIntervalSince(t), "depth": 0])
    }

    /// qakit run --bench: 마지막 단계 뒤 앱을 그 상태로 켜 둔 채, qakit이 측정을 끝낼 때까지 기다린다.
    /// 시작은 `<signal>.ready` 파일로 알리고, qakit이 `<signal>.done`을 만들면 끝낸다.
    private func benchHold(signal: String, seconds: Double) throws {
        if QAConfig.isDevice {
            // 실기기: Mac의 신호 파일을 볼 수 없다 → 출력 줄로 시작을 알리고, 측정 시간 + 여유만큼 그대로 둔다
            let lead = Double(QAConfig.value("BENCH_LEAD") ?? "") ?? 30
            print("[qakit-bench] ready")
            testCase.note("성능 측정 시작: \(Int(seconds))초 동안 앱을 이 상태로 둔다")
            let end = Date().addingTimeInterval(seconds + lead)
            while Date() < end {
                if app.state != .runningForeground {
                    throw fail("성능 측정 중 앱이 종료되거나 화면에서 내려감 (상태 \(app.state.rawValue))")
                }
                // 기기와 주고받는 양을 줄인다 (무선에서 Time Profiler 녹화와 같이 쓰면 연결이 끊길 수 있음)
                RunLoop.current.run(until: min(end, Date().addingTimeInterval(10)))
            }
            testCase.note("성능 측정 끝")
            return
        }
        let fm = FileManager.default
        fm.createFile(atPath: signal + ".ready", contents: Data("ready".utf8))
        testCase.note("성능 측정 시작: \(Int(seconds))초 동안 앱을 이 상태로 둔다")
        let deadline = Date().addingTimeInterval(seconds * 2 + 900)   // 측정 + Time Profiler 정리 시간
        while !fm.fileExists(atPath: signal + ".done") {
            if Date() > deadline { throw fail("성능 측정이 끝나지 않음 (qakit의 종료 신호 없음)") }
            if app.state != .runningForeground {
                throw fail("성능 측정 중 앱이 종료되거나 화면에서 내려감 (상태 \(app.state.rawValue))")
            }
            RunLoop.current.run(until: Date().addingTimeInterval(2))
        }
        testCase.note("성능 측정 끝")
    }

    /// 단계 하나 실행 (상주 실행기의 /step). 변수·스냅샷은 같은 실행기 인스턴스 안에서 이어진다.
    public func runStep(json data: Data) throws {
        let raw = try JSONSerialization.jsonObject(with: data)
        try runStep(raw)
    }

    // MARK: - Steps

    private func runSteps(_ steps: [Any]) throws {
        for step in steps { try runStep(step) }
    }

    private func runStep(_ raw: Any) throws {
        guard let step = raw as? [String: Any] else { throw fail("단계 형식 오류: \(raw)") }
        let started = Date()
        var interruptSeconds = 0.0
        if step["group"] == nil {
            try handleInterrupts(before: step)
            interruptSeconds = Date().timeIntervalSince(started)
            currentStep = step
        }
        trail.append(describe(step))
        if trail.count > 50 { trail.removeFirst(trail.count - 50) }
        let index = timings.count
        timings.append([:])   // 자리를 먼저 잡아 묶음이 안쪽 단계보다 앞에 오게
        depth += 1
        defer {
            depth -= 1
            var row: [String: Any] = ["kind": step["group"] == nil ? "step" : "group", "name": describe(step),
                                      "seconds": Date().timeIntervalSince(started), "depth": depth]
            if interruptSeconds >= 0.05 { row["interrupts"] = interruptSeconds }
            timings[index] = row
        }
        try XCTContext.runActivity(named: describe(step)) { _ in try execute(step) }
    }

    // MARK: - 끼어드는 화면 (interrupts)
    // 시나리오 맨 위 `interrupts:` — 언제 뜰지 모르는 팝업(안내·광고 등)을 단계마다 실행 전에 확인해 처리한다.
    //   interrupts:
    //     - if: { contains: { target: PopupView.titleLabel, text: 항해 보조 장치 } }
    //       then: [ tap: PopupView.actionButton ]
    // 조건은 기다리지 않고 지금 화면만 본다. 단계가 기다리는 동안에도 1초마다 다시 확인한다 (늦게 뜨는 팝업). `use:`로 공통 단계 파일을 넣으면 그 안의 if 단계들이 모두 interrupt가 된다.

    private var interrupts: [[String: Any]] = []
    private var handlingInterrupt = false
    private var currentStep: [String: Any] = [:]
    private var lastInterruptPoll = Date.distantPast

    /// 단계가 기다리는 동안(wait·tap·wait-any·timeout 있는 조건) 1초에 한 번씩 interrupt를 다시 확인한다.
    /// 기다리는 사이에 늦게 뜬 팝업이 화면을 막아 단계가 시간 초과로 실패하지 않게.
    private func pollInterrupts() throws {
        guard !interrupts.isEmpty, !handlingInterrupt, Date().timeIntervalSince(lastInterruptPoll) >= 1 else { return }
        lastInterruptPoll = Date()
        try handleInterrupts(before: currentStep)
    }

    private func flattenInterrupts(_ items: [Any]) -> [[String: Any]] {
        items.flatMap { item -> [[String: Any]] in
            guard let step = item as? [String: Any] else { return [] }
            if step["group"] != nil { return flattenInterrupts(step["steps"] as? [Any] ?? []) }
            return (step["if"] ?? step["unless"]) != nil ? [step] : []
        }
    }

    /// 단계·interrupt 안의 ID처럼 보이는 글자들 (점이 들어간 것)
    private func ids(in value: Any) -> Set<String> {
        if let s = value as? String { return s.contains(".") ? [s] : [] }
        if let a = value as? [Any] { return a.reduce(into: Set<String>()) { $0.formUnion(ids(in: $1)) } }
        if let d = value as? [String: Any] { return d.values.reduce(into: Set<String>()) { $0.formUnion(ids(in: $1)) } }
        return []
    }

    private func handleInterrupts(before current: [String: Any]) throws {
        guard !interrupts.isEmpty, !handlingInterrupt else { return }
        handlingInterrupt = true
        defer { handlingInterrupt = false }
        let currentIDs = ids(in: current)
        for step in interrupts {
            // 이 단계가 그 화면을 직접 다루면(같은 ID) 건너뛴다 — 단계가 누르려던 버튼을 먼저 눌러 버리지 않게
            if !currentIDs.isDisjoint(with: ids(in: step)) { continue }
            var hit = try evaluate(step["if"] ?? step["unless"] as Any, timeout: 0)
            if step["unless"] != nil { hit.toggle() }
            guard hit else { continue }
            try XCTContext.runActivity(named: "끼어든 화면 처리: " + describe(step)) { _ in
                testCase.note((step["note"] as? String).map { text($0) } ?? "끼어든 화면 처리")
                try runSteps(step["then"] as? [Any] ?? [])
            }
            // 닫히는 동안(애니메이션) 남아 있는 글자를 다음 단계가 다시 보지 않게, 조건이 풀릴 때까지 잠깐 기다린다
            let end = Date().addingTimeInterval(3)
            while Date() < end {
                var still = try evaluate(step["if"] ?? step["unless"] as Any, timeout: 0)
                if step["unless"] != nil { still.toggle() }
                if !still { break }
                RunLoop.current.run(until: Date().addingTimeInterval(0.3))
            }
        }
    }

    private func execute(_ step: [String: Any]) throws {
        if let name = step["group"] as? String {
            mergeVars(step["vars"])
            _ = name
            try runSteps(step["steps"] as? [Any] ?? [])

        } else if let target = step["tap"] {
            let element = resolve(target)
            try waitFor(element, timeout: number(step["timeout"]) ?? 10, what: target)
            element.tap()

        } else if let spec = step["input"] as? [String: Any] {
            if let tapTarget = spec["tap"] {
                let element = resolve(tapTarget)
                try waitFor(element, timeout: 10, what: tapTarget)
                element.tap()
            }
            let alert = app.alerts.firstMatch
            guard alert.waitForExistence(timeout: 5) else { throw fail("입력 알림이 뜨지 않음") }
            alert.textFields.firstMatch.clearAndType(text(spec["alert"]))
            let confirm = alert.buttons[text(spec["confirm"] ?? "확인")]
            try waitFor(confirm, timeout: 5, what: spec["confirm"] ?? "확인")
            confirm.tap()

        } else if let spec = step["type"] as? [String: Any] {
            let element = resolve(spec["into"] as Any)
            element.clearAndType(text(spec["text"]))

        } else if let target = step["wait"] {
            let spec = target as? [String: Any]
            let what = spec?["for"] ?? target
            try waitFor(resolve(what), timeout: number(spec?["timeout"]) ?? number(step["timeout"]) ?? 10, what: what)

        } else if let spec = step["wait-any"] as? [String: Any] {
            let candidates = (spec["candidates"] as? [String: Any] ?? [:]).mapValues { resolve($0) }
            let timeout = number(spec["timeout"]) ?? 30
            let ordered = candidates.sorted { $0.key < $1.key }
            let deadline = Date().addingTimeInterval(timeout)
            var found: String?
            repeat {
                found = ordered.first { $0.value.exists }?.key
                if found != nil { break }
                try pollInterrupts()
                RunLoop.current.run(until: Date().addingTimeInterval(0.5))
            } while Date() < deadline
            guard let found else {
                throw fail("\(Int(timeout))초 안에 아무것도 나타나지 않음: \(candidates.keys.sorted().joined(separator: ", "))")
            }
            if let name = spec["as"] as? String { vars[name] = found }
            testCase.note("먼저 나타남: \(found)")

        } else if let condition = step["if"] ?? step["unless"] {
            var ok = try evaluate(condition, timeout: number(step["timeout"]) ?? 0)
            if step["unless"] != nil { ok.toggle() }
            try runSteps((ok ? step["then"] : step["else"]) as? [Any] ?? [])

        } else if let spec = step["read"] as? [String: Any] {
            let element = resolve(spec["from"] as Any)
            try waitFor(element, timeout: number(spec["timeout"]) ?? 10, what: spec["from"] as Any)
            let source = element.label.isEmpty ? (element.value as? String ?? "") : element.label
            let value = try extract(source, pattern: spec["pattern"] as? String)
            guard let name = spec["as"] as? String else { throw fail("read에 as: 가 필요함") }
            vars[name] = value
            testCase.note("읽음 \(name) = \(value)")

        } else if let spec = step["scroll-to"] as? [String: Any] {
            let element = resolve(spec["target"] as Any)
            let container = resolve(spec["in"] as Any)
            let max = Int(number(spec["max"]) ?? 8)
            var count = 0
            while !(element.exists && element.isVisibleOnScreen(in: app)) && count < max {
                swipe(container, (spec["dir"] as? String) ?? "up")
                count += 1
            }
            if spec["required"] as? Bool != false, !element.exists {
                throw fail("\(max)번 스크롤해도 찾지 못함: \(compact(spec["target"] as Any))")
            }

        } else if let spec = step["swipe"] as? [String: Any] {
            swipe(resolve(spec["on"] as Any), (spec["dir"] as? String) ?? "up")

        } else if let spec = step["pinch"] as? [String: Any] {
            let element = resolve(spec["on"] as Any)
            try waitFor(element, timeout: 5, what: spec["on"] as Any)
            let scale = CGFloat(number(spec["scale"]) ?? 2)
            // XCUITest 규칙: 확대(scale > 1)는 양수 속도, 축소(scale < 1)는 음수 속도.
            // velocity는 "초당 배율"이라 기본값 2로 scale 10을 하면 동작에만 5초 넘게 걸린다 → 기본은 1초 안팎이 되게
            let speed = abs(CGFloat(number(spec["velocity"]) ?? Double(max(4, scale >= 1 ? scale : 1 / scale))))
            element.pinch(withScale: scale, velocity: scale < 1 ? -speed : speed)
            RunLoop.current.run(until: Date().addingTimeInterval(number(spec["settle"]) ?? 0.5))

        } else if let raw = step["two-finger-tap"] {
            // 대상 가운데를 두 손가락으로 탭. 지도 SDK(Mapbox 등)는 1단계 축소.
            // 축소 핀치는 손가락이 대상 가장자리에서 시작해, 가장자리에 패널이 있으면(아이패드 가로) 그 패널을 끈다 → 가운데만 누르는 이 방식이 안전
            let spec = raw as? [String: Any]
            let target = spec?["on"] ?? raw
            let element = resolve(target)
            try waitFor(element, timeout: 5, what: target)
            for _ in 0..<Int(number(spec?["count"]) ?? 1) {
                element.twoFingerTap()
                RunLoop.current.run(until: Date().addingTimeInterval(number(spec?["settle"]) ?? 0.6))
            }

        } else if let spec = step["pinch-to"] as? [String: Any] {
            // 숫자 앱 설정(예: 지도 줌)이 target이 되도록 필요한 핀치 수를 계산해 기다리지 않고 연달아 한 뒤, 값이 멈출 때 한 번만 본다.
            // gain = scale 10 핀치 한 번에 바뀌는 양(측정값). 핀치 한 번이 바꾸는 양 ≈ log2(scale) × gain / log2(10)
            let element = resolve(spec["on"] as Any)
            try waitFor(element, timeout: 5, what: spec["on"] as Any)
            guard let key = spec["pref"] as? String, let target = number(spec["target"]), let gain = number(spec["gain"]),
                  gain > 0 else { throw fail("pinch-to: { on, pref, target, gain } 형식") }
            var current = prefValue(key).flatMap { ($0 as? NSNumber)?.doubleValue }
            if current == nil {
                // 값이 아직 없으면(한 번도 확대·축소하지 않은 앱) 한 번 핀치해서 값이 생기게 한다
                element.pinch(withScale: 2, velocity: 4)
                let end = Date().addingTimeInterval(number(spec["wait"]) ?? 10)
                while current == nil && Date() < end {
                    RunLoop.current.run(until: Date().addingTimeInterval(0.3))
                    current = prefValue(key).flatMap { ($0 as? NSNumber)?.doubleValue }
                }
            }
            guard let startValue = current else {
                throw fail("앱 설정에 '\(key)' 숫자 값이 없음 (\(prefsPathNote))")
            }
            // 축소 방법 — pinch: scale 0.5 핀치 한 번 = gain-out (빠르게 크게 오므리면 거의 안 먹어 여러 번)
            //            two-finger-tap: 가운데 두 손가락 탭 한 번 = gain-out(기본 1단계). 손가락이 가장자리를 누르지 않는다
            let tapOut = (spec["out"] as? String) == "two-finger-tap"
            let gainOut = number(spec["gain-out"]) ?? (tapOut ? 1 : gain / 4)
            let perLog2 = gain / log2(10)
            var remaining = target - startValue
            var pinches: [Double] = []
            let limit = Int(number(spec["max"]) ?? 12)
            while abs(remaining) > 0.2 && pinches.count < limit {
                if remaining > 0 {
                    let step = min(gain, remaining)                  // 확대: 한 번에 scale 10까지
                    pinches.append(pow(2, step / perLog2))
                    remaining -= step
                } else {
                    let step = min(gainOut, -remaining)              // 축소: scale 0.5 한 번 = gain-out
                    pinches.append(pow(0.5, step / gainOut))
                    remaining += step
                }
            }
            for scale in pinches {
                if scale < 1 && tapOut {
                    // 1단계를 다 못 채우는 나머지(예: 0.4단계)는 탭하면 넘치므로 반 이상일 때만 탭
                    if log2(1 / scale) * gainOut >= gainOut / 2 { element.twoFingerTap() }
                    RunLoop.current.run(until: Date().addingTimeInterval(0.6))   // 축소 애니메이션이 끝난 뒤 다음 탭
                    continue
                }
                let speed = CGFloat(scale >= 1 ? max(4, scale) : 4)
                element.pinch(withScale: CGFloat(scale), velocity: scale < 1 ? -speed : speed)
                RunLoop.current.run(until: Date().addingTimeInterval(0.2))
            }
            // 값이 바뀐 뒤 1초 동안 더 변하지 않을 때까지 (최대 wait초) — UserDefaults는 늦게 쓰인다
            let before = formatPref(startValue as NSNumber)
            var last = before, lastChange = Date()
            let deadline = Date().addingTimeInterval(number(spec["wait"]) ?? 10)
            while !pinches.isEmpty && Date() < deadline {
                let now = prefValue(key).map { formatPref($0) } ?? last
                if now != last { last = now; lastChange = Date() }
                if last != before && Date().timeIntervalSince(lastChange) >= 1.0 { break }
                RunLoop.current.run(until: Date().addingTimeInterval(0.2))
            }
            let outCount = pinches.filter { $0 < 1 }.count
            let inCount = pinches.count - outCount
            let how = !(tapOut && outCount > 0) ? "핀치 \(pinches.count)번 연달아"
                : inCount == 0 ? "두 손가락 탭 \(outCount)번 연달아" : "핀치 \(inCount)번 + 두 손가락 탭 \(outCount)번 연달아"
            testCase.note("\(key) \(before) → \(last) (목표 \(formatPref(target as NSNumber)), \(how))")

        } else if let spec = step["snapshot"] as? [String: Any] {
            let element = resolve(spec["of"] as Any)
            try waitFor(element, timeout: 5, what: spec["of"] as Any)
            let shot = element.screenshot()
            let name = (spec["as"] as? String) ?? "snapshot"
            snapshots[name] = shot.pngRepresentation
            let attachment = XCTAttachment(screenshot: shot)
            attachment.name = "scenario-\(name)"
            attachment.lifetime = .keepAlways
            testCase.add(attachment)

        } else if let condition = step["expect"] {
            let timeout = number(step["timeout"]) ?? 0
            guard try evaluate(condition, timeout: timeout) else {
                throw fail(step["message"] as? String ?? "기대 조건 실패: \(compact(condition))")
            }
            if let hold = number(step["hold"]), hold > 0 {
                let deadline = Date().addingTimeInterval(hold)
                while Date() < deadline {
                    guard try evaluate(condition, timeout: 0) else {
                        throw fail((step["message"] as? String ?? "조건이 유지되지 않음") + " (\(Int(hold))초 유지 필요)")
                    }
                    RunLoop.current.run(until: Date().addingTimeInterval(0.5))
                }
            }

        } else if let message = step["note"] {
            testCase.note(text(message))

        } else if let name = step["dump"] {
            // 지금 화면 구조를 results/dumps/<이름>.txt에 저장. 앱을 다시 켜면 못 가는 화면(세션 중간 화면)을 볼 때 쓴다.
            let output = try QADump.run(app: app, settle: number(step["settle"]) ?? 1, name: text(name))
            let header = output.split(separator: "\n").prefix(4).joined(separator: "\n")
            testCase.note("dump \(text(name)):\n\(header)")

        } else if let spec = step["repeat"] as? [String: Any] {
            let max = Int(number(spec["max"]) ?? 5)
            let wait = number(spec["wait"]) ?? 3
            guard let until = spec["until"] else { throw fail("repeat에 until: 조건이 필요함") }
            // watch: 앱 설정 키. 매 반복 뒤 그 값이 실제로 바뀔 때까지(최대 wait초) 기다렸다가 판정한다.
            // UserDefaults는 디스크에 늦게 쓰여, 그냥 판정하면 옛 값을 보고 한 번 더 반복해 목표를 넘친다.
            let watch = spec["watch"] as? String
            var count = 0
            while try !evaluate(until, timeout: 0) && count < max {
                count += 1
                let before = watch.flatMap { prefValue($0) }.map { formatPref($0) }
                try XCTContext.runActivity(named: "반복 \(count)/\(max)") { _ in
                    try runSteps(spec["steps"] as? [Any] ?? [])
                }
                if let watch {
                    // 값이 바뀐 뒤 1초 동안 더 변하지 않을 때(관성 확대·스크롤이 멈췄을 때) 판정한다
                    let deadline = Date().addingTimeInterval(wait)
                    var last = before
                    var lastChange = Date()
                    while Date() < deadline {
                        let now = prefValue(watch).map { formatPref($0) }
                        if now != last { last = now; lastChange = Date() }
                        if last != before && Date().timeIntervalSince(lastChange) >= 1.0 { break }
                        RunLoop.current.run(until: Date().addingTimeInterval(0.2))
                    }
                    if try evaluate(until, timeout: 0) { break }
                } else if try evaluate(until, timeout: wait) {
                    break
                }
            }
            let done = try evaluate(until, timeout: 0)
            testCase.note("반복 \(count)번 → 조건 \(done ? "충족" : "미충족"): \(compact(until))")
            if !done && spec["required"] as? Bool != false {
                throw fail("\(max)번 반복해도 조건을 만족하지 못함: \(compact(until))")
            }

        } else if let spec = step["read-pref"] as? [String: Any] {
            guard let key = spec["key"] as? String, let name = spec["as"] as? String else {
                throw fail("read-pref: { key, as } 형식")
            }
            guard let value = prefValue(key) else {
                // default: 값이 아직 없을 때 쓸 글자 (예: 새로 설치해 한 번도 확대하지 않은 앱에는 zoom이 없다)
                if let fallback = spec["default"] {
                    vars[name] = text(fallback)
                    testCase.note("앱 설정 \(key) 없음 → \(text(fallback))")
                    return
                }
                throw fail("앱 설정에 '\(key)' 값이 없음 (\(prefsPathNote))")
            }
            vars[name] = formatPref(value)
            testCase.note("앱 설정 \(key) = \(vars[name] ?? "")")

        } else if step["hide-keyboard"] != nil {
            let keyboard = app.keyboards.firstMatch
            if keyboard.exists {
                // iPad 키보드에는 "키보드 내리기" 키가 있다 → 먼저 그 키 (Return은 화면에 따라 입력을 제출해 버릴 수 있음)
                let dismiss = keyboard.buttons.matching(NSPredicate(format:
                    "label CONTAINS[c] 'hide keyboard' OR label CONTAINS[c] 'dismiss' OR label CONTAINS '키보드'"
                    + " OR identifier CONTAINS[c] 'dismiss'")).firstMatch
                let keys = ["Return", "return", "Done", "완료", "확인", "이동"]
                if dismiss.exists {
                    dismiss.tap()
                } else if let key = keys.map({ keyboard.buttons[$0] }).first(where: { $0.exists }) {
                    key.tap()
                } else {
                    keyboard.buttons.allElementsBoundByIndex.last?.tap()
                }
                // 키보드가 실제로 사라질 때까지 (최대 3초) — 남아 있으면 다음 탭이 키보드에 들어간다
                let end = Date().addingTimeInterval(3)
                while keyboard.exists && Date() < end { RunLoop.current.run(until: Date().addingTimeInterval(0.2)) }
            }

        } else if step["relaunch"] != nil {
            app.terminate()
            testCase.launchApp()

        } else if let message = step["fail"] {
            throw fail(text(message))

        } else {
            throw fail("알 수 없는 단계: \(compact(step))")
        }
    }

    // MARK: - Conditions

    private func evaluate(_ raw: Any, timeout: TimeInterval) throws -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        repeat {
            if try check(raw) { return true }
            if timeout > 0 {
                try pollInterrupts()
                RunLoop.current.run(until: Date().addingTimeInterval(0.3))
            }
        } while Date() < deadline
        return false
    }

    private func check(_ raw: Any) throws -> Bool {
        guard let c = raw as? [String: Any], let (key, value) = c.first else {
            throw fail("조건 형식 오류: \(compact(raw))")
        }
        switch key {
        case "exists": return resolve(value).exists
        case "missing": return !resolve(value).exists
        case "visible": return resolve(value).isVisibleOnScreen(in: app)
        case "hidden": return !resolve(value).isVisibleOnScreen(in: app)
        case "selected": let e = resolve(value); return e.exists && e.isSelected
        case "hittable": let e = resolve(value); return e.exists && e.isHittable
        case "right-of":
            guard let pair = value as? [Any], pair.count == 2 else { throw fail("right-of: [A, B] 형식") }
            let a = resolve(pair[0]), b = resolve(pair[1])
            return a.exists && b.exists && a.frame.midX > b.frame.midX
        case "contains":
            guard let spec = value as? [String: Any] else { throw fail("contains: { target, text } 형식") }
            let e = resolve(spec["target"] as Any)
            return e.exists && e.label.localizedCaseInsensitiveContains(text(spec["text"]))
        case "equals":
            guard let pair = value as? [Any], pair.count == 2 else { throw fail("equals: [a, b] 형식") }
            return text(pair[0]) == text(pair[1])
        case "changed":
            guard let spec = value as? [String: Any], let since = spec["since"] as? String,
                  let before = snapshots[since] else { throw fail("changed: { of, since: 스냅샷 } — 스냅샷이 없음") }
            return resolve(spec["of"] as Any).screenshot().pngRepresentation != before
        case "pref":
            guard let spec = value as? [String: Any], let key = spec["key"] as? String else {
                throw fail("pref: { key, gte|lte|gt|lt|eq|ne|exists } 형식")
            }
            let actual = prefValue(key)
            if let want = spec["exists"] as? Bool { return (actual != nil) == want }
            guard let actual else { return false }
            if let n = (actual as? NSNumber)?.doubleValue {
                if let v = number(spec["gte"]) { return n >= v }
                if let v = number(spec["lte"]) { return n <= v }
                if let v = number(spec["gt"]) { return n > v }
                if let v = number(spec["lt"]) { return n < v }
            }
            if let v = spec["eq"] { return formatPref(actual) == text(v) || ((actual as? NSNumber)?.doubleValue == number(v)) }
            if let v = spec["ne"] { return formatPref(actual) != text(v) }
            throw fail("pref 비교 연산이 없음 (gte/lte/gt/lt/eq/ne/exists)")
        case "not": return try !check(value)
        case "all": return try (value as? [Any] ?? []).allSatisfy { try check($0) }
        case "any": return try (value as? [Any] ?? []).contains { try check($0) }
        default: throw fail("알 수 없는 조건: \(key)")
        }
    }

    // MARK: - Targets

    private func resolve(_ raw: Any) -> XCUIElement {
        if let id = raw as? String {
            return app.descendants(matching: .any).matching(identifier: text(id)).firstMatch
        }
        guard let spec = raw as? [String: Any] else {
            return app.descendants(matching: .any).matching(identifier: "__invalid__").firstMatch
        }
        if let button = spec["alert-button"] {
            return app.alerts.firstMatch.buttons[text(button)]
        }
        if spec["alert-field"] != nil {
            return app.alerts.firstMatch.textFields.firstMatch
        }
        if let segment = spec["segment"] {
            return app.segmentedControls[text(segment)].buttons[text(spec["label"] ?? "")]
        }
        let scope: XCUIElement? = spec["in"].map { resolve($0) }
        if let cellID = spec["cell"] {
            let base = (scope?.cells ?? app.cells).matching(identifier: text(cellID))
            let query = spec["has"].map { base.containing(predicate($0 as? [String: Any] ?? [:])) } ?? base
            return pick(query, spec)
        }
        let type = elementType(spec["type"] as? String)
        let base = scope?.descendants(matching: type) ?? app.descendants(matching: type)
        return pick(base.matching(predicate(spec)), spec)
    }

    private func pick(_ query: XCUIElementQuery, _ spec: [String: Any]) -> XCUIElement {
        if let index = number(spec["index"]) { return query.element(boundBy: Int(index)) }
        return query.firstMatch
    }

    private func predicate(_ spec: [String: Any]) -> NSPredicate {
        var parts: [NSPredicate] = []
        if let id = spec["id"] { parts.append(NSPredicate(format: "identifier == %@", text(id))) }
        if let label = spec["label"] { parts.append(NSPredicate(format: "label == %@", text(label))) }
        if let contains = spec["contains"] { parts.append(NSPredicate(format: "label CONTAINS[c] %@", text(contains))) }
        return parts.isEmpty ? NSPredicate(value: true) : NSCompoundPredicate(andPredicateWithSubpredicates: parts)
    }

    private func elementType(_ name: String?) -> XCUIElement.ElementType {
        switch name?.lowercased() {
        case "button": return .button
        case "cell": return .cell
        case "text", "statictext": return .staticText
        case "textfield": return .textField
        case "securetextfield": return .secureTextField
        case "switch": return .switch
        case "image": return .image
        case "segment", "segmentedcontrol": return .segmentedControl
        case "other": return .other
        case "collectionview", "collection": return .collectionView
        case "scrollview", "scroll": return .scrollView
        case "table", "tableview": return .table
        default: return .any
        }
    }

    // MARK: - Helpers

    private func waitFor(_ element: XCUIElement, timeout: TimeInterval, what: Any) throws {
        if element.exists { return }   // 이미 있으면 기다리지 않는다
        // waitForExistence 대신 직접 폴링: 기다리는 동안 늦게 뜬 팝업(interrupts)도 처리한다
        let deadline = Date().addingTimeInterval(timeout)
        repeat {
            try pollInterrupts()
            RunLoop.current.run(until: Date().addingTimeInterval(0.5))
            if element.exists { return }
        } while Date() < deadline
        throw fail("\(Int(timeout))초 안에 나타나지 않음: \(compact(what))")
    }

    private func swipe(_ element: XCUIElement, _ dir: String) {
        switch dir {
        case "down": element.swipeDown()
        case "left": element.swipeLeft()
        case "right": element.swipeRight()
        default: element.swipeUp()
        }
    }

    private func extract(_ source: String, pattern: String?) throws -> String {
        guard let pattern else { return source }
        let regex = try NSRegularExpression(pattern: pattern)
        let range = NSRange(source.startIndex..., in: source)
        guard let m = regex.firstMatch(in: source, range: range) else {
            throw fail("'\(source)'에서 패턴 \(pattern)을 찾지 못함")
        }
        let r = m.numberOfRanges > 1 ? m.range(at: 1) : m.range
        return (source as NSString).substring(with: r)
    }

    /// 앱 설정(UserDefaults) 파일. qakit이 시뮬레이터 앱 데이터 경로를 넘겨 준다 (QA_ARG_APP_PREFS).
    /// UserDefaults는 디스크에 늦게 쓰일 수 있으므로 조건은 timeout으로 기다리며 읽는다.
    private var prefsPathNote: String {
        QAConfig.isDevice ? "실기기: 앱 안 AutoID의 QAKit.prefs 요소" : (QAConfig.value("APP_PREFS") ?? "QA_ARG_APP_PREFS 없음")
    }

    private func prefValue(_ key: String) -> Any? {
        if QAConfig.isDevice {
            // AutoID가 앱 설정 값을 JSON으로 담아 두는 숨은 요소 (0.5초마다 갱신)
            let element = app.descendants(matching: .any).matching(identifier: "QAKit.prefs").firstMatch
            guard element.waitForExistence(timeout: 3), let json = element.value as? String,
                  let dict = try? JSONSerialization.jsonObject(with: Data(json.utf8)) as? [String: Any] else { return nil }
            return dict[key]
        }
        guard let path = QAConfig.value("APP_PREFS"),
              let dict = NSDictionary(contentsOfFile: path) as? [String: Any] else { return nil }
        return dict[key]
    }

    private func formatPref(_ value: Any) -> String {
        if let n = value as? NSNumber, CFGetTypeID(n) != CFBooleanGetTypeID() {
            let d = n.doubleValue
            return d == d.rounded() ? String(Int(d)) : String(format: "%.2f", d)
        }
        return "\(value)"
    }

    private func mergeVars(_ raw: Any?) {
        guard let dict = raw as? [String: Any] else { return }
        for (k, v) in dict { vars[k] = text(v) }
    }

    /// {변수}, {secret:KEY} 치환
    private func text(_ raw: Any?) -> String {
        guard let raw else { return "" }
        var s = (raw as? String) ?? "\(raw)"
        guard s.contains("{") else { return s }
        let regex = try? NSRegularExpression(pattern: #"\{(secret:)?([A-Za-z0-9_\-]+)\}"#)
        let matches = regex?.matches(in: s, range: NSRange(s.startIndex..., in: s)) ?? []
        for m in matches.reversed() {
            let isSecret = m.range(at: 1).location != NSNotFound
            let key = (s as NSString).substring(with: m.range(at: 2))
            let value = isSecret ? (QASecrets.value(key) ?? "") : (vars[key] ?? "{\(key)}")
            s = (s as NSString).replacingCharacters(in: m.range, with: value)
        }
        return s
    }

    private func number(_ raw: Any?) -> Double? {
        if let n = raw as? NSNumber { return n.doubleValue }
        if let s = raw as? String { return Double(s) }
        return nil
    }

    private func describe(_ step: [String: Any]) -> String {
        if let group = step["group"] as? String { return "▸ \(group)" }
        let key = step.keys.first { !["then", "else", "timeout", "hold", "message", "vars", "steps"].contains($0) } ?? "?"
        return "\(key) \(compact(step[key] as Any))"
    }

    private func compact(_ value: Any) -> String {
        if let s = value as? String { return s }
        guard JSONSerialization.isValidJSONObject(value) || value is [Any],
              let data = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys, .fragmentsAllowed]),
              let s = String(data: data, encoding: .utf8) else { return "\(value)" }
        return s.count > 140 ? String(s.prefix(140)) + "…" : s
    }

    private func fail(_ message: String) -> QAError {
        if recordsFailures { XCTFail(message) }
        return .failed(message)
    }
}
