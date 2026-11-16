// QA Kit 맥 앱 — 작업공간마다 `qakit ui` 서버를 띄우고 웹 UI를 창(WKWebView)으로 연다.
// 빌드: scripts/build-app.sh (docs/PLAN.md "맥 앱(DMG) 설계" D2)
import AppKit

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
