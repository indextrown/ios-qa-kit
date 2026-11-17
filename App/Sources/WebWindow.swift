import AppKit
import Combine
import WebKit

/// 웹 UI를 담는 창. 작업공간 창(서버 있음)과 그 창에서 새 탭으로 연 결과 파일 창(서버 없음)이 같이 쓴다.
/// 브라우저가 해 주던 것: 내려받기, alert·confirm·prompt, 새 창(target=_blank), 바깥 링크는 기본 브라우저로.
class WebWindow: NSObject, NSWindowDelegate, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
    let window: NSWindow
    let web: WKWebView
    /// 이 서버(127.0.0.1:포트)의 주소만 창 안에서 연다
    var origin: URL?
    private var children: [WebWindow] = []
    private var downloads: [ObjectIdentifier: URL] = [:]
    weak var parent: WebWindow?

    init(configuration: WKWebViewConfiguration? = nil, title: String, size: NSSize, autosave: String?) {
        let cfg = configuration ?? {
            let c = WKWebViewConfiguration()
            c.websiteDataStore = .default()   // 쿠키(로그인)·localStorage(설정)를 남긴다
            c.preferences.setValue(true, forKey: "developerExtrasEnabled")   // 우클릭 → 요소 검사
            return c
        }()
        web = WKWebView(frame: NSRect(origin: .zero, size: size), configuration: cfg)
        if #available(macOS 13.3, *) { web.isInspectable = true }
        web.pageZoom = AppState.shared.zoom
        window = NSWindow(contentRect: NSRect(origin: .zero, size: size),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        super.init()
        window.title = title
        window.isReleasedWhenClosed = false
        window.minSize = NSSize(width: 720, height: 480)
        window.contentView = web
        window.delegate = self
        web.navigationDelegate = self
        web.uiDelegate = self
        if let autosave, !window.setFrameUsingName(autosave) { window.center() }
        if let autosave { window.setFrameAutosaveName(autosave) }
        if autosave == nil { window.center() }
        zoomSub = AppState.shared.$zoom.sink { [weak self] z in self?.web.pageZoom = z }
    }

    private var zoomSub: AnyCancellable?

    func show() {
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func closeChildren() {
        children.forEach { $0.window.close() }
        children.removeAll()
    }

    func windowWillClose(_ notification: Notification) {
        closeChildren()
        parent?.children.removeAll { $0 === self }
    }

    // MARK: 상태 화면 (서버 켜는 중·실패)

    func showStatus(title: String, detail: String = "", retry: Bool = false, spinner: Bool = false) {
        let esc = { (s: String) in s.replacingOccurrences(of: "&", with: "&amp;").replacingOccurrences(of: "<", with: "&lt;") }
        let html = """
        <!doctype html><meta charset="utf-8"><style>
        :root{color-scheme:light dark;--fg:#1d1d1f;--sub:#6e6e73;--bg:#f5f5f7;--card:#fff;--acc:#0a66ff}
        @media (prefers-color-scheme:dark){:root{--fg:#f5f5f7;--sub:#a1a1a6;--bg:#1c1c1e;--card:#2c2c2e;--acc:#4c8dff}}
        body{margin:0;height:100vh;display:flex;align-items:center;justify-content:center;background:var(--bg);color:var(--fg);font:14px -apple-system,system-ui}
        .c{max-width:720px;padding:32px;text-align:center}h1{font-size:18px;font-weight:600;margin:12px 0 8px}
        pre{text-align:left;white-space:pre-wrap;background:var(--card);color:var(--sub);padding:12px;border-radius:10px;max-height:50vh;overflow:auto;font:12px ui-monospace,Menlo}
        a{display:inline-block;margin-top:16px;padding:8px 18px;border-radius:8px;background:var(--acc);color:#fff;text-decoration:none}
        .s{width:22px;height:22px;margin:auto;border:3px solid var(--sub);border-top-color:transparent;border-radius:50%;animation:r 1s linear infinite}
        @keyframes r{to{transform:rotate(360deg)}}</style>
        <div class="c">\(spinner ? "<div class=s></div>" : "")<h1>\(esc(title))</h1>
        \(detail.isEmpty ? "" : "<pre>\(esc(detail))</pre>")\(retry ? "<a href=\"qakit-app:retry\">다시 시도</a>" : "")</div>
        """
        web.loadHTMLString(html, baseURL: nil)
    }

    /// 상태 화면의 "다시 시도"
    func retry() {}

    private func isOurs(_ url: URL) -> Bool {
        if ["about", "blob", "data"].contains(url.scheme ?? "") { return true }
        guard let o = origin else { return false }
        return url.scheme == o.scheme && url.host == o.host && url.port == o.port
    }

    // MARK: WKNavigationDelegate

    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = action.request.url else { return decisionHandler(.allow) }
        if url.scheme == "qakit-app" {
            let app = NSApp.delegate as? AppDelegate
            switch url.host {
            case "open":   // 웹 화면의 작업공간 바꾸기 → 그 작업공간 창 (이미 열려 있으면 그 창으로)
                if let path = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?.first(where: { $0.name == "path" })?.value {
                    app?.open(path: path)
                }
            case "open-folder":
                app?.openFolder(nil)
            default:
                if url.absoluteString.hasSuffix("retry") { retry() }
            }
            return decisionHandler(.cancel)
        }
        if action.shouldPerformDownload { return decisionHandler(.download) }   // <a download>
        if ["http", "https", "mailto"].contains(url.scheme ?? ""), !isOurs(url), action.targetFrame?.isMainFrame ?? true {
            NSWorkspace.shared.open(url)   // 바깥 링크(GitHub 등)는 기본 브라우저로
            return decisionHandler(.cancel)
        }
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, decidePolicyFor response: WKNavigationResponse,
                 decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        let disposition = (response.response as? HTTPURLResponse)?.value(forHTTPHeaderField: "Content-Disposition") ?? ""
        if disposition.lowercased().hasPrefix("attachment") || !response.canShowMIMEType {
            return decisionHandler(.download)
        }
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) {
        download.delegate = self
    }

    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) {
        download.delegate = self
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        webView.reload()
    }

    // MARK: 내려받기 → ~/Downloads (같은 이름이 있으면 "이름 2.mp4")

    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse, suggestedFilename: String,
                  completionHandler: @escaping (URL?) -> Void) {
        let dir = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask)[0]
        let name = suggestedFilename.isEmpty ? "download" : suggestedFilename
        let ext = (name as NSString).pathExtension, stem = (name as NSString).deletingPathExtension
        var dest = dir.appendingPathComponent(name)
        var n = 2
        while FileManager.default.fileExists(atPath: dest.path) {
            dest = dir.appendingPathComponent(ext.isEmpty ? "\(stem) \(n)" : "\(stem) \(n).\(ext)")
            n += 1
        }
        downloads[ObjectIdentifier(download)] = dest
        completionHandler(dest)
    }

    func downloadDidFinish(_ download: WKDownload) {
        guard let dest = downloads.removeValue(forKey: ObjectIdentifier(download)) else { return }
        // Dock의 다운로드 폴더가 튀어 오르게 (Safari와 같은 신호)
        DistributedNotificationCenter.default().post(name: .init("com.apple.DownloadFileFinished"), object: dest.path)
    }

    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
        downloads.removeValue(forKey: ObjectIdentifier(download))
        alert("내려받지 못했습니다", error.localizedDescription)
    }

    // MARK: WKUIDelegate — 새 창, alert·confirm·prompt, 파일 고르기

    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        guard let url = action.request.url else { return nil }
        if !isOurs(url) {
            NSWorkspace.shared.open(url)
            return nil
        }
        // 결과 파일(사진·리포트)은 쿠키 로그인이 필요해 기본 브라우저로는 안 열린다 → 같은 세션의 작은 창으로
        let child = WebWindow(configuration: configuration, title: url.lastPathComponent, size: NSSize(width: 900, height: 760), autosave: nil)
        child.origin = origin
        child.parent = self
        children.append(child)
        child.window.cascadeTopLeft(from: NSPoint(x: window.frame.minX + 30, y: window.frame.maxY - 30))
        child.show()
        return child.web
    }

    func webViewDidClose(_ webView: WKWebView) {
        if webView === web, parent != nil { window.close() }
    }

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let a = NSAlert()
        a.messageText = message
        a.addButton(withTitle: "확인")
        a.beginSheetModal(for: window) { _ in completionHandler() }
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let a = NSAlert()
        a.messageText = message
        a.addButton(withTitle: "확인")
        a.addButton(withTitle: "취소")
        a.beginSheetModal(for: window) { completionHandler($0 == .alertFirstButtonReturn) }
    }

    func webView(_ webView: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String, defaultText: String?,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (String?) -> Void) {
        let a = NSAlert()
        a.messageText = prompt
        let field = NSTextField(frame: NSRect(x: 0, y: 0, width: 300, height: 24))
        field.stringValue = defaultText ?? ""
        a.accessoryView = field
        a.addButton(withTitle: "확인")
        a.addButton(withTitle: "취소")
        a.window.initialFirstResponder = field
        a.beginSheetModal(for: window) { completionHandler($0 == .alertFirstButtonReturn ? field.stringValue : nil) }
    }

    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let p = NSOpenPanel()
        p.allowsMultipleSelection = parameters.allowsMultipleSelection
        p.canChooseDirectories = parameters.allowsDirectories
        p.beginSheetModal(for: window) { completionHandler($0 == .OK ? p.urls : nil) }
    }

    func alert(_ title: String, _ detail: String) {
        let a = NSAlert()
        a.messageText = title
        a.informativeText = detail
        a.beginSheetModal(for: window)
    }
}

/// 작업공간 하나 = 창 하나 + qakit ui 서버 하나
final class WorkspaceWindow: WebWindow {
    let path: String
    let server: Server
    var onClose: ((WorkspaceWindow) -> Void)?

    init(path: String) {
        self.path = path
        server = Server(workspace: path)
        super.init(title: (path as NSString).lastPathComponent, size: NSSize(width: 1440, height: 900), autosave: "workspace:" + path)
        window.subtitle = (path as NSString).abbreviatingWithTildeInPath
        window.tabbingMode = .disallowed
        server.onExit = { [weak self] log in
            self?.origin = nil
            self?.busyText = nil
            self?.showStatus(title: "qakit ui 서버가 멈췄습니다", detail: log, retry: true)
        }
        startServer()
    }

    private var token: String?
    private var poll: Timer?
    /// 지금 도는 것 ("시나리오 실행 중: home-01" 등). 없으면 nil
    private(set) var busyText: String? {
        didSet { AppState.shared.busy[path] = busyText }
    }

    /// 서버의 /api/busy를 3초마다 (메뉴 막대·닫기 전 확인용). 토큰은 헤더로.
    private func startPolling() {
        poll?.invalidate()
        poll = Timer.scheduledTimer(withTimeInterval: 3, repeats: true) { [weak self] _ in self?.checkBusy() }
        checkBusy()
    }

    func checkBusy(sync: Bool = false) {
        guard let o = origin, let token, let url = URL(string: "/api/busy", relativeTo: o) else { busyText = nil; return }
        var req = URLRequest(url: url, timeoutInterval: 2)
        req.setValue(token, forHTTPHeaderField: "X-Qakit-Token")
        let sem = DispatchSemaphore(value: 0)
        URLSession.shared.dataTask(with: req) { [weak self] data, _, _ in
            defer { sem.signal() }
            struct Busy: Decodable { let run: Bool; let runArgs: [String]?; let ai: Bool; let aiGoal: String?; let record: Bool }
            let b = data.flatMap { try? JSONDecoder().decode(Busy.self, from: $0) }
            var parts: [String] = []
            if let b {
                if b.run { parts.append("시나리오 실행 중" + ((b.runArgs?.dropFirst().first).map { ": \($0)" } ?? "")) }
                if b.ai { parts.append("AI 작업 중" + (b.aiGoal.map { ": \($0.prefix(30))" } ?? "")) }
                if b.record { parts.append("녹화 중") }
            }
            let text = parts.isEmpty ? nil : parts.joined(separator: " · ")
            DispatchQueue.main.async { if self?.busyText != text { self?.busyText = text } }
        }.resume()
        if sync { _ = sem.wait(timeout: .now() + 2) }
    }

    /// 도는 중이면 닫기 전에 묻는다 (설정에서 끌 수 있음)
    func windowShouldClose(_ sender: NSWindow) -> Bool {
        guard AppState.shared.confirmWhenBusy, let b = busyText else { return true }
        let a = NSAlert()
        a.messageText = "\(window.title) — \(b)"
        a.informativeText = "창을 닫으면 서버와 함께 멈춥니다."
        a.addButton(withTitle: "닫기")
        a.addButton(withTitle: "취소")
        return a.runModal() == .alertFirstButtonReturn
    }

    private func startServer() {
        showStatus(title: "qakit ui를 켜는 중…", detail: "", spinner: true)
        server.start { [weak self] result in
            guard let self else { return }
            switch result {
            case .success(let url):
                var o = URLComponents(url: url, resolvingAgainstBaseURL: false)!
                self.token = o.queryItems?.first { $0.name == "token" }?.value
                o.path = ""; o.query = nil
                self.origin = o.url
                self.startPolling()
                self.web.load(URLRequest(url: url))
            case .failure(let e):
                self.showStatus(title: "qakit ui를 켜지 못했습니다", detail: e.text, retry: true)
            }
        }
    }

    override func retry() {
        if !server.isRunning { startServer() } else if let o = origin { web.load(URLRequest(url: o)) }
    }

    func reload() {
        if origin != nil { web.reload() } else { retry() }
    }

    override func windowWillClose(_ notification: Notification) {
        super.windowWillClose(notification)
        poll?.invalidate()
        busyText = nil
        server.stop()
        onClose?(self)
    }
}
