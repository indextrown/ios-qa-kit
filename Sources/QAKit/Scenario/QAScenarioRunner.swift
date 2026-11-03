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
//    snapshot: { of: <대상>, as: 이름 }
//    expect: <조건>, timeout?: 초, hold?: 초, message?: 글자
//    hide-keyboard: true (키보드가 버튼을 가릴 때)
//    repeat: { until: <조건>, max: 5, wait: 3, steps: [단계] }   조건이 맞을 때까지 반복
//    read-pref: { key: 키, as: 변수 }      앱 설정(UserDefaults) 값 읽기
//    note: 글자 / relaunch: true / group: 이름 + steps (use: 가 펼쳐진 것) / fail: 글자
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
    private var vars: [String: String] = [:]
    private var snapshots: [String: Data] = [:]
    private var app: XCUIApplication { testCase.app }

    public init(testCase: QATestCase) {
        self.testCase = testCase
    }

    /// 시나리오 JSON 파일 실행
    public func run(fileAt path: String) throws {
        let data = try Data(contentsOf: URL(fileURLWithPath: path))
        guard let root = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw fail("시나리오 형식 오류: 맨 위가 맵이 아님")
        }
        mergeVars(root["vars"])
        testCase.note("시나리오: \(root["name"] as? String ?? "(이름 없음)")")
        if (root["launch"] as? Bool) != false {
            testCase.launchApp()
        }
        try runSteps(root["steps"] as? [Any] ?? [])
    }

    // MARK: - Steps

    private func runSteps(_ steps: [Any]) throws {
        for step in steps { try runStep(step) }
    }

    private func runStep(_ raw: Any) throws {
        guard let step = raw as? [String: Any] else { throw fail("단계 형식 오류: \(raw)") }
        try XCTContext.runActivity(named: describe(step)) { _ in try execute(step) }
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
            guard let found = QAWait.forAny(candidates, timeout: timeout) else {
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
            element.pinch(withScale: CGFloat(number(spec["scale"]) ?? 2), velocity: CGFloat(number(spec["velocity"]) ?? 2))
            RunLoop.current.run(until: Date().addingTimeInterval(number(spec["settle"]) ?? 1.5))

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

        } else if let spec = step["repeat"] as? [String: Any] {
            let max = Int(number(spec["max"]) ?? 5)
            let wait = number(spec["wait"]) ?? 3
            guard let until = spec["until"] else { throw fail("repeat에 until: 조건이 필요함") }
            var count = 0
            while try !evaluate(until, timeout: 0) && count < max {
                count += 1
                try XCTContext.runActivity(named: "반복 \(count)/\(max)") { _ in
                    try runSteps(spec["steps"] as? [Any] ?? [])
                }
                if try evaluate(until, timeout: wait) { break }
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
            guard let value = prefValue(key) else { throw fail("앱 설정에 '\(key)' 값이 없음 (\(prefsPathNote))") }
            vars[name] = formatPref(value)
            testCase.note("앱 설정 \(key) = \(vars[name] ?? "")")

        } else if step["hide-keyboard"] != nil {
            let keyboard = app.keyboards.firstMatch
            if keyboard.exists {
                let keys = ["Return", "return", "Done", "완료", "확인", "이동"]
                if let key = keys.map({ keyboard.buttons[$0] }).first(where: { $0.exists }) {
                    key.tap()
                } else {
                    keyboard.buttons.allElementsBoundByIndex.last?.tap()
                }
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
            if timeout > 0 { RunLoop.current.run(until: Date().addingTimeInterval(0.3)) }
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
        default: return .any
        }
    }

    // MARK: - Helpers

    private func waitFor(_ element: XCUIElement, timeout: TimeInterval, what: Any) throws {
        guard element.waitForExistence(timeout: timeout) else {
            throw fail("\(Int(timeout))초 안에 나타나지 않음: \(compact(what))")
        }
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
    private var prefsPathNote: String { QAConfig.value("APP_PREFS") ?? "QA_ARG_APP_PREFS 없음" }

    private func prefValue(_ key: String) -> Any? {
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
        XCTFail(message)
        return .timeout(message)
    }
}
