//
//  BasePage.swift
//  QAKit
//
//  화면 하나 = Page Object 하나. 셀렉터는 Page 안에만 둔다.
//
//  class LoginPage: BasePage {
//      override var anchor: XCUIElement { el("LoginView.loginButton") }
//      var emailField: XCUIElement { el("LoginView.emailTextField.textField.textField") }
//  }
//

import XCTest

@MainActor
open class BasePage {

    public let app: XCUIApplication

    public init(_ app: XCUIApplication) {
        self.app = app
    }

    /// 이 화면이 떠 있음을 나타내는 대표 요소. 하위 클래스에서 지정한다.
    open var anchor: XCUIElement {
        fatalError("\(type(of: self)).anchor를 지정하세요")
    }

    /// 화면이 떠 있는지
    public func isDisplayed(timeout: TimeInterval = 0) -> Bool {
        timeout > 0 ? anchor.waitForExistence(timeout: timeout) : anchor.exists
    }

    /// 화면이 뜰 때까지 기다리고, 안 뜨면 실패
    @discardableResult
    public func waitUntilDisplayed(timeout: TimeInterval = 15, file: StaticString = #filePath, line: UInt = #line) -> Self {
        if !anchor.waitForExistence(timeout: timeout) {
            XCTFail("\(type(of: self))가 \(Int(timeout))초 안에 뜨지 않음 (anchor: \(anchor.identifier))", file: file, line: line)
        }
        return self
    }

    /// anchor가 실제로 화면 안에 보이는지 (존재 + 프레임이 화면 안).
    /// 하단 시트·드로어처럼 닫혀도 화면 밖에 남아 있는 화면은 exists 대신 이것으로 판단한다.
    public var isVisibleOnScreen: Bool { anchor.isVisibleOnScreen(in: app) }

    /// 화면이 닫힐 때까지 (사라지거나 화면 밖으로 나갈 때까지) 기다린다.
    @discardableResult
    public func waitUntilGone(timeout: TimeInterval = 5) -> Bool {
        QAWait.forOffscreen(anchor, in: app, timeout: timeout)
    }

    /// 같은 셀이 여러 개일 때 셀 안 라벨로 하나 찾기.
    /// 예) cell(QAID.MenuCell.id, labelID: QAID.MenuCell.titleLabel, label: "검색")
    public func cell(_ cellID: String, labelID: String, label: String) -> XCUIElement {
        app.cells.matching(identifier: cellID)
            .containing(NSPredicate(format: "identifier == %@ AND label == %@", labelID, label))
            .firstMatch
    }

    /// ID로 요소 찾기 (타입 무관). 같은 ID가 여러 개면 첫 번째.
    public func el(_ id: String) -> XCUIElement {
        app.descendants(matching: .any).matching(identifier: id).firstMatch
    }

    /// 화면에 보이는 글자로 요소 찾기 (ID가 없을 때)
    public func text(_ label: String) -> XCUIElement {
        app.descendants(matching: .any).matching(NSPredicate(format: "label == %@", label)).firstMatch
    }
}
