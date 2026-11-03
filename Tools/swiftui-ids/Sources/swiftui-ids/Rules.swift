//
//  Rules.swift
//  swiftui-ids
//
//  후보에 ID를 매긴다. docs/PLAN.md "ID 규칙 (SwiftUI)" 그대로.
//

import Foundation

struct Assigner {
    let views: [String: ViewDecl]
    private var singleCache: [String: Bool] = [:]

    init(views: [String: ViewDecl]) { self.views = views }

    /// 컨트롤 하나짜리 커스텀 뷰인가 (호출부에 ID를 붙여도 안의 ID를 덮어 원하는 결과가 나오는 뷰).
    /// 컨트롤 밖에 글자·그림이 있으면 화면이지 래퍼가 아니므로 제외한다 (호출부 ID가 글자에도 붙어 버린다).
    mutating func isSingleControl(_ key: String, visiting: Set<String> = []) -> Bool {
        if let cached = singleCache[key] { return cached }
        guard let decl = views[key], !visiting.contains(key) else { return false }
        if decl.hasRepeater || decl.looseLeafCount > 0 { singleCache[key] = false; return false }
        var count = decl.controlCount
        for custom in decl.customCalls {
            guard let target = resolve(custom, from: decl) else { continue }   // 레포 밖 뷰는 셀 수 없음 → 0으로 취급
            if isSingleControl(target, visiting: visiting.union([key])) { count += 1 } else {
                count += 2   // 둘 이상이거나 알 수 없음 → 하나가 아님
            }
        }
        let result = count == 1
        singleCache[key] = result
        return result
    }

    /// 호출 이름을 View 키로. 같은 모듈 → 호출한 쪽의 중첩 타입 → 다른 모듈(유일할 때만)
    func resolve(_ name: String, from decl: ViewDecl) -> String? {
        if views[ViewDecl.key(decl.module, name)] != nil { return ViewDecl.key(decl.module, name) }
        var parts = decl.path.split(separator: ".").map(String.init)
        while !parts.isEmpty {
            let nested = ViewDecl.key(decl.module, (parts + [name]).joined(separator: "."))
            if views[nested] != nil { return nested }
            parts.removeLast()
        }
        let matches = views.values.filter { $0.path == name || $0.path.hasSuffix("." + name) }
        return matches.count == 1 ? matches[0].key : nil
    }

    mutating func assign(_ candidates: [Candidate]) -> [Assigned] {
        var out: [Assigned] = []
        // (모듈, View)별로, 소스 순서대로
        let byView = Dictionary(grouping: candidates, by: { ViewDecl.key($0.module, $0.view) })
        for (key, list) in byView.sorted(by: { $0.key < $1.key }) {
            guard let decl = views[key] else { continue }       // extension인데 View가 아님
            let view = decl.path
            let ordered = list.sorted { ($0.file, $0.order) < ($1.file, $1.order) }
            var kindCounter: [String: Int] = [:]
            var used: [String: Int] = [:]
            let viewIsSingle = isSingleControl(key)

            for c in ordered {
                if c.hasOwnID { continue }
                var kindName: String
                var name: String
                var modifierPrefix = ""
                var overridable = false

                switch c.kind {
                case .control(let control):
                    kindName = control
                    let n = kindCounter[control, default: 0]
                    kindCounter[control] = n + 1
                    if let path = c.bindingPath {
                        name = path
                    } else if let label = c.label.flatMap(sanitize) {
                        name = "\(control).\(label)"
                    } else {
                        name = "\(control).\(n)"
                    }
                    overridable = viewIsSingle
                case .custom(let typeName):
                    guard let target = resolve(typeName, from: decl), isSingleControl(target) else { continue }
                    kindName = "custom:" + typeName
                    let n = kindCounter[typeName, default: 0]
                    kindCounter[typeName] = n + 1
                    if let lit = c.argLiteral.flatMap(sanitize) {
                        name = "\(typeName).\(lit)"
                    } else {
                        name = "\(typeName).\(n)"
                    }
                case .row:
                    kindName = "row"
                    name = "row"
                    modifierPrefix = ".accessibilityElement(children: .contain)"
                }

                var id = "\(view).\(name)"
                let seen = used[id, default: 0] + 1
                used[id] = seen
                if seen > 1 { id += "_\(seen)" }

                out.append(Assigned(id: id, file: c.file, line: c.line, kind: kindName, view: view,
                                    modifier: modifierPrefix + ".accessibilityIdentifier(\"\(id)\")",
                                    offset: c.insertOffset, overridable: overridable))
            }
        }
        return out.sorted { ($0.file, $0.offset) < ($1.file, $1.offset) }
    }
}

/// 라벨 → ID 조각. 공백·구두점은 `_`, 앞뒤 `_` 제거, 20자. Swift 식별자로도 쓸 수 있는 글자만 남긴다 (한글 허용).
func sanitize(_ label: String) -> String? {
    var out = ""
    var lastUnderscore = false
    for ch in label {
        if ch.isLetter || ch.isNumber {
            out.append(ch)
            lastUnderscore = false
        } else if !lastUnderscore {
            out.append("_")
            lastUnderscore = true
        }
    }
    while out.hasPrefix("_") { out.removeFirst() }
    while out.hasSuffix("_") { out.removeLast() }
    if out.isEmpty { return nil }
    if out.count > maxLabelLength { out = String(out.prefix(maxLabelLength)) }
    while out.hasSuffix("_") { out.removeLast() }
    if let first = out.first, first.isNumber { out = "_" + out }   // 숫자로 시작하면 Swift 식별자가 안 된다
    return out
}
