//
//  Interruptions.swift
//  QAKit
//
//  시스템 권한 팝업(위치, 알림 등) 처리. qakit build-app이 권한을 미리 허용해 두지만,
//  그래도 뜨는 팝업을 닫는다.
//

import XCTest

@MainActor
public enum QAInterruptions {

    /// 허용 쪽 버튼 후보 (한국어/영어). 앞에 있을수록 우선.
    public static var allowLabels = [
        "항상 허용", "앱을 사용하는 동안 허용", "허용", "확인",
        "Always Allow", "Allow While Using App", "Allow", "OK",
    ]

    /// 테스트 시작 시 한 번 호출. 이후 팝업이 테스트를 막으면 자동으로 닫는다.
    public static func install(on testCase: XCTestCase) {
        testCase.addUIInterruptionMonitor(withDescription: "QAKit system alert") { alert in
            for label in allowLabels where alert.buttons[label].exists {
                alert.buttons[label].tap()
                return true
            }
            return false
        }
    }

    /// 지금 떠 있는 시스템 팝업을 즉시 닫는다. 닫았으면 true.
    @discardableResult
    public static func dismissSystemAlerts(timeout: TimeInterval = 1) -> Bool {
        let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        let alert = springboard.alerts.firstMatch
        guard alert.waitForExistence(timeout: timeout) else { return false }
        for label in allowLabels where alert.buttons[label].exists {
            alert.buttons[label].tap()
            return true
        }
        return false
    }
}
