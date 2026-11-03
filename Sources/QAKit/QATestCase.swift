//
//  QATestCase.swift
//  QAKit
//
//  모든 UI 테스트의 기본 클래스.
//  - 실패하면 그 시점의 화면 구조(텍스트)와 스크린샷을 결과에 첨부한다 → qakit summarize가 읽음
//  - 시스템 팝업 자동 처리
//

import XCTest

@MainActor
open class QATestCase: XCTestCase {

    /// 테스트 중인 앱. setUp 이후 launchApp()/attachApp()으로 채운다.
    public var app: XCUIApplication!

    private var attachedFailureContext = false

    override open func setUp() async throws {
        try await super.setUp()
        continueAfterFailure = false
        attachedFailureContext = false
        QAInterruptions.install(on: self)
    }

    /// 앱 실행 (데이터 유지)
    @discardableResult
    public func launchApp(arguments: [String] = [], environment: [String: String] = [:]) -> XCUIApplication {
        app = QAApp.launch(arguments: arguments, environment: environment)
        return app
    }

    /// 단계 기록. 결과 요약에 "어디까지 진행했는지"로 나타난다.
    public func step<T>(_ name: String, _ body: () throws -> T) rethrows -> T {
        try XCTContext.runActivity(named: name) { _ in try body() }
    }

    /// 결과에 메모 남기기 (예: "이미 로그인됨")
    public func note(_ text: String) {
        let attachment = XCTAttachment(string: text)
        attachment.name = "qakit-note"
        attachment.lifetime = .keepAlways
        add(attachment)
        print("[qakit-note] \(text)")
    }

    override open func record(_ issue: XCTIssue) {
        if !attachedFailureContext, let app, app.state != .notRunning {
            attachedFailureContext = true
            let tree = XCTAttachment(string: app.debugDescription)
            tree.name = "qakit-ui-tree"
            tree.lifetime = .keepAlways
            add(tree)

            let shot = XCTAttachment(screenshot: app.screenshot())
            shot.name = "qakit-screenshot"
            shot.lifetime = .keepAlways
            add(shot)
        }
        super.record(issue)
    }
}
