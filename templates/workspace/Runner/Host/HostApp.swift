// 테스트 실행용 빈 호스트 앱. 실제 테스트 대상은 qakit.yml의 bundleId 앱이다. 수정하지 않는다.
import SwiftUI

@main
struct HostApp: App {
    var body: some Scene { WindowGroup { Text("qakit runner") } }
}
