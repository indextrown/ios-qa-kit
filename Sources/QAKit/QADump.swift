//
//  QADump.swift
//  QAKit
//
//  `qakit dump-ui`가 실행하는 화면 구조 덤프.
//  화면 구조를 간결한 텍스트로 QA_RESULTS_DIR/ui-dump.txt에 저장한다. (AI가 읽는 용도: 스크린샷보다 토큰이 훨씬 적다)
//

import XCTest

@MainActor
public enum QADump {

    /// 누를 수 있거나 값을 가진 요소 타입. 커버리지(ID 비율) 계산 대상.
    static let interactiveTypes: Set<XCUIElement.ElementType> = [
        .button, .textField, .secureTextField, .switch, .slider, .stepper,
        .segmentedControl, .cell, .link, .searchField, .textView, .picker, .toggle,
    ]

    /// 현재 화면을 덤프한다.
    /// - Parameters:
    ///   - app: 대상 앱
    ///   - settle: 덤프 전 기다릴 시간 (화면 전환/애니메이션 대기)
    ///   - name: 지정하면 results/ui-dump.txt 대신 results/dumps/<name>.txt에 저장 (시나리오 `dump:` 단계용)
    public static func run(app: XCUIApplication, settle: TimeInterval = 2, name: String? = nil, save: Bool = true) throws -> String {
        RunLoop.current.run(until: Date().addingTimeInterval(settle))

        let snapshot = try app.snapshot()
        var lines: [String] = []
        var total = 0
        var withID = 0
        var missing: [String] = []

        func visit(_ node: XCUIElementSnapshot, depth: Int) {
            let type = node.elementType
            let id = node.identifier
            let label = node.label
            let value = (node.value as? String) ?? ""

            // 의미 없는 빈 컨테이너는 줄이지 않고 들여쓰기만 유지 (구조 파악용)
            var parts = [typeName(type)]
            if !id.isEmpty { parts.append("#\(id)") }
            if !label.isEmpty { parts.append("\"\(label)\"") }
            if !value.isEmpty, type != .secureTextField { parts.append("value=\"\(value)\"") }
            if !node.isEnabled { parts.append("(disabled)") }
            let f = node.frame
            parts.append("@\(coord(f.minX)),\(coord(f.minY)) \(coord(f.width))x\(coord(f.height))")
            lines.append(String(repeating: "  ", count: depth) + parts.joined(separator: " "))

            if interactiveTypes.contains(type) {
                total += 1
                if !id.isEmpty { withID += 1 }
                else { missing.append("\(typeName(type)) \"\(label)\"") }
            }
            for child in node.children { visit(child, depth: depth + 1) }
        }
        visit(snapshot, depth: 0)

        let ratio = total == 0 ? 100 : Int((Double(withID) / Double(total) * 100).rounded())
        var header = [
            "# qakit dump-ui",
            "# bundle: \(QAConfig.bundleId)",
            "# interactive: \(total), with auto/app ID: \(withID) (\(ratio)%)",
        ]
        if !missing.isEmpty {
            header.append("# missing ID: " + missing.prefix(20).joined(separator: ", "))
        }
        let output = (header + [""] + lines).joined(separator: "\n") + "\n"

        if !save {
            // 저장하지 않고 돌려주기만 (상주 실행기의 실패 시점 화면 구조)
        } else if QAConfig.isDevice {
            // 실기기: Mac 폴더에 쓸 수 없다 → 첨부로 남기면 qakit이 결과 폴더로 꺼낸다
            let attachment = XCTAttachment(string: output)
            attachment.name = "qakit-file:" + (name.map { "dumps/\($0).txt" } ?? "ui-dump.txt")
            attachment.lifetime = .keepAlways
            XCTContext.runActivity(named: "qakit dump") { $0.add(attachment) }
        } else if let dir = QAConfig.resultsDir {
            var url = URL(fileURLWithPath: dir)
            if let name {
                url.appendPathComponent("dumps")
                try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
                url.appendPathComponent("\(name).txt")
            } else {
                url.appendPathComponent("ui-dump.txt")
            }
            try output.write(to: url, atomically: true, encoding: .utf8)
        }
        print("[qakit-coverage] \(withID)/\(total) (\(ratio)%)")
        return output
    }

    /// 좌표를 정수 문자열로. 화면 밖·레이아웃 전 요소는 무한대/NaN일 수 있어 그대로 Int로 바꾸면 크래시한다.
    static func coord(_ value: CGFloat) -> String {
        guard value.isFinite, abs(value) < 1_000_000 else { return "?" }
        return String(Int(value.rounded()))
    }

    static func typeName(_ type: XCUIElement.ElementType) -> String {
        switch type {
        case .any: return "Any"
        case .other: return "Other"
        case .application: return "Application"
        case .window: return "Window"
        case .button: return "Button"
        case .staticText: return "Text"
        case .textField: return "TextField"
        case .secureTextField: return "SecureTextField"
        case .image: return "Image"
        case .scrollView: return "ScrollView"
        case .table: return "Table"
        case .collectionView: return "CollectionView"
        case .cell: return "Cell"
        case .switch: return "Switch"
        case .toggle: return "Toggle"
        case .slider: return "Slider"
        case .navigationBar: return "NavigationBar"
        case .tabBar: return "TabBar"
        case .alert: return "Alert"
        case .sheet: return "Sheet"
        case .map: return "Map"
        case .webView: return "WebView"
        case .textView: return "TextView"
        case .segmentedControl: return "SegmentedControl"
        case .keyboard: return "Keyboard"
        case .key: return "Key"
        default: return "Type\(type.rawValue)"
        }
    }
}
