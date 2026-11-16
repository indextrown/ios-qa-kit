//
//  QASynth.swift
//  좌표 터치를 XCTest 이벤트 합성으로 넣는다 (상주 실행기 /touch — AI 직접 터치·라이브 세션·qakit touch).
//
//  비공개 API (Xcode 27에서 확인): XCSynthesizedEventRecord · XCPointerEventPath · XCTRunnerDaemonSession.daemonProxy
//  ._XCT_synthesizeEvent:completion:  — 오픈소스 Maestro의 iOS 드라이버와 같은 방식.
//  시뮬레이터 HID 주입(simtouch)은 부팅에 따라 시뮬레이터 안 경로가 막혀 조용히 무시될 때가 있지만(docs/private-apis.md),
//  이 길은 XCUITest 탭과 같은 테스트 데몬을 거쳐 늘 먹힌다. XCUICoordinate.tap()과 달리 앱이 한가해질 때까지 기다리지 않는다.
//

import UIKit
import XCTest

public enum QASynth {
    public struct Failure: Error, CustomStringConvertible {
        public let description: String
    }

    /// body: {"action": "tap" | "press" | "swipe", "x", "y" (화면 대비 0~1), "x2", "y2" (swipe), "ms" (tap 누름) | "seconds" (press·swipe)}
    /// → {"screen": [폭, 높이], "points": [[x, y], …]} (포인트)
    public static func perform(_ body: [String: Any]) throws -> [String: Any] {
        let action = body["action"] as? String ?? "tap"
        func number(_ key: String) throws -> Double {
            guard let v = (body[key] as? NSNumber)?.doubleValue else { throw Failure(description: "\(key) 없음 (화면 대비 0~1)") }
            return v
        }
        let size = UIScreen.main.bounds.size   // 세로 기준 (기기 회전은 아직 다루지 않음)
        func point(_ x: Double, _ y: Double) -> CGPoint {
            CGPoint(x: min(max(x, 0), 1) * Double(size.width), y: min(max(y, 0), 1) * Double(size.height))
        }
        let start = point(try number("x"), try number("y"))
        var points = [start]
        let record = try makeRecord(name: "qakit \(action)")
        let path = try makePath(at: start)
        let total: Double
        switch action {
        case "tap", "press":
            let hold = action == "tap"
                ? max((body["ms"] as? NSNumber)?.doubleValue ?? 60, 30) / 1000
                : max((body["seconds"] as? NSNumber)?.doubleValue ?? 1, 0.1)
            try liftUp(path, at: hold)
            total = hold
        case "swipe":
            let end = point(try number("x2"), try number("y2"))
            let secs = max((body["seconds"] as? NSNumber)?.doubleValue ?? 0.4, 0.05)
            try move(path, to: end, at: secs)
            try liftUp(path, at: secs + 0.02)
            points.append(end)
            total = secs + 0.02
        default:
            throw Failure(description: "모르는 action: \(action) (tap · press · swipe)")
        }
        try add(path, to: record)
        try synthesize(record, timeout: total + 10)
        return ["screen": [Double(size.width), Double(size.height)], "points": points.map { [Double($0.x), Double($0.y)] }]
    }

    // MARK: 비공개 클래스 (이름으로 찾고 정확한 C 형식으로 부른다 — 형식이 틀리면 죽으므로 Xcode가 바뀌면 docs/reverse-engineering.md로 다시 확인)

    private static func objcClass(_ name: String) throws -> AnyClass {
        guard let cls = NSClassFromString(name) else { throw Failure(description: "\(name)이 없음 (Xcode가 바뀌었을 수 있음)") }
        return cls
    }

    private static func method(_ target: AnyObject, _ name: String) throws -> (Selector, IMP) {
        let sel = NSSelectorFromString(name)
        guard let obj = target as? NSObject, obj.responds(to: sel), let imp = obj.method(for: sel) else {
            throw Failure(description: "\(name)이 없음 (Xcode가 바뀌었을 수 있음)")
        }
        return (sel, imp)
    }

    /// alloc → init… : alloc 결과는 init이 가져가므로(+1을 넘김) 소유하지 않고, init 결과를 소유한다
    private static func allocate(_ cls: AnyClass) -> NSObject {
        typealias Alloc = @convention(c) (AnyClass, Selector) -> Unmanaged<NSObject>
        let sel = NSSelectorFromString("alloc")
        return unsafeBitCast(class_getMethodImplementation(object_getClass(cls), sel), to: Alloc.self)(cls, sel).takeUnretainedValue()
    }

    private static func makeRecord(name: String) throws -> NSObject {
        let allocated = allocate(try objcClass("XCSynthesizedEventRecord"))
        let (sel, imp) = try method(allocated, "initWithName:interfaceOrientation:")
        typealias Init = @convention(c) (NSObject, Selector, NSString, Int) -> Unmanaged<NSObject>?
        guard let record = unsafeBitCast(imp, to: Init.self)(allocated, sel, name as NSString, 1)?.takeRetainedValue() else {   // 1 = 세로
            throw Failure(description: "XCSynthesizedEventRecord를 만들지 못함")
        }
        return record
    }

    private static func makePath(at point: CGPoint) throws -> NSObject {
        let allocated = allocate(try objcClass("XCPointerEventPath"))
        let (sel, imp) = try method(allocated, "initForTouchAtPoint:offset:")
        typealias Init = @convention(c) (NSObject, Selector, CGPoint, Double) -> Unmanaged<NSObject>?
        guard let path = unsafeBitCast(imp, to: Init.self)(allocated, sel, point, 0)?.takeRetainedValue() else {
            throw Failure(description: "XCPointerEventPath를 만들지 못함")
        }
        return path
    }

    private static func move(_ path: NSObject, to point: CGPoint, at offset: Double) throws {
        let (sel, imp) = try method(path, "moveToPoint:atOffset:")
        typealias Move = @convention(c) (NSObject, Selector, CGPoint, Double) -> Void
        unsafeBitCast(imp, to: Move.self)(path, sel, point, offset)
    }

    private static func liftUp(_ path: NSObject, at offset: Double) throws {
        let (sel, imp) = try method(path, "liftUpAtOffset:")
        typealias Lift = @convention(c) (NSObject, Selector, Double) -> Void
        unsafeBitCast(imp, to: Lift.self)(path, sel, offset)
    }

    private static func add(_ path: NSObject, to record: NSObject) throws {
        let (sel, imp) = try method(record, "addPointerEventPath:")
        typealias Add = @convention(c) (NSObject, Selector, NSObject) -> Void
        unsafeBitCast(imp, to: Add.self)(record, sel, path)
    }

    /// 테스트 데몬에 보내고 끝날 때까지 기다린다. 완료 콜백이 메인 큐로 올 수 있어 세마포어 대신 런루프를 돌리며 기다린다.
    private static func synthesize(_ record: NSObject, timeout: Double) throws {
        let sessionClass = try objcClass("XCTRunnerDaemonSession")
        typealias Shared = @convention(c) (AnyClass, Selector) -> Unmanaged<NSObject>?
        let sharedSel = NSSelectorFromString("sharedSession")
        guard let session = unsafeBitCast(class_getMethodImplementation(object_getClass(sessionClass), sharedSel), to: Shared.self)(sessionClass, sharedSel)?
                .takeUnretainedValue(),
              let proxy = session.perform(NSSelectorFromString("daemonProxy"))?.takeUnretainedValue() as? NSObject else {
            throw Failure(description: "테스트 데몬 연결(XCTRunnerDaemonSession.daemonProxy)이 없음")
        }
        let sel = NSSelectorFromString("_XCT_synthesizeEvent:completion:")
        guard let imp = proxy.method(for: sel) else { throw Failure(description: "_XCT_synthesizeEvent:completion:이 없음") }
        typealias Synthesize = @convention(c) (NSObject, Selector, NSObject, @escaping @convention(block) (NSError?) -> Void) -> Void
        var done = false
        var failure: NSError?
        unsafeBitCast(imp, to: Synthesize.self)(proxy, sel, record) { error in
            failure = error
            done = true
        }
        let deadline = Date().addingTimeInterval(timeout)
        while !done && Date() < deadline {
            RunLoop.current.run(until: Date().addingTimeInterval(0.005))
        }
        if !done { throw Failure(description: "이벤트 합성이 \(Int(timeout))초 안에 끝나지 않음") }
        if let failure { throw Failure(description: "이벤트 합성 실패: \(failure.localizedDescription)") }
    }
}
