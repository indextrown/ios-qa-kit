import AppKit
import Combine

/// 메뉴 막대 아이콘: 열린 작업공간과 지금 도는 것(시나리오·AI·녹화). 도는 중이면 아이콘이 채워진다.
final class StatusBar: NSObject, NSMenuDelegate {
    private var item: NSStatusItem?
    private var bag: Set<AnyCancellable> = []
    private weak var app: AppDelegate?

    init(app: AppDelegate) {
        self.app = app
        super.init()
        let s = AppState.shared
        s.$showStatusItem.sink { [weak self] on in self?.setVisible(on) }.store(in: &bag)
        s.$busy.sink { [weak self] busy in self?.updateIcon(busy: !busy.isEmpty) }.store(in: &bag)
    }

    private func setVisible(_ on: Bool) {
        if on, item == nil {
            let i = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
            let m = NSMenu()
            m.delegate = self
            i.menu = m
            item = i
            updateIcon(busy: !AppState.shared.busy.isEmpty)
        } else if !on, let i = item {
            NSStatusBar.system.removeStatusItem(i)
            item = nil
        }
    }

    private func updateIcon(busy: Bool) {
        guard let button = item?.button else { return }
        let img = NSImage(systemSymbolName: busy ? "checkmark.seal.fill" : "checkmark.seal", accessibilityDescription: "QA Kit")
        img?.isTemplate = true
        button.image = img
        button.title = busy ? " 실행 중" : ""
        button.imagePosition = .imageLeading
    }

    func menuNeedsUpdate(_ menu: NSMenu) {
        menu.removeAllItems()
        guard let app else { return }
        let open = app.openWorkspaces
        if open.isEmpty {
            menu.addItem(disabled("열린 작업공간 없음"))
        } else {
            menu.addItem(disabled("열린 작업공간"))
            for w in open {
                let i = NSMenuItem(title: (w.path as NSString).abbreviatingWithTildeInPath, action: #selector(AppDelegate.focusWorkspace(_:)), keyEquivalent: "")
                i.representedObject = w.path
                i.target = app
                i.image = NSImage(systemSymbolName: AppState.shared.busy[w.path] != nil ? "circle.fill" : "circle", accessibilityDescription: nil)
                menu.addItem(i)
                if let b = AppState.shared.busy[w.path] {
                    let sub = disabled("    " + b)
                    menu.addItem(sub)
                }
            }
        }
        menu.addItem(.separator())
        menu.addItem(action("작업공간 열기…", #selector(AppDelegate.openFolder(_:))))
        menu.addItem(action("작업공간 목록", #selector(AppDelegate.showLauncher(_:))))
        menu.addItem(action("설정…", #selector(AppDelegate.showSettingsMenu(_:))))
        menu.addItem(.separator())
        menu.addItem(action("QA Kit 종료", #selector(NSApplication.terminate(_:)), target: NSApp))
    }

    private func disabled(_ title: String) -> NSMenuItem {
        let i = NSMenuItem(title: title, action: nil, keyEquivalent: "")
        i.isEnabled = false
        return i
    }

    private func action(_ title: String, _ sel: Selector, target: AnyObject? = nil) -> NSMenuItem {
        let i = NSMenuItem(title: title, action: sel, keyEquivalent: "")
        i.target = target ?? app
        return i
    }
}
