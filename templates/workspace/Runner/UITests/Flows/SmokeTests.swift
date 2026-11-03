// 기본 동작 확인: 앱이 실행되고 화면에 무언가 뜨는지.
import QAKit
import XCTest

final class SmokeTests: QATestCase {

    func test_appLaunches() {
        launchApp()
        XCTAssertTrue(app.wait(for: .runningForeground, timeout: 15), "앱이 15초 안에 실행되지 않음")
    }
}
