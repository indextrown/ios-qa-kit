//
//  QASecrets.swift
//  QAKit
//
//  작업공간의 secrets.txt(KEY=VALUE) 값을 읽는다. 키 이름은 앱마다 자유롭게 정한다.
//  1순위: CLI가 넘긴 환경변수 QA_SECRET_<KEY>
//  2순위: QA_SECRETS_FILE 경로의 파일을 직접 읽기 (시뮬레이터는 호스트 파일에 접근 가능)
//
//  비밀값은 print/로그/첨부에 남기지 않는다.
//

import Foundation
import XCTest

public enum QASecrets {

    /// 필수 비밀값. 없으면 어떤 키가 빠졌는지 알려 주고 테스트를 실패시킨다.
    public static func require(_ key: String, file: StaticString = #filePath, line: UInt = #line) throws -> String {
        if let value = value(key) { return value }
        let source = QAConfig.secretsFile ?? "secrets.txt"
        let message = "비밀값 '\(key)'가 없습니다. \(source)에 '\(key)=값' 줄을 추가하세요."
        XCTFail(message, file: file, line: line)
        throw QAError.missingSecret(key)
    }

    /// 선택 비밀값
    public static func value(_ key: String) -> String? {
        if let value = ProcessInfo.processInfo.environment["QA_SECRET_\(key)"], !value.isEmpty {
            return value
        }
        return fileValues()[key]
    }

    private static func fileValues() -> [String: String] {
        guard let path = QAConfig.secretsFile,
              let text = try? String(contentsOfFile: path, encoding: .utf8) else { return [:] }
        return parse(text)
    }

    static func parse(_ text: String) -> [String: String] {
        var result: [String: String] = [:]
        for raw in text.components(separatedBy: .newlines) {
            let line = raw.trimmingCharacters(in: .whitespaces)
            guard !line.isEmpty, !line.hasPrefix("#"), let eq = line.firstIndex(of: "=") else { continue }
            let key = line[..<eq].trimmingCharacters(in: .whitespaces)
            var value = line[line.index(after: eq)...].trimmingCharacters(in: .whitespaces)
            if let hash = value.range(of: " #") { value = value[..<hash.lowerBound].trimmingCharacters(in: .whitespaces) }
            result[key] = value
        }
        return result
    }
}

public enum QAError: Error, CustomStringConvertible {
    case missingSecret(String)
    case timeout(String)
    case failed(String)

    public var description: String {
        switch self {
        case .missingSecret(let key): return "missing secret: \(key)"
        case .timeout(let what): return "timeout: \(what)"
        case .failed(let message): return message
        }
    }
}
