//
//  Waits.swift
//  QAKit
//
//  sleep 대신 쓰는 대기 유틸.
//

import XCTest

@MainActor
public enum QAWait {

    /// 여러 후보 중 먼저 나타나는 것의 키를 돌려준다. 시간 안에 아무것도 없으면 nil.
    /// 예) 로그인 상태 판별: waitForAny(["main": mainButton, "login": loginButton], timeout: 30)
    public static func forAny(
        _ candidates: [String: XCUIElement],
        timeout: TimeInterval,
        poll: TimeInterval = 0.5
    ) -> String? {
        let deadline = Date().addingTimeInterval(timeout)
        let ordered = candidates.sorted { $0.key < $1.key }
        repeat {
            for (key, element) in ordered where element.exists { return key }
            RunLoop.current.run(until: Date().addingTimeInterval(poll))
        } while Date() < deadline
        return nil
    }

    /// 요소가 사라지거나 화면 밖으로 나갈 때까지 기다린다. (하단 시트·드로어 닫힘 판정)
    @discardableResult
    public static func forOffscreen(_ element: XCUIElement, in app: XCUIApplication,
                                    timeout: TimeInterval, poll: TimeInterval = 0.3) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        repeat {
            if !element.isVisibleOnScreen(in: app) { return true }
            RunLoop.current.run(until: Date().addingTimeInterval(poll))
        } while Date() < deadline
        return !element.isVisibleOnScreen(in: app)
    }

    /// 요소가 사라질 때까지 기다린다.
    @discardableResult
    public static func forDisappear(_ element: XCUIElement, timeout: TimeInterval) -> Bool {
        let predicate = NSPredicate(format: "exists == false")
        let expectation = XCTNSPredicateExpectation(predicate: predicate, object: element)
        return XCTWaiter().wait(for: [expectation], timeout: timeout) == .completed
    }
}

@MainActor
public extension XCUIElement {

    /// 존재하고 프레임이 화면 안에 있는지 (exists는 화면 밖 요소도 true)
    func isVisibleOnScreen(in app: XCUIApplication) -> Bool {
        guard exists else { return false }
        let frame = self.frame
        let screen = app.frame
        return !frame.isEmpty && frame.minY < screen.maxY && frame.maxY > screen.minY
            && frame.minX < screen.maxX && frame.maxX > screen.minX
    }

    /// 나타날 때까지 기다린 뒤 탭. 없으면 실패.
    func waitAndTap(timeout: TimeInterval = 10, file: StaticString = #filePath, line: UInt = #line) {
        guard waitForExistence(timeout: timeout) else {
            XCTFail("요소가 \(Int(timeout))초 안에 나타나지 않음: \(self)", file: file, line: line)
            return
        }
        tap()
    }

    /// 기존 내용을 지우고 입력. secure: true면 실패 메시지에 값을 남기지 않는다.
    func clearAndType(_ text: String, timeout: TimeInterval = 10, file: StaticString = #filePath, line: UInt = #line) {
        guard waitForExistence(timeout: timeout) else {
            XCTFail("입력 칸이 \(Int(timeout))초 안에 나타나지 않음: \(identifier)", file: file, line: line)
            return
        }
        tap()
        if let current = value as? String, !current.isEmpty, current != placeholderValue {
            typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: current.count))
        }
        typeText(text)
    }
}
