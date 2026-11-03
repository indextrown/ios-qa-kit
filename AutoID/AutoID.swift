//
//  AutoID.swift
//  QAAutoID
//
//  앱 코드를 수정하지 않고 UIView에 accessibilityIdentifier를 자동으로 붙인다.
//  시뮬레이터에서 DYLD_INSERT_LIBRARIES로 주입하거나, 앱에 이 파일을 넣고 start()를 호출해 쓴다.
//
//  ID 규칙 (소유 경로 기반)
//  - VC의 뷰 프로퍼티            : <VC타입>.<프로퍼티>             예) LoginViewController.rootView
//  - VC가 소유한 커스텀 뷰의 자식 : <뷰타입>.<프로퍼티>             예) LoginView.loginButton
//  - 커스텀 뷰 안의 커스텀 뷰 자식 : <상위 ID>.<프로퍼티>           예) LoginView.emailTextField.textField
//  - 소유자를 모르는 커스텀 뷰    : <뷰타입>.<프로퍼티>             예) ShipCell.nameLabel
//  - 셀 자체                      : <셀타입>                        예) ShipCell (여러 개면 index/라벨로 구분)
//  - 탭바 버튼                    : Tab.<탭 첫 화면 VC타입>          예) Tab.SettingsViewController
//  - UIKit 기본 셀                : <목록 ID>.cell / .header / .footer 예) SettingsView.tableView.cell
//  - Collection/TableViewController의 목록 : <VC>.collectionView / <VC>.tableView
//  - 바 버튼 (프로퍼티)           : <VC>.<프로퍼티>                  예) SettingsViewController.saveButton
//  - 바 버튼 (프로퍼티 아님)      : <VC>.nav.left|right.<i>, <VC>.toolbar.<i>
//  - 검색창 입력칸                : <검색창 ID>.textField
//  - 앱이 직접 붙인 ID는 절대 덮어쓰지 않는다.
//

import ObjectiveC
import UIKit

@objc(QAAutoID)
public final class QAAutoID: NSObject {

    private static var started = false
    private static let logEnabled = ProcessInfo.processInfo.environment["QAKIT_AUTOID_LOG"] == "1"

    // 이름의 확실성. strong: 소유자(VC나 상위 뷰)에서 찾은 경로, weak: 소유자를 몰라 타입 이름으로 붙임.
    // weak 이름은 나중에 소유자가 확인되면 strong 이름으로 바뀐다. 반대는 없다.
    private static var autoIDKey: UInt8 = 0      // AutoID가 붙인 ID
    private static var strongKey: UInt8 = 0      // 그 ID가 strong인지
    private static var walkedKey: UInt8 = 0      // 훑은 prefix
    private static var walkedStrongKey: UInt8 = 0
    private static var vcRootKey: UInt8 = 0      // VC가 직접 가진 뷰

    @objc public static func start() {
        guard !started else { return }
        started = true
        swizzle(UIViewController.self,
                #selector(UIViewController.viewDidAppear(_:)),
                #selector(UIViewController.qa_viewDidAppear(_:)))
        swizzle(UIViewController.self,
                #selector(UIViewController.viewDidLayoutSubviews),
                #selector(UIViewController.qa_viewDidLayoutSubviews))
        swizzle(UIView.self,
                #selector(UIView.didMoveToWindow),
                #selector(UIView.qa_didMoveToWindow))
        log("started")
    }

    // MARK: - Entry points

    /// 탭바 버튼: 각 탭의 첫 화면 VC 타입으로 ID를 붙인다 → Tab.<VC타입>
    /// (탭바 버튼은 UIKit이 만들어 프로퍼티 이름이 없다. 아직 열지 않은 탭도 타입은 알 수 있다)
    static func handleTabBar(_ tabBarController: UITabBarController) {
        for child in tabBarController.viewControllers ?? [] {
            let root = (child as? UINavigationController)?.viewControllers.first ?? child
            guard isAppClass(type(of: root)) else { continue }
            let item = child.tabBarItem
            if let current = item?.accessibilityIdentifier, !current.isEmpty { continue }
            let id = "Tab.\(typeName(type(of: root)))"
            item?.accessibilityIdentifier = id
            log("\(id)  <UITabBarItem>")
        }
    }

    static func handle(viewController vc: UIViewController) {
        if let tab = vc as? UITabBarController { handleTabBar(tab) }
        if let tab = vc.tabBarController { handleTabBar(tab) }
        let vcType: AnyClass = type(of: vc)
        guard isAppClass(vcType) else { return }
        let vcName = typeName(vcType)

        // VC가 직접 가진 뷰는 "루트"로 표시한다. 다른 뷰를 훑다가 같은 객체를 만나도 건너뛴다.
        // → 같은 뷰를 VC와 하위 뷰가 함께 들고 있어도 이름이 선언 순서와 무관하게 VC 기준으로 정해진다.
        forEachViewProperty(of: vc) { _, view in
            objc_setAssociatedObject(view, &vcRootKey, true, .OBJC_ASSOCIATION_RETAIN_NONATOMIC)
        }
        handleBarItems(of: vc, vcName: vcName)
        // UICollectionViewController / UITableViewController의 목록은 UIKit 부모 클래스 프로퍼티라 Mirror에 안 보인다
        if let cvc = vc as? UICollectionViewController, cvc.isViewLoaded {
            assign(cvc.collectionView, id: "\(vcName).collectionView", strong: true)
        }
        if let tvc = vc as? UITableViewController, tvc.isViewLoaded {
            assign(tvc.tableView, id: "\(vcName).tableView", strong: true)
        }
        forEachViewProperty(of: vc) { name, view in
            assign(view, id: "\(vcName).\(name)", strong: true)
            if isAppClass(type(of: view)) {
                walk(view, prefix: typeName(type(of: view)), strong: true)
            }
        }
    }

    private static var lastLayoutWalkKey: UInt8 = 0
    private static var pendingKey: UInt8 = 0

    /// 화면이 뜬 뒤 나중에 만들어진 뷰(옵셔널 프로퍼티에 나중에 대입 등)를 잡기 위해 레이아웃 때 다시 훑는다.
    /// 레이아웃은 자주 일어나므로 VC마다 0.3초에 한 번으로 제한한다.
    static func handleLayout(viewController vc: UIViewController) {
        guard isAppClass(type(of: vc)), vc.viewIfLoaded?.window != nil else { return }
        if objc_getAssociatedObject(vc, &pendingKey) != nil { return }
        let last = (objc_getAssociatedObject(vc, &lastLayoutWalkKey) as? Date) ?? .distantPast
        let delay = max(0, 0.3 - Date().timeIntervalSince(last))
        objc_setAssociatedObject(vc, &pendingKey, true, .OBJC_ASSOCIATION_RETAIN_NONATOMIC)
        DispatchQueue.main.asyncAfter(deadline: .now() + delay) { [weak vc] in
            guard let vc else { return }
            objc_setAssociatedObject(vc, &pendingKey, nil, .OBJC_ASSOCIATION_RETAIN_NONATOMIC)
            objc_setAssociatedObject(vc, &lastLayoutWalkKey, Date(), .OBJC_ASSOCIATION_RETAIN_NONATOMIC)
            handle(viewController: vc)
        }
    }

    static func handle(view: UIView) {
        // UIKit 기본 셀(리스트 셀 등)은 앱 클래스가 아니다 → 담고 있는 목록의 ID로 이름을 붙인다
        if !isAppClass(type(of: view)), view is UITableViewCell || view is UICollectionViewCell {
            assignSystemCell(view)
            return
        }
        guard isAppClass(type(of: view)) else { return }
        // 소유자가 있는 뷰는 상위에서 경로 기반으로 훑는다. 여기서는 일단 타입 이름(weak)으로 훑어 두고,
        // 소유자가 나중에 확인되면 strong 이름으로 덮어쓴다. (셀처럼 소유자가 없는 뷰는 weak로 남는다)
        walk(view, prefix: typeName(type(of: view)), strong: false)

        // 셀은 프로퍼티가 아니라 이름을 얻을 수 없다. 셀 타입 이름을 ID로 붙인다 (같은 타입 셀은 index나 라벨로 구분).
        if view is UITableViewCell || view is UICollectionViewCell {
            assign(view, id: typeName(type(of: view)), strong: false)
        }
    }

    /// 시스템 셀: <목록 ID>.cell (같은 목록 안 셀은 index·라벨로 구분)
    private static func assignSystemCell(_ cell: UIView) {
        var node = cell.superview
        while let current = node, !(current is UITableView || current is UICollectionView) {
            node = current.superview
        }
        guard let list = node, let listID = list.accessibilityIdentifier, !listID.isEmpty else { return }
        assign(cell, id: "\(listID).\(systemCellRole(cell, in: list))", strong: false)
    }

    /// 셀로 쓰였는지, 섹션 헤더/푸터(supplementary)로 쓰였는지
    private static func systemCellRole(_ view: UIView, in list: UIView) -> String {
        if let collection = list as? UICollectionView {
            for kind in [UICollectionView.elementKindSectionHeader, UICollectionView.elementKindSectionFooter] {
                if collection.visibleSupplementaryViews(ofKind: kind).contains(where: { $0 === view }) {
                    return kind == UICollectionView.elementKindSectionHeader ? "header" : "footer"
                }
            }
        }
        if let table = list as? UITableView, let cell = view as? UITableViewCell, table.indexPath(for: cell) == nil {
            return "header"
        }
        return "cell"
    }

    /// 목록이 ID를 받은 뒤, 이미 화면에 있는 시스템 셀·헤더에도 이름을 붙인다
    private static func assignVisibleSystemCells(of list: UIView) {
        var cells: [UIView]
        if let table = list as? UITableView { cells = table.visibleCells }
        else if let collection = list as? UICollectionView {
            cells = collection.visibleCells
            for kind in [UICollectionView.elementKindSectionHeader, UICollectionView.elementKindSectionFooter] {
                cells += collection.visibleSupplementaryViews(ofKind: kind)
            }
        }
        else { return }
        for cell in cells where !isAppClass(type(of: cell)) && (cell is UITableViewCell || cell is UICollectionViewCell) {
            assignSystemCell(cell)
        }
    }

    /// 내비게이션 바·툴바 버튼 (UIBarButtonItem은 UIView가 아니라 따로 처리)
    /// - VC 프로퍼티면 <VC>.<프로퍼티>, 아니면 위치 <VC>.nav.left.0 / nav.right.0 / toolbar.0
    private static func handleBarItems(of vc: UIViewController, vcName: String) {
        var named = Set<ObjectIdentifier>()
        var mirror: Mirror? = Mirror(reflecting: vc)
        while let current = mirror {
            if let subject = current.subjectType as? AnyClass, !isAppClass(subject) { break }
            for child in current.children {
                guard let label = child.label, let item = unwrap(child.value) as? UIBarItem else { continue }
                named.insert(ObjectIdentifier(item))
                setBarItem(item, id: "\(vcName).\(cleanName(label))")
            }
            mirror = current.superclassMirror
        }
        let groups: [(String, [UIBarButtonItem]?)] = [
            ("nav.left", vc.navigationItem.leftBarButtonItems),
            ("nav.right", vc.navigationItem.rightBarButtonItems),
            ("toolbar", vc.toolbarItems),
        ]
        for (place, items) in groups {
            for (index, item) in (items ?? []).enumerated() where !named.contains(ObjectIdentifier(item)) {
                setBarItem(item, id: "\(vcName).\(place).\(index)")
            }
        }
    }

    private static func setBarItem(_ item: UIBarItem, id: String) {
        if let current = item.accessibilityIdentifier, !current.isEmpty { return }
        item.accessibilityIdentifier = id
        log("\(id)  <\(typeName(type(of: item)))>")
    }

    // MARK: - Walking

    private static var visiting = Set<ObjectIdentifier>()
    private static var depth = 0

    private static func walk(_ view: UIView, prefix: String, strong: Bool) {
        if let previous = objc_getAssociatedObject(view, &walkedKey) as? String {
            let previousStrong = (objc_getAssociatedObject(view, &walkedStrongKey) as? Bool) ?? false
            if previousStrong && !strong { return }               // strong을 weak로 바꾸지 않음
            // 이미 같은 이름으로 훑었어도 다시 훑는다(나중에 추가된 프로퍼티 반영). assign이 중복 대입을 막는다.
            // 단 무한 재귀를 막기 위해 같은 walk 패스 안에서는 한 번만.
            if previous == prefix && previousStrong == strong && visiting.contains(ObjectIdentifier(view)) { return }
        }
        visiting.insert(ObjectIdentifier(view))
        defer { if depth == 0 { visiting.removeAll() } }
        depth += 1
        defer { depth -= 1 }
        objc_setAssociatedObject(view, &walkedKey, prefix, .OBJC_ASSOCIATION_RETAIN_NONATOMIC)
        objc_setAssociatedObject(view, &walkedStrongKey, strong, .OBJC_ASSOCIATION_RETAIN_NONATOMIC)

        forEachViewProperty(of: view) { name, child in
            guard child !== view else { return }
            if strong, objc_getAssociatedObject(child, &vcRootKey) != nil { return } // VC 루트는 VC가 이름 지음
            let id = "\(prefix).\(name)"
            assign(child, id: id, strong: strong)
            if isAppClass(type(of: child)) {
                walk(child, prefix: id, strong: strong)
            }
        }
    }

    private static func assign(_ view: UIView, id: String, strong: Bool) {
        let ours = objc_getAssociatedObject(view, &autoIDKey) as? String
        if let current = view.accessibilityIdentifier, !current.isEmpty, current != ours,
           !isImageAssetName(current, of: view) {
            return // 앱이 직접 붙인 ID
        }
        var shouldSet = true
        if ours != nil {
            let oursStrong = (objc_getAssociatedObject(view, &strongKey) as? Bool) ?? false
            if oursStrong && !strong { shouldSet = false }
            if ours == id && oursStrong == strong { shouldSet = false }
        }
        if shouldSet {
            view.accessibilityIdentifier = id
            objc_setAssociatedObject(view, &autoIDKey, id, .OBJC_ASSOCIATION_RETAIN_NONATOMIC)
            objc_setAssociatedObject(view, &strongKey, strong, .OBJC_ASSOCIATION_RETAIN_NONATOMIC)
            log("\(id)  <\(typeName(type(of: view)))>\(strong ? "" : " (weak)")")
        }
        guard let finalID = view.accessibilityIdentifier, finalID == (objc_getAssociatedObject(view, &autoIDKey) as? String) else { return }

        // UIKit 복합 컨트롤의 안쪽 요소 (ID가 그대로여도 매번: 셀은 스크롤로 새로 생긴다)
        if let searchBar = view as? UISearchBar {
            assign(searchBar.searchTextField, id: "\(finalID).textField", strong: strong)
        }
        if view is UITableView || view is UICollectionView {
            assignVisibleSystemCells(of: view)
        }
    }

    /// UIImageView는 ID가 없으면 이미지 에셋 이름을 ID처럼 돌려준다. 이건 앱이 붙인 ID가 아니다.
    private static func isImageAssetName(_ id: String, of view: UIView) -> Bool {
        guard let imageView = view as? UIImageView else { return false }
        return imageView.image?.accessibilityIdentifier == id
    }

    // MARK: - Reflection

    /// 객체와 앱 소속 부모 클래스의 저장 프로퍼티 중 UIView(또는 UIView 배열)를 넘겨준다.
    private static func forEachViewProperty(of object: AnyObject, _ body: (String, UIView) -> Void) {
        var mirror: Mirror? = Mirror(reflecting: object)
        while let current = mirror {
            if let subject = current.subjectType as? AnyClass, !isAppClass(subject) { break }
            for child in current.children {
                guard let rawLabel = child.label else { continue }
                let name = cleanName(rawLabel)
                guard let value = unwrap(child.value) else { continue }

                if let view = value as? UIView {
                    body(name, view)
                } else if let views = value as? [UIView] {
                    for (index, view) in views.enumerated() { body("\(name).\(index)", view) }
                }
            }
            mirror = current.superclassMirror
        }
    }

    private static func unwrap(_ value: Any) -> Any? {
        let mirror = Mirror(reflecting: value)
        guard mirror.displayStyle == .optional else { return value }
        return mirror.children.first.map { unwrap($0.value) } ?? nil
    }

    private static func cleanName(_ label: String) -> String {
        // lazy var 내부 이름: $__lazy_storage_$_foo
        if label.hasPrefix("$__lazy_storage_$_") {
            return String(label.dropFirst("$__lazy_storage_$_".count))
        }
        // property wrapper 내부 이름: _foo
        if label.hasPrefix("_") { return String(label.dropFirst()) }
        return label
    }

    private static func isAppClass(_ cls: AnyClass) -> Bool {
        Bundle(for: cls) == Bundle.main
    }

    private static func typeName(_ cls: AnyClass) -> String {
        // 모듈 이름과 제네릭 인자 제거: app.LoginView -> LoginView
        let full = String(describing: cls)
        return full.split(separator: "<").first.map(String.init) ?? full
    }

    // MARK: - Utils

    private static func swizzle(_ cls: AnyClass, _ original: Selector, _ replacement: Selector) {
        guard let o = class_getInstanceMethod(cls, original),
              let r = class_getInstanceMethod(cls, replacement) else {
            log("swizzle failed: \(original)")
            return
        }
        method_exchangeImplementations(o, r)
    }

    private static func log(_ message: String) {
        guard logEnabled else { return }
        NSLog("[QAAutoID] %@", message)
    }
}

// MARK: - Swizzled methods

extension UIViewController {
    @objc func qa_viewDidAppear(_ animated: Bool) {
        qa_viewDidAppear(animated) // 원래 구현 호출
        QAAutoID.handle(viewController: self)
    }
}

extension UIViewController {
    @objc func qa_viewDidLayoutSubviews() {
        qa_viewDidLayoutSubviews() // 원래 구현 호출
        QAAutoID.handleLayout(viewController: self)
    }
}

extension UIView {
    @objc func qa_didMoveToWindow() {
        qa_didMoveToWindow() // 원래 구현 호출
        if window != nil { QAAutoID.handle(view: self) }
    }
}
