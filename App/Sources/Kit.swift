import Foundation

/// 앱 안의 도구 폴더(Resources/kit)와 서버를 띄울 환경.
enum Kit {
    /// QAKIT_KIT(개발용: 저장소 경로) → 앱 번들 안 Resources/kit
    static let dir: URL? = {
        var cands: [URL] = []
        if let p = ProcessInfo.processInfo.environment["QAKIT_KIT"], !p.isEmpty { cands.append(URL(fileURLWithPath: p)) }
        if let r = Bundle.main.resourceURL { cands.append(r.appendingPathComponent("kit")) }
        return cands.first { FileManager.default.isExecutableFile(atPath: $0.appendingPathComponent("bin/qakit").path) }
    }()

    static var qakit: URL? { dir?.appendingPathComponent("bin/qakit") }

    static var version: String {
        guard let d = dir, let v = try? String(contentsOf: d.appendingPathComponent("VERSION"), encoding: .utf8) else { return "?" }
        return v.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// 앱을 Finder·Dock에서 켜면 PATH가 /usr/bin:/bin 정도뿐이라 xcodegen·adb·claude를 못 찾는다
    /// → 사용자 로그인 셸의 PATH를 한 번 읽어 쓴다 (터미널에서 qakit을 쓸 때와 같게). 느린 셸이면 5초에서 포기.
    static let environment: [String: String] = {
        var env = ProcessInfo.processInfo.environment
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        var path = loginShellPath() ?? env["PATH"] ?? "/usr/bin:/bin:/usr/sbin:/sbin"
        for extra in ["/opt/homebrew/bin", "/usr/local/bin", "\(home)/.local/bin"] where !path.split(separator: ":").contains(Substring(extra)) {
            path += ":" + extra
        }
        env["PATH"] = path
        if env["LANG"] == nil { env["LANG"] = "en_US.UTF-8" }
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"   // 주소 줄을 바로 읽으려고
        env["QAKIT_UI_PARENT"] = "1"    // 앱이 죽으면 서버도 끈다
        return env
    }()

    private static func loginShellPath() -> String? {
        let shell = ProcessInfo.processInfo.environment["SHELL"] ?? "/bin/zsh"
        let marker = "__QAKIT_PATH__"
        let p = Process()
        p.executableURL = URL(fileURLWithPath: shell)
        p.arguments = ["-ilc", "printf '\\n\(marker)%s\\n' \"$PATH\""]
        let out = Pipe()
        p.standardOutput = out
        p.standardError = FileHandle.nullDevice
        p.standardInput = FileHandle.nullDevice
        do { try p.run() } catch { return nil }
        // 셸이 띄운 다른 프로그램이 출력을 붙잡고 있을 수도 있어 읽기도 시간 제한 안에서만
        let box = DataBox()
        let read = DispatchGroup()
        read.enter()
        DispatchQueue.global().async {
            box.data = out.fileHandleForReading.readDataToEndOfFile()
            read.leave()
        }
        if read.wait(timeout: .now() + 5) == .timedOut {
            if p.isRunning { p.terminate() }
            return nil
        }
        let text = String(decoding: box.data, as: UTF8.self)
        guard let line = text.split(separator: "\n").last(where: { $0.hasPrefix(marker) }) else { return nil }
        let path = String(line.dropFirst(marker.count))
        return path.isEmpty ? nil : path
    }
}

private final class DataBox: @unchecked Sendable { var data = Data() }
