import Foundation

/// 작업공간 하나의 `qakit ui --no-open --port <포트>` 서버.
final class Server {
    let workspace: String
    private var process: Process?
    private var output = ""
    private let lock = NSLock()
    private var resolved = false
    private var stopping = false

    /// 서버가 주소를 내기 전에 끝나면 실패, 연 뒤에 끝나면 onExit (둘 다 메인 스레드)
    var onExit: ((String) -> Void)?

    init(workspace: String) { self.workspace = workspace }

    var isRunning: Bool { process?.isRunning ?? false }

    /// 출력 끝부분 (실패 이유 보여 주기)
    var logTail: String {
        lock.lock(); defer { lock.unlock() }
        return String(output.suffix(3000))
    }

    func start(completion: @escaping (Result<URL, ServerError>) -> Void) {
        lock.lock(); output = ""; resolved = false; stopping = false; lock.unlock()
        DispatchQueue.global(qos: .userInitiated).async { [self] in
            guard let qakit = Kit.qakit else {
                return DispatchQueue.main.async { completion(.failure(.message("앱 안에서 qakit 도구 폴더를 찾지 못했습니다 (Resources/kit)."))) }
            }
            let port = Ports.port(for: workspace)
            let p = Process()
            p.executableURL = qakit
            p.arguments = ["-w", workspace, "ui", "--no-open", "--port", String(port)]
            p.currentDirectoryURL = URL(fileURLWithPath: workspace)
            p.environment = Kit.environment
            let pipe = Pipe()
            p.standardOutput = pipe
            p.standardError = pipe
            p.standardInput = FileHandle.nullDevice
            pipe.fileHandleForReading.readabilityHandler = { [weak self] h in
                let d = h.availableData
                guard let self, !d.isEmpty else { h.readabilityHandler = nil; return }
                self.received(String(decoding: d, as: UTF8.self), completion: completion)
            }
            p.terminationHandler = { [weak self] proc in
                guard let self else { return }
                self.lock.lock()
                let wasResolved = self.resolved, wasStopping = self.stopping
                self.resolved = true
                self.lock.unlock()
                let tail = self.logTail
                DispatchQueue.main.async {
                    if !wasResolved {
                        completion(.failure(.exited(code: proc.terminationStatus, log: tail)))
                    } else if !wasStopping {
                        self.onExit?(tail)
                    }
                }
            }
            do {
                try p.run()
                process = p
            } catch {
                DispatchQueue.main.async { completion(.failure(.message("qakit을 실행하지 못했습니다: \(error.localizedDescription)"))) }
            }
        }
    }

    private func received(_ text: String, completion: @escaping (Result<URL, ServerError>) -> Void) {
        lock.lock()
        output += text
        if output.count > 20000 { output = String(output.suffix(10000)) }
        var found: URL?
        if !resolved, let r = output.range(of: #"http://127\.0\.0\.1:\d+/\?token=[A-Za-z0-9_\-]+"#, options: .regularExpression) {
            found = URL(string: String(output[r]))
            resolved = found != nil
        }
        lock.unlock()
        if let url = found { DispatchQueue.main.async { completion(.success(url)) } }
    }

    /// Ctrl+C와 같이 SIGINT로 멈춘다 (UI에서 띄운 실행·AI·녹화도 서버가 정리). 안 멈추면 SIGTERM → SIGKILL.
    func stop(wait: Bool = false) {
        lock.lock(); stopping = true; lock.unlock()
        guard let p = process, p.isRunning else { return }
        let pid = p.processIdentifier
        p.interrupt()
        let finish = {
            for _ in 0..<80 where p.isRunning { usleep(100_000) }   // 8초: 실행 중인 시나리오·녹화 마무리
            if p.isRunning { p.terminate() }
            for _ in 0..<20 where p.isRunning { usleep(100_000) }
            if p.isRunning { kill(pid, SIGKILL) }
        }
        if wait { finish() } else { DispatchQueue.global().async(execute: finish) }
    }
}

enum ServerError: Error {
    case message(String)
    case exited(code: Int32, log: String)

    var text: String {
        switch self {
        case .message(let m): return m
        case .exited(let code, let log): return "qakit ui가 끝났습니다 (코드 \(code)).\n\n\(log)"
        }
    }
}

/// 작업공간마다 같은 포트를 쓴다 — 웹 UI 설정(테마·커서·탭)이 주소(포트)별 localStorage라서.
enum Ports {
    static func port(for workspace: String) -> Int {
        let key = "port:" + workspace
        let saved = UserDefaults.standard.integer(forKey: key)
        if saved > 0, isFree(saved) { return saved }
        var h: UInt32 = 2_166_136_261   // FNV-1a: 경로마다 고르게
        for b in workspace.utf8 { h = (h ^ UInt32(b)) &* 16_777_619 }
        let base = Int(h % 300)
        let port = (0..<300).lazy.map { 8700 + (base + $0) % 300 }.first(where: isFree) ?? 0
        if port > 0, saved == 0 { UserDefaults.standard.set(port, forKey: key) }   // 정한 포트를 잠깐 다른 데서 쓰면 이번만 다른 번호
        return port
    }

    static func isFree(_ port: Int) -> Bool {
        let fd = socket(AF_INET, SOCK_STREAM, 0)
        guard fd >= 0 else { return false }
        defer { close(fd) }
        var yes: Int32 = 1   // 서버(HTTPServer)처럼 SO_REUSEADDR — 막 끈 포트(TIME_WAIT)도 비었다고 본다
        setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &yes, socklen_t(MemoryLayout<Int32>.size))
        var addr = sockaddr_in()
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_port = in_port_t(UInt16(port).bigEndian)
        addr.sin_addr.s_addr = inet_addr("127.0.0.1")
        return withUnsafePointer(to: &addr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { bind(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size)) == 0 }
        }
    }
}
