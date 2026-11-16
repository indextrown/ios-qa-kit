import AppKit

/// 새 버전 확인·업데이트 (D5): GitHub 최신 릴리스의 DMG를 받아 앱을 바꾸고 다시 켠다.
/// 앱이 직접 받은 파일에는 격리 속성이 붙지 않아 "처음 열 때 허용"이 다시 필요 없다.
final class Updater: ObservableObject {
    static let shared = Updater()
    static let repo = "indextrown/qa-kit"

    struct Release { let version: String; let page: URL; let dmg: URL?; let notes: String }

    enum Phase: Equatable { case idle, checking, upToDate, available, downloading(Double), installing, failed(String) }

    @Published var phase: Phase = .idle
    @Published var latest: Release?
    @Published var lastChecked: Date? = UserDefaults.standard.object(forKey: "updateLastChecked") as? Date
    @Published var autoCheck: Bool = UserDefaults.standard.object(forKey: "updateAutoCheck") as? Bool ?? true {
        didSet { UserDefaults.standard.set(autoCheck, forKey: "updateAutoCheck") }
    }

    private var task: URLSessionDownloadTask?
    private var progressObs: NSKeyValueObservation?

    var current: String { Kit.version }
    var hasUpdate: Bool { latest.map { Self.newer($0.version, than: current) } ?? false }

    /// 개발 중(QAKIT_KIT로 저장소를 씀)이거나 저장소 안 dist/에서 켠 앱은 바꾸지 않는다
    var canInstall: Bool {
        if let k = ProcessInfo.processInfo.environment["QAKIT_KIT"], !k.isEmpty { return false }
        let app = Bundle.main.bundleURL
        if FileManager.default.fileExists(atPath: app.deletingLastPathComponent().deletingLastPathComponent().appendingPathComponent(".git").path) { return false }
        return FileManager.default.isWritableFile(atPath: app.deletingLastPathComponent().path)
    }

    static func newer(_ a: String, than b: String) -> Bool {
        let pa = a.split(separator: ".").map { Int($0) ?? 0 }, pb = b.split(separator: ".").map { Int($0) ?? 0 }
        for i in 0..<max(pa.count, pb.count) {
            let x = i < pa.count ? pa[i] : 0, y = i < pb.count ? pb[i] : 0
            if x != y { return x > y }
        }
        return false
    }

    /// 켤 때: 하루에 한 번만 (GitHub API는 로그인 없이 시간당 60번)
    func checkIfDue() {
        guard autoCheck else { return }
        if let last = lastChecked, Date().timeIntervalSince(last) < 20 * 3600 { return }
        check()
    }

    func check(done: (() -> Void)? = nil) {
        if case .downloading = phase { return }
        phase = .checking
        var req = URLRequest(url: URL(string: "https://api.github.com/repos/\(Self.repo)/releases/latest")!, timeoutInterval: 15)
        req.setValue("application/vnd.github+json", forHTTPHeaderField: "Accept")
        req.setValue("qakit-mac-app", forHTTPHeaderField: "User-Agent")
        URLSession.shared.dataTask(with: req) { data, resp, err in
            struct Asset: Decodable { let name: String; let browser_download_url: URL }
            struct R: Decodable { let tag_name: String; let html_url: URL; let body: String?; let assets: [Asset] }
            let r = data.flatMap { try? JSONDecoder().decode(R.self, from: $0) }
            DispatchQueue.main.async {
                self.lastChecked = Date()
                UserDefaults.standard.set(self.lastChecked, forKey: "updateLastChecked")
                guard let r else {
                    let code = (resp as? HTTPURLResponse)?.statusCode
                    self.phase = .failed(err?.localizedDescription ?? "릴리스 정보를 읽지 못했습니다 (HTTP \(code.map(String.init) ?? "?"))")
                    done?(); return
                }
                let v = r.tag_name.hasPrefix("v") ? String(r.tag_name.dropFirst()) : r.tag_name
                self.latest = Release(version: v, page: r.html_url,
                                      dmg: r.assets.first { $0.name.hasSuffix(".dmg") }?.browser_download_url, notes: r.body ?? "")
                self.phase = self.hasUpdate ? .available : .upToDate
                done?()
            }
        }.resume()
    }

    func openReleasePage() {
        NSWorkspace.shared.open(latest?.page ?? URL(string: "https://github.com/\(Self.repo)/releases/latest")!)
    }

    // MARK: 받기 → 붙이기 → 꺼내기 → 확인 → 바꾸고 다시 켜기

    func install() {
        guard let rel = latest, let dmg = rel.dmg else { return openReleasePage() }
        guard canInstall else { return openReleasePage() }
        phase = .downloading(0)
        let t = URLSession.shared.downloadTask(with: dmg) { file, _, err in
            guard let file else {
                return DispatchQueue.main.async { self.phase = .failed("내려받지 못했습니다: \(err?.localizedDescription ?? "?")") }
            }
            let keep = FileManager.default.temporaryDirectory.appendingPathComponent("QA-Kit-\(rel.version).dmg")
            try? FileManager.default.removeItem(at: keep)
            do { try FileManager.default.moveItem(at: file, to: keep) } catch {
                return DispatchQueue.main.async { self.phase = .failed("내려받은 파일을 옮기지 못했습니다") }
            }
            DispatchQueue.main.async { self.phase = .installing }
            DispatchQueue.global(qos: .userInitiated).async {
                let result = Self.prepare(dmg: keep, version: rel.version)
                DispatchQueue.main.async {
                    switch result {
                    case .success(let newApp): self.swapAndRelaunch(newApp)
                    case .failure(let e): self.phase = .failed(e.text)
                    }
                }
            }
        }
        progressObs = t.progress.observe(\.fractionCompleted) { p, _ in
            DispatchQueue.main.async { if case .downloading = self.phase { self.phase = .downloading(p.fractionCompleted) } }
        }
        task = t
        t.resume()
    }

    struct Failure: Error { let text: String }

    /// DMG를 붙여 앱을 임시 폴더로 꺼내고, 같은 앱(번들 ID·버전·서명)인지 확인
    static func prepare(dmg: URL, version: String) -> Result<URL, Failure> {
        defer { try? FileManager.default.removeItem(at: dmg) }   // 앱을 꺼내면 DMG는 필요 없다
        let mount = FileManager.default.temporaryDirectory.appendingPathComponent("qakit-update-mnt-\(UUID().uuidString.prefix(8))")
        let (out, code) = run("/usr/bin/hdiutil", ["attach", "-nobrowse", "-readonly", "-noautoopen", "-mountpoint", mount.path, dmg.path])
        guard code == 0 else { return .failure(Failure(text: "DMG를 열지 못했습니다\n\(out.suffix(500))")) }
        defer { _ = run("/usr/bin/hdiutil", ["detach", "-quiet", mount.path]) }
        let src = mount.appendingPathComponent("QA Kit.app")
        let stage = FileManager.default.temporaryDirectory.appendingPathComponent("qakit-update-\(version)")
        try? FileManager.default.removeItem(at: stage)
        try? FileManager.default.createDirectory(at: stage, withIntermediateDirectories: true)
        let dst = stage.appendingPathComponent("QA Kit.app")
        let (cpOut, cpCode) = run("/usr/bin/ditto", [src.path, dst.path])
        guard cpCode == 0 else { return .failure(Failure(text: "앱을 꺼내지 못했습니다\n\(cpOut.suffix(500))")) }
        guard let info = Bundle(url: dst)?.infoDictionary,
              info["CFBundleIdentifier"] as? String == Bundle.main.bundleIdentifier,
              info["CFBundleShortVersionString"] as? String == version else {
            return .failure(Failure(text: "받은 앱이 QA Kit \(version)이 아닙니다"))
        }
        let (vOut, vCode) = run("/usr/bin/codesign", ["--verify", "--strict", dst.path])
        guard vCode == 0 else { return .failure(Failure(text: "받은 앱의 서명이 맞지 않습니다\n\(vOut.suffix(500))")) }
        // 지금 앱이 Developer ID로 서명돼 있으면 새 앱도 같은 팀이어야 한다
        let team = { (p: String) in run("/usr/bin/codesign", ["-dv", p]).0.split(separator: "\n").first { $0.hasPrefix("TeamIdentifier=") }.map(String.init) }
        if let mine = team(Bundle.main.bundlePath), mine != "TeamIdentifier=not set", team(dst.path) != mine {
            return .failure(Failure(text: "받은 앱의 서명 팀이 다릅니다"))
        }
        return .success(dst)
    }

    /// 받은 새 앱. 앱이 실제로 끝날 때(applicationWillTerminate) 바꾸는 셸을 띄운다 — 끄기를 취소하면 다음에 끌 때 바뀐다.
    private(set) var pending: URL?

    private func swapAndRelaunch(_ newApp: URL) {
        pending = newApp
        phase = .installing
        NSApp.terminate(nil)
        // 끄기가 취소됐으면(도는 작업이 있어서) 여기로 돌아온다
        DispatchQueue.main.asyncAfter(deadline: .now() + 15) {
            if self.pending != nil { self.phase = .failed("끄기를 취소해서 아직 바꾸지 않았습니다. 앱을 끄면 \(self.latest?.version ?? "새 버전")으로 바뀌고 다시 켜집니다.") }
        }
    }

    /// 앱이 끝나기를 기다렸다가 바꾸고 다시 켜는 셸. 옛 앱은 옆에 두었다가 새 앱이 자리 잡으면 지운다 (실패하면 되돌림).
    func launchPendingSwap() {
        guard let newApp = pending else { return }
        let script = """
        pid=\(getpid()); n=0
        while kill -0 $pid 2>/dev/null; do sleep 0.3; n=$((n+1)); [ $n -gt 200 ] && exit 1; done
        old="$1.old-$$"
        mv "$1" "$old" || exit 1
        if /usr/bin/ditto "$2" "$1"; then rm -rf "$old" "$(dirname "$2")"; else rm -rf "$1"; mv "$old" "$1"; fi
        /usr/bin/open "$1"
        """
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/sh")
        p.arguments = ["-c", script, "qakit-update", Bundle.main.bundleURL.path, newApp.path]
        p.standardInput = FileHandle.nullDevice
        p.standardOutput = FileHandle.nullDevice
        p.standardError = FileHandle.nullDevice
        try? p.run()
    }

    @discardableResult
    static func run(_ exe: String, _ args: [String]) -> (String, Int32) {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: exe)
        p.arguments = args
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = pipe
        do { try p.run() } catch { return (error.localizedDescription, -1) }
        let d = pipe.fileHandleForReading.readDataToEndOfFile()
        p.waitUntilExit()
        return (String(decoding: d, as: UTF8.self), p.terminationStatus)
    }
}
