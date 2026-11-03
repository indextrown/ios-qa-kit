// qakit run이 넘긴 시나리오(JSON)를 실행한다. 앱별 코드 없음.
import QAKit
import XCTest

final class ScenarioTests: QATestCase {

    func test_run() throws {
        guard let path = QAConfig.value("SCENARIO_JSON") else {
            XCTFail("QA_ARG_SCENARIO_JSON이 없습니다. qakit run <시나리오>로 실행하세요.")
            return
        }
        try QAScenarioRunner(testCase: self).run(fileAt: path)
    }

    /// qakit dump-ui (시나리오 모드 작업공간용)
    func test_dump() throws {
        app = QAConfig.value("DUMP_MODE") == "attach" ? QAApp.attach() : QAApp.launch()
        if let id = QAConfig.value("DUMP_WAIT_ID") {
            XCTAssertTrue(app.descendants(matching: .any).matching(identifier: id).firstMatch
                .waitForExistence(timeout: 30), "--wait-id \(id)가 30초 안에 나타나지 않음")
        }
        try QADump.run(app: app, settle: Double(QAConfig.value("DUMP_SETTLE") ?? "3") ?? 3)
    }
}
