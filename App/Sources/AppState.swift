import AppKit
import Combine

/// 앱 전체 설정·상태 (설정 창·메뉴 막대·작업공간 창이 같이 본다)
final class AppState: ObservableObject {
    static let shared = AppState()

    // MARK: 설정 (UserDefaults)

    static let zoomSteps: [Double] = [0.5, 0.67, 0.75, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0]

    /// 웹 화면 크기 (모든 작업공간 창). 1.0 = 100%
    @Published var zoom: Double {
        didSet { UserDefaults.standard.set(zoom, forKey: "zoom") }
    }
    @Published var showStatusItem: Bool {
        didSet { UserDefaults.standard.set(showStatusItem, forKey: "showStatusItem") }
    }
    /// 실행 중일 때 창 닫기·종료 전에 묻기
    @Published var confirmWhenBusy: Bool {
        didSet { UserDefaults.standard.set(confirmWhenBusy, forKey: "confirmWhenBusy") }
    }

    private init() {
        let d = UserDefaults.standard
        d.register(defaults: ["zoom": 1.0, "showStatusItem": true, "confirmWhenBusy": true])
        zoom = d.double(forKey: "zoom")
        showStatusItem = d.bool(forKey: "showStatusItem")
        confirmWhenBusy = d.bool(forKey: "confirmWhenBusy")
    }

    func zoomIn() { zoom = Self.zoomSteps.first { $0 > zoom + 0.001 } ?? zoom }
    func zoomOut() { zoom = Self.zoomSteps.last { $0 < zoom - 0.001 } ?? zoom }
    func zoomReset() { zoom = 1.0 }

    // MARK: 처음 점검 (qakit doctor --system --json)

    struct Check: Decodable, Identifiable {
        let key, name, need, detail, hint: String
        let ok: Bool
        var id: String { key }
    }

    @Published var checks: [Check] = []
    @Published var checking = false
    @Published var checkError: String?
    var problems: Int { checks.filter { !$0.ok && $0.need == "필수" }.count }

    func runChecks(done: (() -> Void)? = nil) {
        guard !checking, let qakit = Kit.qakit else { return }
        checking = true
        DispatchQueue.global(qos: .userInitiated).async {
            let (out, code) = Self.capture(qakit, ["doctor", "--system", "--json"])
            struct Result: Decodable { let checks: [Check] }
            let parsed = try? JSONDecoder().decode(Result.self, from: Data(out.utf8))
            DispatchQueue.main.async {
                self.checking = false
                self.checks = parsed?.checks ?? []
                self.checkError = parsed == nil ? "점검을 실행하지 못했습니다 (코드 \(code))\n\(out.suffix(1500))" : nil
                done?()
            }
        }
    }

    // MARK: 명령줄·스킬 링크 (install-skill이 만드는 심볼릭 링크)

    struct Link: Identifiable {
        enum State { case app, other(String), missing, notLink }
        let label: String
        let path: URL
        let state: State
        var id: String { path.path }
    }

    @Published var links: [Link] = []

    static var linkTargets: [(String, URL)] {
        let home = FileManager.default.homeDirectoryForCurrentUser
        return [("qakit 명령", home.appendingPathComponent(".local/bin/qakit")),
                ("Claude Code 스킬", home.appendingPathComponent(".claude/skills/qa-kit")),
                ("Codex 스킬", home.appendingPathComponent(".agents/skills/qa-kit"))]
    }

    func refreshLinks() {
        let fm = FileManager.default
        let kit = Kit.dir?.resolvingSymlinksInPath().path ?? "\u{0}"
        links = Self.linkTargets.map { label, url in
            if let dest = try? fm.destinationOfSymbolicLink(atPath: url.path) {
                let abs = URL(fileURLWithPath: dest, relativeTo: url.deletingLastPathComponent()).resolvingSymlinksInPath().path
                return Link(label: label, path: url, state: abs.hasPrefix(kit + "/") ? .app : .other(abs))
            }
            return Link(label: label, path: url, state: fm.fileExists(atPath: url.path) ? .notLink : .missing)
        }
    }

    /// 앱 안 도구로 install-skill (다른 곳을 가리키던 링크는 앱으로 바꾼다)
    func installLinks(done: @escaping (String) -> Void) {
        guard let qakit = Kit.qakit else { return done("도구 폴더를 찾지 못했습니다") }
        DispatchQueue.global(qos: .userInitiated).async {
            let (out, _) = Self.capture(qakit, ["install-skill"])
            DispatchQueue.main.async { self.refreshLinks(); done(out) }
        }
    }

    /// 이 앱을 가리키는 링크만 지운다 (git 설치 등 다른 곳 링크는 그대로)
    func removeAppLinks() {
        for l in links { if case .app = l.state { try? FileManager.default.removeItem(at: l.path) } }
        refreshLinks()
    }

    // MARK: 실행 중 (메뉴 막대)

    @Published var busy: [String: String] = [:]   // 작업공간 경로 → "시나리오 실행 중" 등

    static func capture(_ exe: URL, _ args: [String]) -> (String, Int32) {
        let p = Process()
        p.executableURL = exe
        p.arguments = args
        p.environment = Kit.environment
        p.currentDirectoryURL = FileManager.default.homeDirectoryForCurrentUser
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = pipe
        p.standardInput = FileHandle.nullDevice
        do { try p.run() } catch { return ("\(error.localizedDescription)", -1) }
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        p.waitUntilExit()
        return (String(decoding: data, as: UTF8.self), p.terminationStatus)
    }
}
