//
//  Scanner.swift
//  swiftui-ids
//
//  소스를 훑어 View 타입과 컨트롤 호출을 모은다. 이름 계산은 Rules.swift.
//

import Foundation
import SwiftParser
import SwiftSyntax

final class Scanner {
    private(set) var views: [String: ViewDecl] = [:]
    private(set) var candidates: [Candidate] = []
    private(set) var fileCount = 0

    func scan(file: String) throws {
        let source = try String(contentsOfFile: file, encoding: .utf8)
        // SwiftUI 뷰가 없는 파일은 파싱하지 않는다 (속도)
        guard source.contains("View") else { return }
        let tree = Parser.parse(source: source)
        fileCount += 1
        let visitor = FileVisitor(file: file, module: Scanner.moduleKey(file), tree: tree, scanner: self)
        visitor.walk(tree)
    }

    /// 모듈 키: 경로에서 마지막 "Sources" 바로 위까지 (SPM/Tuist 관례). 없으면 파일의 폴더.
    static func moduleKey(_ file: String) -> String {
        let parts = file.split(separator: "/").map(String.init)
        if let i = parts.lastIndex(of: "Sources"), i > 0 {
            return parts[..<i].joined(separator: "/")
        }
        return parts.dropLast().joined(separator: "/")
    }

    fileprivate func declare(_ module: String, _ path: String) -> ViewDecl {
        let key = ViewDecl.key(module, path)
        if let v = views[key] { return v }
        let v = ViewDecl(module: module, path: path)
        views[key] = v
        return v
    }

    fileprivate func add(_ c: Candidate) { candidates.append(c) }
}

/// 파일 하나를 훑는다. 타입 선언 스택으로 "지금 어느 View 안인지"를 추적한다.
private final class FileVisitor: SyntaxVisitor {
    private struct Scope {
        let path: String?              // View 타입 경로. View가 아닌 타입(enum 등) 안이면 nil
        let isView: Bool
    }

    let file: String
    let module: String
    let converter: SourceLocationConverter
    unowned let scanner: Scanner
    private var scopes: [Scope] = []
    private var typePath: [String] = []    // 중첩 타입 이름 (View 여부 무관)
    private var order = 0

    init(file: String, module: String, tree: SourceFileSyntax, scanner: Scanner) {
        self.file = file
        self.module = module
        self.converter = SourceLocationConverter(fileName: file, tree: tree)
        self.scanner = scanner
        super.init(viewMode: .sourceAccurate)
    }

    private var currentView: String? { scopes.last?.path }

    // MARK: 타입 선언

    override func visit(_ node: StructDeclSyntax) -> SyntaxVisitorContinueKind {
        let name = node.name.text
        typePath.append(name)
        let path = typePath.joined(separator: ".")
        let conformances = inherited(node.inheritanceClause)
        if conformances.contains("PreviewProvider") {
            scopes.append(Scope(path: nil, isView: false))
            return .skipChildren
        }
        if conformances.contains("View") {
            _ = scanner.declare(module, path)
            scopes.append(Scope(path: path, isView: true))
        } else {
            scopes.append(Scope(path: nil, isView: false))
        }
        return .visitChildren
    }
    override func visitPost(_ node: StructDeclSyntax) { scopes.removeLast(); typePath.removeLast() }

    override func visit(_ node: ClassDeclSyntax) -> SyntaxVisitorContinueKind { enterNonView(node.name.text) }
    override func visitPost(_ node: ClassDeclSyntax) { leaveNonView() }
    override func visit(_ node: EnumDeclSyntax) -> SyntaxVisitorContinueKind { enterNonView(node.name.text) }
    override func visitPost(_ node: EnumDeclSyntax) { leaveNonView() }
    override func visit(_ node: ActorDeclSyntax) -> SyntaxVisitorContinueKind { enterNonView(node.name.text) }
    override func visitPost(_ node: ActorDeclSyntax) { leaveNonView() }
    override func visit(_ node: ProtocolDeclSyntax) -> SyntaxVisitorContinueKind { .skipChildren }

    override func visit(_ node: ExtensionDeclSyntax) -> SyntaxVisitorContinueKind {
        // extension LoginView { ... } → LoginView의 일부로 본다 (View 여부는 나중에 index로 판단)
        let path = node.extendedType.trimmedDescription
        typePath.append(path)
        scopes.append(Scope(path: path, isView: true))
        return .visitChildren
    }
    override func visitPost(_ node: ExtensionDeclSyntax) { scopes.removeLast(); typePath.removeLast() }

    private func enterNonView(_ name: String) -> SyntaxVisitorContinueKind {
        typePath.append(name)
        scopes.append(Scope(path: nil, isView: false))
        return .visitChildren
    }
    private func leaveNonView() { scopes.removeLast(); typePath.removeLast() }

    // #Preview { ... } 는 건너뛴다
    override func visit(_ node: MacroExpansionDeclSyntax) -> SyntaxVisitorContinueKind {
        node.macroName.text == "Preview" ? .skipChildren : .visitChildren
    }
    override func visit(_ node: MacroExpansionExprSyntax) -> SyntaxVisitorContinueKind {
        node.macroName.text == "Preview" ? .skipChildren : .visitChildren
    }

    // MARK: 호출

    override func visit(_ node: FunctionCallExprSyntax) -> SyntaxVisitorContinueKind {
        guard let view = currentView, let callee = calleeName(node) else { return .visitChildren }
        order += 1

        if controls[callee] != nil {
            let decl = scanner.declare(module, view)
            decl.controlCount += 1
            scanner.add(candidate(.control(callee), node: node, view: view))
        } else if repeaters.contains(callee) {
            scanner.declare(module, view).hasRepeater = true
            if let row = rowExpression(node) {
                // 행 콘텐츠가 그 자체로 컨트롤이면 컨트롤 ID로 충분하다 (둘 다 붙이면 컨테이너가 돼 버린다)
                if let rowCall = row.as(FunctionCallExprSyntax.self), let n = calleeName(rowCall), controls[n] != nil {
                    // skip
                } else if hasVisibleContent(row) {
                    scanner.add(Candidate(kind: .row, module: module, view: view, file: file, line: line(of: row), order: order,
                                          insertOffset: row.endPositionBeforeTrailingTrivia.utf8Offset,
                                          bindingPath: nil, label: nil, argLiteral: nil,
                                          hasOwnID: chainHasOwnID(Syntax(row))))
                }
            }
        } else if labelCarriers.contains(callee) || callee == "Image" {
            // 컨트롤 밖의 글자·그림: 이 뷰가 "컨트롤 하나짜리"인지 판단할 때 쓴다
            if !isInsideControl(node) { scanner.declare(module, view).looseLeafCount += 1 }
        } else if callee.first?.isUppercase == true, !builtinNonControls.contains(callee) {
            // 앱 커스텀 뷰일 수 있음. 실제로 View인지는 index로 나중에 판단
            scanner.declare(module, view).customCalls.append(callee)
            scanner.add(candidate(.custom(callee), node: node, view: view))
        }
        return .visitChildren
    }

    /// 행 콘텐츠에 XCUITest가 보는 것(컨트롤·글자·그림·커스텀 뷰)이 있는가. 점(Capsule)만 있는 ForEach는 행이 아니다.
    private func hasVisibleContent(_ expr: ExprSyntax) -> Bool {
        let finder = VisibleFinder(viewMode: .sourceAccurate)
        finder.walk(expr)
        return finder.found
    }

    /// 조상 중에 컨트롤 호출이 있는가 (Button 안의 Text는 컨트롤의 일부)
    private func isInsideControl(_ node: FunctionCallExprSyntax) -> Bool {
        var current: Syntax? = node.parent
        while let c = current {
            if c.is(StructDeclSyntax.self) || c.is(ExtensionDeclSyntax.self) { return false }
            if let call = c.as(FunctionCallExprSyntax.self), let n = calleeName(call), controls[n] != nil { return true }
            current = c.parent
        }
        return false
    }

    private func candidate(_ kind: Candidate.Kind, node: FunctionCallExprSyntax, view: String) -> Candidate {
        Candidate(kind: kind, module: module, view: view, file: file, line: line(of: node), order: order,
                  insertOffset: node.endPositionBeforeTrailingTrivia.utf8Offset,
                  bindingPath: bindingPath(node, kind: kind),
                  label: literalLabel(node),
                  argLiteral: firstArgLiteral(node),
                  hasOwnID: chainHasOwnID(Syntax(node)))
    }

    private func line(of node: some SyntaxProtocol) -> Int {
        converter.location(for: node.positionAfterSkippingLeadingTrivia).line
    }

    // MARK: 호출 분석

    /// `Button(...)`, `SwiftUI.Button(...)` → "Button". 메서드 호출(`.padding()`)은 nil
    private func calleeName(_ node: FunctionCallExprSyntax) -> String? {
        if let ref = node.calledExpression.as(DeclReferenceExprSyntax.self) {
            return ref.baseName.text
        }
        if let member = node.calledExpression.as(MemberAccessExprSyntax.self),
           let base = member.base?.as(DeclReferenceExprSyntax.self), base.baseName.text == "SwiftUI" {
            return member.declName.baseName.text
        }
        return nil
    }

    /// 바인딩 인자 (`text: $email`) → "email". `$vm.email` → "vm.email"
    private func bindingPath(_ node: FunctionCallExprSyntax, kind: Candidate.Kind) -> String? {
        guard case .control(let name) = kind, let labels = controls[name], !labels.isEmpty else { return nil }
        for label in labels {
            guard let arg = node.arguments.first(where: { $0.label?.text == label }) else { continue }
            if let path = dollarPath(arg.expression) { return path }
        }
        return nil
    }

    private func dollarPath(_ expr: ExprSyntax) -> String? {
        let text = expr.trimmedDescription
        guard text.hasPrefix("$") else { return nil }
        let path = String(text.dropFirst())
        // 식별자 경로만 (호출·첨자가 섞이면 포기)
        guard path.allSatisfy({ $0.isLetter || $0.isNumber || $0 == "_" || $0 == "." }) else { return nil }
        return path
    }

    /// 라벨 글자: 첫 무라벨 인자의 문자열 리터럴 → 없으면 라벨 클로저 안 첫 Text/Label/Image(systemName:) 리터럴
    private func literalLabel(_ node: FunctionCallExprSyntax) -> String? {
        if let first = node.arguments.first, first.label == nil, let s = stringLiteral(first.expression) {
            return s
        }
        // Label("x", systemImage:) 같은 경우도 위에서 잡힌다. 이제 클로저.
        var closures: [ClosureExprSyntax] = []
        if let labelClosure = node.additionalTrailingClosures.first(where: { $0.label.text == "label" }) {
            closures.append(labelClosure.closure)
        } else if let labelArg = node.arguments.first(where: { $0.label?.text == "label" }),
                  let c = labelArg.expression.as(ClosureExprSyntax.self) {
            closures.append(c)
        } else if let trailing = node.trailingClosure {
            // Button(action:) { label } / NavigationLink(destination:) { label } / Menu("…") 는 위에서 리터럴로 잡힘
            // Button { action } label: { } 은 위 분기. 트레일링 하나뿐이고 action: 인자가 있거나 Button이 아니면 라벨 클로저.
            let hasActionArg = node.arguments.contains { $0.label?.text == "action" || $0.label?.text == "destination" || $0.label?.text == "value" }
            if hasActionArg || calleeName(node) != "Button" || node.arguments.isEmpty == false {
                closures.append(trailing)
            }
        }
        for closure in closures {
            let finder = LabelFinder(viewMode: .sourceAccurate)
            finder.walk(closure)
            if let found = finder.found { return found }
        }
        return nil
    }

    /// 커스텀 뷰 첫 인자 리터럴: `.kakao` → "kakao", `"로그인"` → "로그인"
    private func firstArgLiteral(_ node: FunctionCallExprSyntax) -> String? {
        guard let first = node.arguments.first else { return nil }
        if let s = stringLiteral(first.expression) { return s }
        if let member = first.expression.as(MemberAccessExprSyntax.self), member.base == nil {
            return member.declName.baseName.text
        }
        return nil
    }

    /// ForEach/List 트레일링 클로저의 단일 식 (행 콘텐츠)
    private func rowExpression(_ node: FunctionCallExprSyntax) -> ExprSyntax? {
        // List { ForEach … } 처럼 데이터 인자가 없는 List는 행 클로저가 아니다
        if calleeName(node) == "List", node.arguments.isEmpty { return nil }
        guard let closure = node.trailingClosure ?? node.arguments.compactMap({ $0.expression.as(ClosureExprSyntax.self) }).last else { return nil }
        guard closure.statements.count == 1, let item = closure.statements.first?.item.as(ExprSyntax.self) else { return nil }
        // if/switch 식 뒤에는 수식어를 붙일 수 없다. 호출식(수식어 체인 포함)만 행으로 본다.
        guard item.is(FunctionCallExprSyntax.self) else { return nil }
        return item
    }

    /// 호출을 감싼 수식어 체인에 accessibilityIdentifier / accessibilityHidden이 있는가
    private func chainHasOwnID(_ start: Syntax) -> Bool {
        var current = start
        while let parent = current.parent {
            if let member = parent.as(MemberAccessExprSyntax.self), member.base.map({ Syntax($0) == current }) == true {
                let name = member.declName.baseName.text
                if name == "accessibilityIdentifier" || name == "accessibilityHidden" { return true }
                current = Syntax(member)
            } else if let call = parent.as(FunctionCallExprSyntax.self), Syntax(call.calledExpression) == current {
                current = Syntax(call)
            } else {
                return false
            }
        }
        return false
    }

    private func inherited(_ clause: InheritanceClauseSyntax?) -> Set<String> {
        guard let clause else { return [] }
        return Set(clause.inheritedTypes.map { $0.type.trimmedDescription })
    }
}

/// 문자열 리터럴(보간 없음) → 글자. `String(localized: "x", …)`, `LocalizedStringKey("x")`, `Text("x", …)`도 안쪽 리터럴
func stringLiteral(_ expr: ExprSyntax) -> String? {
    if let lit = expr.as(StringLiteralExprSyntax.self) {
        var out = ""
        for seg in lit.segments {
            guard let s = seg.as(StringSegmentSyntax.self) else { return nil }   // 보간이 있으면 정적 라벨이 아님
            out += s.content.text
        }
        return out.isEmpty ? nil : out
    }
    if let call = expr.as(FunctionCallExprSyntax.self), let ref = call.calledExpression.as(DeclReferenceExprSyntax.self) {
        switch ref.baseName.text {
        case "String":
            if let arg = call.arguments.first(where: { $0.label?.text == "localized" }) { return stringLiteral(arg.expression) }
        case "LocalizedStringKey", "Text", "Label", "NSLocalizedString":
            if let first = call.arguments.first, first.label == nil { return stringLiteral(first.expression) }
        default: break
        }
    }
    return nil
}

/// 행 콘텐츠 안에 XCUITest가 보는 호출이 있는지
private final class VisibleFinder: SyntaxVisitor {
    var found = false
    override func visit(_ node: FunctionCallExprSyntax) -> SyntaxVisitorContinueKind {
        if found { return .skipChildren }
        guard let ref = node.calledExpression.as(DeclReferenceExprSyntax.self) else { return .visitChildren }
        let name = ref.baseName.text
        if controls[name] != nil || labelCarriers.contains(name) || name == "Image"
            || (name.first?.isUppercase == true && !builtinNonControls.contains(name)) {
            found = true
            return .skipChildren
        }
        return .visitChildren
    }
}

/// 라벨 클로저 안에서 첫 Text/Label 리터럴 또는 Image(systemName:)을 찾는다
private final class LabelFinder: SyntaxVisitor {
    var found: String?
    override func visit(_ node: FunctionCallExprSyntax) -> SyntaxVisitorContinueKind {
        if found != nil { return .skipChildren }
        guard let ref = node.calledExpression.as(DeclReferenceExprSyntax.self) else { return .visitChildren }
        let name = ref.baseName.text
        if labelCarriers.contains(name), let first = node.arguments.first, first.label == nil, let s = stringLiteral(first.expression) {
            found = s
            return .skipChildren
        }
        if name == "Image", let arg = node.arguments.first(where: { $0.label?.text == "systemName" }), let s = stringLiteral(arg.expression) {
            found = s
            return .skipChildren
        }
        return .visitChildren
    }
}

/// 대문자로 시작하지만 커스텀 뷰가 아닌 흔한 호출 (index에 없는 타입은 어차피 무시되지만, 호출 수집을 줄인다)
let builtinNonControls: Set<String> = [
    "Text", "Image", "Label", "VStack", "HStack", "ZStack", "LazyVStack", "LazyHStack", "ScrollView", "Group",
    "GeometryReader", "Spacer", "Divider", "Color", "Rectangle", "RoundedRectangle", "Circle", "Capsule",
    "Binding", "String", "Int", "Double", "CGFloat", "Date", "URL", "Font", "UIFont", "Array", "Set", "Dictionary",
    "NavigationStack", "NavigationView", "TabView", "Section", "Form", "AnyView", "EmptyView", "ProgressView",
    "AsyncImage", "LazyVGrid", "LazyHGrid", "GridItem", "Grid", "GridRow", "Path", "Ellipse", "LinearGradient",
    "Animation", "Task", "UUID", "Data", "NSAttributedString", "AttributedString", "Calendar", "DateFormatter",
    "StoreOf", "Store", "Effect", "CGSize", "CGPoint", "CGRect", "EdgeInsets", "UIImage", "IndexSet",
]
