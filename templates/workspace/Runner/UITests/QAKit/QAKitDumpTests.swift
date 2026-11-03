// `qakit dump-ui`가 실행하는 테스트. 수정하지 않는다.
import QAKit
import XCTest

final class QAKitDumpTests: QATestCase {

    func test_dump() throws {
        let attach = QAConfig.value("DUMP_MODE") == "attach"
        app = attach ? QAApp.attach() : QAApp.launch()

        if let id = QAConfig.value("DUMP_WAIT_ID") {
            let found = app.descendants(matching: .any).matching(identifier: id).firstMatch
                .waitForExistence(timeout: 30)
            XCTAssertTrue(found, "--wait-id \(id)가 30초 안에 나타나지 않음")
        }
        let settle = Double(QAConfig.value("DUMP_SETTLE") ?? "3") ?? 3
        try QADump.run(app: app, settle: settle)
    }
}
