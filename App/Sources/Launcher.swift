import AppKit
import SwiftUI

/// 최근 연 작업공간 (최대 10개, UserDefaults)
final class Recents: ObservableObject {
    @Published private(set) var paths: [String]
    private let key = "recentWorkspaces"

    init() { paths = UserDefaults.standard.stringArray(forKey: key) ?? [] }

    func add(_ path: String) {
        paths.removeAll { $0 == path }
        paths.insert(path, at: 0)
        paths = Array(paths.prefix(10))
        UserDefaults.standard.set(paths, forKey: key)
    }

    func remove(_ path: String) {
        paths.removeAll { $0 == path }
        UserDefaults.standard.set(paths, forKey: key)
    }
}

/// 처음 화면: 최근 작업공간 + 폴더 열기
struct LauncherView: View {
    @ObservedObject var recents: Recents
    let open: (String) -> Void
    let openFolder: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            VStack(alignment: .leading, spacing: 4) {
                Text("QA Kit").font(.system(size: 26, weight: .semibold))
                Text(Kit.dir == nil ? "도구 폴더를 찾지 못했습니다 (Resources/kit)" : "qakit \(Kit.version)")
                    .font(.callout).foregroundColor(Kit.dir == nil ? .red : .secondary)
            }
            .padding(.horizontal, 28).padding(.top, 36).padding(.bottom, 18)

            Text("최근 작업공간").font(.subheadline.weight(.semibold)).foregroundColor(.secondary)
                .padding(.horizontal, 28).padding(.bottom, 6)

            if recents.paths.isEmpty {
                Text("아직 연 작업공간이 없습니다.\n아래 \"폴더 열기\"로 qakit.yml이 있는 폴더를 고르세요.")
                    .font(.callout).foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                    .padding(.horizontal, 28).padding(.top, 8)
            } else {
                ScrollView {
                    VStack(spacing: 2) {
                        ForEach(recents.paths, id: \.self) { path in
                            RecentRow(path: path, open: open, remove: { recents.remove(path) })
                        }
                    }
                    .padding(.horizontal, 16)
                }
            }

            Divider()
            HStack {
                Text("작업공간이 없으면 터미널에서 qakit init <앱 프로젝트> --worktree")
                    .font(.caption).foregroundColor(.secondary).textSelection(.enabled)
                Spacer()
                Button("폴더 열기…", action: openFolder).keyboardShortcut("o").controlSize(.large)
            }
            .padding(.horizontal, 20).padding(.vertical, 14)
        }
        .frame(minWidth: 520, minHeight: 400)
    }
}

private struct RecentRow: View {
    let path: String
    let open: (String) -> Void
    let remove: () -> Void
    @State private var hover = false

    private var exists: Bool {
        FileManager.default.fileExists(atPath: (path as NSString).appendingPathComponent("qakit.yml"))
    }

    var body: some View {
        Button { if exists { open(path) } } label: {
            HStack(spacing: 10) {
                Image(systemName: "folder").foregroundColor(.accentColor).frame(width: 20)
                VStack(alignment: .leading, spacing: 1) {
                    Text(title).font(.body.weight(.medium)).lineLimit(1)
                    Text((path as NSString).abbreviatingWithTildeInPath + (exists ? "" : " — 없음"))
                        .font(.caption).foregroundColor(.secondary).lineLimit(1).truncationMode(.middle)
                }
                Spacer()
            }
            .padding(.horizontal, 12).padding(.vertical, 8)
            .background(RoundedRectangle(cornerRadius: 8).fill(hover ? Color.primary.opacity(0.07) : .clear))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .opacity(exists ? 1 : 0.5)
        .onHover { hover = $0 }
        .contextMenu {
            Button("Finder에서 보기") { NSWorkspace.shared.selectFile(nil, inFileViewerRootedAtPath: path) }
            Button("목록에서 빼기", action: remove)
        }
    }

    /// QA 폴더 이름이 "QA"뿐이면 위 폴더(앱 레포·워크트리) 이름을 같이
    private var title: String {
        let u = URL(fileURLWithPath: path)
        let name = u.lastPathComponent
        return name.count <= 3 ? "\(u.deletingLastPathComponent().lastPathComponent) / \(name)" : name
    }
}
