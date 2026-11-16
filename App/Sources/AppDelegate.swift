import AppKit
import SwiftUI

final class AppDelegate: NSObject, NSApplicationDelegate, NSMenuDelegate {
    private var workspaces: [String: WorkspaceWindow] = [:]
    private var launcher: NSWindow?
    private var settings: NSWindow?
    private var statusBar: StatusBar?
    let recents = Recents()

    var openWorkspaces: [WorkspaceWindow] { workspaces.values.sorted { $0.path < $1.path } }

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.mainMenu = makeMenu()
        statusBar = StatusBar(app: self)
        // ⌘+는 Shift가 필요한 자판이 많아 ⌘=도 확대로
        NSEvent.addLocalMonitorForEvents(matching: .keyDown) { e in
            let mods = e.modifierFlags.intersection([.command, .shift, .option, .control])
            if mods == .command, e.charactersIgnoringModifiers == "=" { AppState.shared.zoomIn(); return nil }
            return e
        }
        // 처음 점검: 필수 도구(Xcode·xcodegen 등)가 빠졌으면 설정의 환경 점검을 연다
        AppState.shared.runChecks { [weak self] in
            if AppState.shared.problems > 0 { self?.showSettings(tab: .check) }
        }
        // `open -a "QA Kit" --args -workspace <경로>`나 Finder로 폴더를 끌어 놓은 경우는 application(_:open:)
        if let ws = UserDefaults.standard.string(forKey: "workspace") {
            open(path: ws)
        } else if workspaces.isEmpty {
            showLauncher()
        }
    }

    func application(_ application: NSApplication, open urls: [URL]) {
        urls.forEach { open(path: $0.path) }
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if !flag { showLauncher() }
        return true
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    /// 끌 때 서버를 모두 SIGINT로 멈추고(실행·AI·녹화 정리) 끝난 뒤에 앱을 닫는다
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        let busy = workspaces.values.filter { $0.busyText != nil }
        if AppState.shared.confirmWhenBusy, !busy.isEmpty {
            let a = NSAlert()
            a.messageText = "도는 중인 작업이 있습니다"
            a.informativeText = busy.map { "\($0.window.title): \($0.busyText ?? "")" }.joined(separator: "\n") + "\n\n끄면 모두 멈춥니다."
            a.addButton(withTitle: "끄기")
            a.addButton(withTitle: "취소")
            if a.runModal() != .alertFirstButtonReturn { return .terminateCancel }
        }
        let servers = workspaces.values.map(\.server).filter(\.isRunning)
        if servers.isEmpty { return .terminateNow }
        DispatchQueue.global().async {
            let group = DispatchGroup()
            for s in servers {
                group.enter()
                DispatchQueue.global().async { s.stop(wait: true); group.leave() }
            }
            group.wait()
            DispatchQueue.main.async { NSApp.reply(toApplicationShouldTerminate: true) }
        }
        return .terminateLater
    }

    // MARK: 작업공간

    func open(path raw: String) {
        let path = URL(fileURLWithPath: raw).standardizedFileURL.resolvingSymlinksInPath().path
        if let w = workspaces[path] { return w.show() }   // 이미 열려 있으면 그 창으로 (서버 둘 방지)
        guard FileManager.default.fileExists(atPath: (path as NSString).appendingPathComponent("qakit.yml")) else {
            let a = NSAlert()
            a.messageText = "qakit 작업공간이 아닙니다"
            a.informativeText = "\((path as NSString).abbreviatingWithTildeInPath)에 qakit.yml이 없습니다.\n작업공간이 없으면 터미널에서 먼저 만드세요:\nqakit init <앱 프로젝트> --worktree"
            a.runModal()
            return
        }
        recents.add(path)
        let w = WorkspaceWindow(path: path)
        w.onClose = { [weak self] w in
            self?.workspaces.removeValue(forKey: w.path)
            if self?.workspaces.isEmpty == true { self?.showLauncher() }
        }
        workspaces[path] = w
        w.show()
        launcher?.close()
    }

    @objc func openFolder(_ sender: Any?) {
        let p = NSOpenPanel()
        p.canChooseDirectories = true
        p.canChooseFiles = false
        p.prompt = "열기"
        p.message = "qakit.yml이 있는 작업공간 폴더를 고르세요"
        if p.runModal() == .OK, let url = p.url { open(path: url.path) }
    }

    @objc func showLauncher(_ sender: Any? = nil) {
        if launcher == nil {
            let w = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 560, height: 440),
                             styleMask: [.titled, .closable, .fullSizeContentView], backing: .buffered, defer: false)
            w.titlebarAppearsTransparent = true
            w.titleVisibility = .hidden
            w.isReleasedWhenClosed = false
            w.contentView = NSHostingView(rootView: LauncherView(recents: recents,
                                                                 open: { [weak self] in self?.open(path: $0) },
                                                                 openFolder: { [weak self] in self?.openFolder(nil) },
                                                                 settings: { [weak self] in self?.showSettings(tab: .check) }))
            w.center()
            launcher = w
        }
        launcher?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    // MARK: 설정

    func showSettings(tab: SettingsTab) {
        if settings == nil {
            let w = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 640, height: 500),
                             styleMask: [.titled, .closable], backing: .buffered, defer: false)
            w.title = "설정"
            w.isReleasedWhenClosed = false
            w.center()
            settings = w
        }
        settings?.contentView = NSHostingView(rootView: SettingsView(tab: tab))
        settings?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    @objc func showSettingsMenu(_ sender: Any?) { showSettings(tab: .general) }
    @objc func zoomIn(_ sender: Any?) { AppState.shared.zoomIn() }
    @objc func zoomOut(_ sender: Any?) { AppState.shared.zoomOut() }
    @objc func zoomReset(_ sender: Any?) { AppState.shared.zoomReset() }

    @objc func focusWorkspace(_ sender: NSMenuItem) {
        if let p = sender.representedObject as? String { workspaces[p]?.show() }
    }

    private var keyWorkspace: WorkspaceWindow? {
        workspaces.values.first { $0.window === NSApp.keyWindow }
    }

    @objc func reloadPage(_ sender: Any?) { keyWorkspace?.reload() }

    @objc func openRecent(_ sender: NSMenuItem) {
        if let path = sender.representedObject as? String { open(path: path) }
    }

    @objc func showInFinder(_ sender: Any?) {
        if let w = keyWorkspace { NSWorkspace.shared.selectFile(nil, inFileViewerRootedAtPath: w.path) }
    }

    @objc func openHelp(_ sender: Any?) {
        NSWorkspace.shared.open(URL(string: "https://github.com/indextrown/qa-kit")!)
    }

    // MARK: 메뉴 (편집 메뉴가 있어야 웹뷰에서 ⌘C·⌘V가 된다)

    private func makeMenu() -> NSMenu {
        let main = NSMenu()
        func sub(_ title: String, _ items: [NSMenuItem]) -> NSMenu {
            let m = NSMenu(title: title)
            items.forEach(m.addItem)
            let host = NSMenuItem(title: title, action: nil, keyEquivalent: "")
            host.submenu = m
            main.addItem(host)
            return m
        }
        func item(_ title: String, _ action: Selector?, _ key: String = "", _ mods: NSEvent.ModifierFlags = .command) -> NSMenuItem {
            let i = NSMenuItem(title: title, action: action, keyEquivalent: key)
            i.keyEquivalentModifierMask = mods
            return i
        }
        _ = sub("QA Kit", [
            item("QA Kit 정보", #selector(NSApplication.orderFrontStandardAboutPanel(_:))),
            .separator(),
            item("설정…", #selector(showSettingsMenu(_:)), ","),
            .separator(),
            item("QA Kit 가리기", #selector(NSApplication.hide(_:)), "h"),
            item("기타 가리기", #selector(NSApplication.hideOtherApplications(_:)), "h", [.command, .option]),
            item("모두 보기", #selector(NSApplication.unhideAllApplications(_:))),
            .separator(),
            item("QA Kit 종료", #selector(NSApplication.terminate(_:)), "q"),
        ])
        let recent = NSMenuItem(title: "최근 작업공간", action: nil, keyEquivalent: "")
        recent.submenu = NSMenu(title: "최근 작업공간")
        recent.submenu?.delegate = self
        _ = sub("파일", [
            item("작업공간 열기…", #selector(openFolder(_:)), "o"),
            item("작업공간 목록", #selector(showLauncher(_:)), "o", [.command, .shift]),
            recent,
            .separator(),
            item("Finder에서 보기", #selector(showInFinder(_:)), "r", [.command, .shift]),
            .separator(),
            item("창 닫기", #selector(NSWindow.performClose(_:)), "w"),
        ])
        _ = sub("편집", [
            item("실행 취소", Selector(("undo:")), "z"),
            item("실행 복귀", Selector(("redo:")), "z", [.command, .shift]),
            .separator(),
            item("오려두기", #selector(NSText.cut(_:)), "x"),
            item("복사하기", #selector(NSText.copy(_:)), "c"),
            item("붙여넣기", #selector(NSText.paste(_:)), "v"),
            item("모두 선택", #selector(NSText.selectAll(_:)), "a"),
        ])
        _ = sub("보기", [
            item("새로고침", #selector(reloadPage(_:)), "r"),
            .separator(),
            item("실제 크기", #selector(zoomReset(_:)), "0"),
            item("확대", #selector(zoomIn(_:)), "+"),
            item("축소", #selector(zoomOut(_:)), "-"),
            .separator(),
            item("전체 화면", #selector(NSWindow.toggleFullScreen(_:)), "f", [.command, .control]),
        ])
        let win = sub("윈도우", [
            item("최소화", #selector(NSWindow.performMiniaturize(_:)), "m"),
            item("확대/축소", #selector(NSWindow.performZoom(_:))),
            .separator(),
            item("모두 앞으로 가져오기", #selector(NSApplication.arrangeInFront(_:))),
        ])
        NSApp.windowsMenu = win
        let help = sub("도움말", [item("QA Kit 저장소 (GitHub)", #selector(openHelp(_:)))])
        NSApp.helpMenu = help
        return main
    }

    func menuNeedsUpdate(_ menu: NSMenu) {   // 최근 작업공간
        menu.removeAllItems()
        for path in recents.paths {
            let i = NSMenuItem(title: (path as NSString).abbreviatingWithTildeInPath, action: #selector(openRecent(_:)), keyEquivalent: "")
            i.representedObject = path
            menu.addItem(i)
        }
        if recents.paths.isEmpty { menu.addItem(NSMenuItem(title: "없음", action: nil, keyEquivalent: "")) }
    }
}
