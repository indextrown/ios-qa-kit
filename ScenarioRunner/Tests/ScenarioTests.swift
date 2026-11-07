// qakit run이 넘긴 시나리오(JSON)를 실행한다. 앱별 코드 없음.
import QAKit
import XCTest

final class ScenarioTests: QATestCase {

    /// 상주 실행기(test_serve)가 도는 중이면 XCUITest 실패를 테스트에 남기지 않고 지금 명령의 오류로 모은다
    private var serving = false
    private var issues: [String] = []

    override func record(_ issue: XCTIssue) {
        if serving {
            issues.append(issue.compactDescription)
            return
        }
        super.record(issue)
    }

    func test_run() throws {
        if let b64 = QAConfig.value("SCENARIO_B64"), let data = Data(base64Encoded: b64) {
            try QAScenarioRunner(testCase: self).run(json: data)
            return
        }
        guard let path = QAConfig.value("SCENARIO_JSON") else {
            XCTFail("QA_ARG_SCENARIO_JSON이 없습니다. qakit run <시나리오>로 실행하세요.")
            return
        }
        try QAScenarioRunner(testCase: self).run(fileAt: path)
    }

    /// 상주 실행기 (docs/PLAN.md "상주 실행기 설계"). 끝나지 않는 테스트로 HTTP 서버를 열고 명령을 기다린다.
    /// 인자: SERVE_STATE(포트·토큰을 쓸 파일), SERVE_TOKEN, SERVE_LAUNCH=0(앱을 띄우지 않음), SERVE_IDLE(초, 기본 1800)
    func test_serve() throws {
        continueAfterFailure = true
        let server = QAServer(token: QAConfig.value("SERVE_TOKEN") ?? UUID().uuidString)
        try server.start()
        if let path = QAConfig.value("SERVE_STATE") {
            let state: [String: Any] = ["port": Int(server.port), "token": server.token,
                                        "pid": Int(ProcessInfo.processInfo.processIdentifier),
                                        "started": ISO8601DateFormatter().string(from: Date())]
            try JSONSerialization.data(withJSONObject: state, options: [.sortedKeys])
                .write(to: URL(fileURLWithPath: path), options: .atomic)
        }
        print("[qakit-serve] ready port=\(server.port)")
        if QAConfig.value("SERVE_LAUNCH") != "0" { launchApp() }

        var runner = makeServeRunner()
        let idle = Double(QAConfig.value("SERVE_IDLE") ?? "") ?? 1800
        var lastRequest = Date()
        var stop = false
        serving = true
        defer {
            serving = false
            server.stop()
        }
        while !stop {
            let handled = server.processNext { request in
                lastRequest = Date()
                return handle(request, runner: &runner, stop: &stop)
            }
            if !handled {
                if Date().timeIntervalSince(lastRequest) > idle {
                    print("[qakit-serve] \(Int(idle))초 동안 명령이 없어 종료")
                    break
                }
                RunLoop.current.run(until: Date().addingTimeInterval(0.05))
            }
        }
        print("[qakit-serve] stopped")
    }

    private func makeServeRunner() -> QAScenarioRunner {
        let runner = QAScenarioRunner(testCase: self)
        runner.recordsFailures = false
        return runner
    }

    private func handle(_ request: QAServer.Request, runner: inout QAScenarioRunner, stop: inout Bool) -> QAServer.Response {
        issues = []
        let started = Date()
        var json: [String: Any] = [:]
        var ok = true
        var message = ""
        switch request.path {
        case "/ping":
            json["appState"] = app.map { Int($0.state.rawValue) } ?? 0
        case "/step":
            if let app, app.state != .runningForeground {
                ok = false
                message = "대상 앱이 화면 맨 앞에 없음 (상태 \(app.state.rawValue)). 다른 앱이 시뮬레이터를 쓰는지 확인하거나 qakit do launch"
                break
            }
            do {
                try runner.runStep(json: request.body)
            } catch {
                ok = false
                message = "\(error)"
            }
        case "/dump":
            let body = (try? JSONSerialization.jsonObject(with: request.body)) as? [String: Any] ?? [:]
            let settle = (body["settle"] as? Double) ?? 0.5
            if let app {
                do { json["dump"] = try QADump.run(app: app, settle: settle) } catch { ok = false; message = "\(error)" }
            } else {
                ok = false
                message = "앱이 실행되지 않음 (/launch 먼저)"
            }
        case "/run":
            // 시나리오 전체 (qakit run). 새 실행기로 돌리고, 끝난 뒤 qakit do가 그 변수 그대로 이어 갈 수 있게 남긴다
            var notes: [String] = []
            noteSink = { notes.append($0) }
            let scenarioRunner = makeServeRunner()
            do {
                try scenarioRunner.run(json: request.body)
            } catch {
                ok = false
                message = "\(error)"
            }
            noteSink = nil
            runner = scenarioRunner
            json["notes"] = notes
            json["steps"] = Array(scenarioRunner.trail.suffix(8))
        case "/launch":
            launchApp()
            runner = makeServeRunner()
        case "/reset":
            runner = makeServeRunner()   // 변수·스냅샷만 비운다 (앱은 그대로)
        case "/stop":
            stop = true
        default:
            return QAServer.Response(status: 404, json: ["ok": false, "message": "알 수 없는 경로: \(request.path)"])
        }
        if !issues.isEmpty {
            ok = false
            message = ([message] + issues).filter { !$0.isEmpty }.joined(separator: "\n")
        }
        if !ok, request.path == "/step" || request.path == "/run", let app, app.state != .notRunning {
            json["dump"] = try? QADump.run(app: app, settle: 0, save: false)   // 실패 시점 화면 구조 (results/ui-dump.txt를 덮지 않음)
            if request.path == "/run" {
                json["screenshot"] = app.screenshot().pngRepresentation.base64EncodedString()
            }
        }
        json["ok"] = ok
        json["message"] = message
        json["durationMs"] = Int(Date().timeIntervalSince(started) * 1000)
        return QAServer.Response(json: json)
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
