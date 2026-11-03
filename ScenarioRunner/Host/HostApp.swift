// 시나리오 실행기용 빈 호스트 앱. 실제 대상은 qakit.yml의 bundleId 앱이다.
import SwiftUI

@main
struct HostApp: App {
    var body: some Scene { WindowGroup { Text("qakit scenario runner") } }
}
