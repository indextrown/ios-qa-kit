//
//  QAServer.swift
//  QAKit
//
//  상주 실행기의 HTTP 서버 (docs/PLAN.md "상주 실행기 설계").
//  실행기 안 끝나지 않는 테스트(test_serve)가 띄운다. 127.0.0.1에만 열고 토큰을 확인한다.
//
//  스레드: 연결 처리는 서버 큐에서, XCUITest 동작은 반드시 메인 스레드에서.
//  서버는 요청을 큐에 넣기만 하고, 테스트의 메인 루프(serveLoop)가 꺼내 실행한 뒤 응답을 보낸다.
//

import Foundation
import Network

public final class QAServer {

    public struct Request {
        public let method: String
        public let path: String
        public let body: Data
    }

    public struct Response {
        public var status: Int
        public var json: [String: Any]
        public init(status: Int = 200, json: [String: Any]) {
            self.status = status
            self.json = json
        }
    }

    private struct Pending {
        let request: Request
        let reply: (Response) -> Void
    }

    public let token: String
    public private(set) var port: UInt16 = 0

    private let queue = DispatchQueue(label: "qakit.serve")
    private var listener: NWListener?
    private let lock = NSLock()
    private var pending: [Pending] = []

    public init(token: String = UUID().uuidString) {
        self.token = token
    }

    /// 리스너를 열고 포트가 정해질 때까지 기다린다. port 0이면 빈 포트 (시뮬레이터: 상태 파일로 알림).
    /// 실기기는 Mac이 상태 파일을 못 읽으므로 Mac이 정한 포트로 연다 (Mac은 usbmuxd로 그 포트에 붙는다).
    /// host: 기본 127.0.0.1. Wi-Fi 실기기는 CoreDevice 터널의 기기 쪽 주소에만 연다 (같은 Wi-Fi의 다른 기기에서는 안 보임).
    public func start(host: String = "127.0.0.1", port requested: UInt16 = 0, timeout: TimeInterval = 10) throws {
        let params = NWParameters.tcp
        let endpointPort = requested == 0 ? NWEndpoint.Port.any : (NWEndpoint.Port(rawValue: requested) ?? .any)
        params.requiredLocalEndpoint = .hostPort(host: NWEndpoint.Host(host), port: endpointPort)
        params.allowLocalEndpointReuse = true
        let listener = try NWListener(using: params)
        let ready = DispatchSemaphore(value: 0)
        var startError: Error?
        listener.stateUpdateHandler = { state in
            switch state {
            case .ready: ready.signal()
            case .failed(let error): startError = error; ready.signal()
            default: break
            }
        }
        listener.newConnectionHandler = { [weak self] connection in
            self?.accept(connection)
        }
        listener.start(queue: queue)
        self.listener = listener
        if ready.wait(timeout: .now() + timeout) == .timedOut {
            throw QAError.failed("상주 실행기 서버가 \(Int(timeout))초 안에 열리지 않음")
        }
        if let startError { throw startError }
        port = listener.port?.rawValue ?? 0
    }

    /// 이 기기의 IP 주소 목록 (터널 주소에 열지 못했을 때 원인 확인용)
    public static func localAddresses() -> [String] {
        var result: [String] = []
        var head: UnsafeMutablePointer<ifaddrs>?
        guard getifaddrs(&head) == 0 else { return result }
        defer { freeifaddrs(head) }
        var cursor = head
        while let ifa = cursor?.pointee {
            if let addr = ifa.ifa_addr, addr.pointee.sa_family == UInt8(AF_INET6) || addr.pointee.sa_family == UInt8(AF_INET) {
                var buf = [CChar](repeating: 0, count: Int(NI_MAXHOST))
                if getnameinfo(addr, socklen_t(addr.pointee.sa_len), &buf, socklen_t(buf.count), nil, 0, NI_NUMERICHOST) == 0 {
                    result.append("\(String(cString: ifa.ifa_name))=\(String(cString: buf))")
                }
            }
            cursor = ifa.ifa_next
        }
        return result
    }

    public func stop() {
        listener?.cancel()
        listener = nil
    }

    /// 메인 루프에서 부른다. 처리할 요청이 있으면 하나 꺼내 handler로 실행하고 응답을 보낸다.
    /// 요청이 없으면 false.
    public func processNext(_ handler: (Request) -> Response) -> Bool {
        lock.lock()
        let next = pending.isEmpty ? nil : pending.removeFirst()
        lock.unlock()
        guard let next else { return false }
        next.reply(handler(next.request))
        return true
    }

    // MARK: - 연결

    private func accept(_ connection: NWConnection) {
        connection.start(queue: queue)
        receive(on: connection, buffer: Data())
    }

    private func receive(on connection: NWConnection, buffer: Data) {
        connection.receive(minimumIncompleteLength: 1, maximumLength: 1 << 20) { [weak self] data, _, isComplete, error in
            guard let self else { return }
            var buffer = buffer
            if let data { buffer.append(data) }
            if let request = Self.parse(buffer) {
                self.dispatch(request, on: connection)
            } else if isComplete || error != nil {
                connection.cancel()
            } else {
                self.receive(on: connection, buffer: buffer)
            }
        }
    }

    private func dispatch(_ parsed: (Request, [String: String]), on connection: NWConnection) {
        let (request, headers) = parsed
        let reply: (Response) -> Void = { response in
            Self.send(response, on: connection)
        }
        guard headers["x-qakit-token"] == token else {
            reply(Response(status: 401, json: ["ok": false, "message": "토큰이 맞지 않음"]))
            return
        }
        lock.lock()
        pending.append(Pending(request: request, reply: reply))
        lock.unlock()
    }

    // MARK: - HTTP (최소한: 요청 한 개, Content-Length 본문, 응답 뒤 연결 닫음)

    private static func parse(_ data: Data) -> (Request, [String: String])? {
        let separator = Data("\r\n\r\n".utf8)
        guard let range = data.range(of: separator),
              let head = String(data: data[..<range.lowerBound], encoding: .utf8) else { return nil }
        var lines = head.components(separatedBy: "\r\n")
        let start = lines.removeFirst().split(separator: " ")
        guard start.count >= 2 else { return nil }
        var headers: [String: String] = [:]
        for line in lines {
            guard let colon = line.firstIndex(of: ":") else { continue }
            let key = line[..<colon].trimmingCharacters(in: .whitespaces).lowercased()
            headers[key] = line[line.index(after: colon)...].trimmingCharacters(in: .whitespaces)
        }
        let length = Int(headers["content-length"] ?? "0") ?? 0
        let bodyStart = range.upperBound
        guard data.count - bodyStart >= length else { return nil }   // 본문이 아직 다 안 옴
        let body = data[bodyStart..<(bodyStart + length)]
        return (Request(method: String(start[0]), path: String(start[1]), body: Data(body)), headers)
    }

    private static func send(_ response: Response, on connection: NWConnection) {
        let body = (try? JSONSerialization.data(withJSONObject: response.json, options: [.sortedKeys]))
            ?? Data(#"{"ok":false,"message":"응답 직렬화 실패"}"#.utf8)
        let reason = response.status == 200 ? "OK" : "Error"
        var head = "HTTP/1.1 \(response.status) \(reason)\r\n"
        head += "Content-Type: application/json; charset=utf-8\r\n"
        head += "Content-Length: \(body.count)\r\nConnection: close\r\n\r\n"
        connection.send(content: Data(head.utf8) + body, completion: .contentProcessed { _ in
            connection.cancel()
        })
    }
}
