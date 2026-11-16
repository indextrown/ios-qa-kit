import AppKit
import SwiftUI

enum SettingsTab: String { case general, cli, check }

/// 설정 창 (⌘,): 일반(화면 크기·메뉴 막대) · 명령줄·스킬 · 환경 점검
struct SettingsView: View {
    @ObservedObject var state = AppState.shared
    @State var tab: SettingsTab

    var body: some View {
        TabView(selection: $tab) {
            GeneralTab(state: state).tabItem { Label("일반", systemImage: "gearshape") }.tag(SettingsTab.general)
            CliTab(state: state).tabItem { Label("명령줄·스킬", systemImage: "terminal") }.tag(SettingsTab.cli)
            CheckTab(state: state).tabItem { Label("환경 점검", systemImage: "stethoscope") }.tag(SettingsTab.check)
        }
        .padding(20)
        .frame(width: 600, height: 460)
    }
}

private struct GeneralTab: View {
    @ObservedObject var state: AppState

    var body: some View {
        Form {
            Section {
                HStack {
                    Text("화면 크기")
                    Slider(value: Binding(get: { nearestIndex }, set: { state.zoom = AppState.zoomSteps[Int($0.rounded())] }),
                           in: 0...Double(AppState.zoomSteps.count - 1), step: 1)
                    Text("\(Int((state.zoom * 100).rounded()))%").monospacedDigit().frame(width: 48, alignment: .trailing)
                }
                HStack {
                    Button("축소") { state.zoomOut() }
                    Button("100%") { state.zoomReset() }
                    Button("확대") { state.zoomIn() }
                    Spacer()
                    Text("⌘− · ⌘0 · ⌘+").font(.caption).foregroundColor(.secondary)
                }
                Text("모든 작업공간 창의 웹 화면 크기입니다. 시뮬레이터 화면·글자가 작거나 크면 바꾸세요.")
                    .font(.caption).foregroundColor(.secondary)
            }
            UpdateSection()
            Section {
                Toggle("메뉴 막대에 아이콘 보이기 (열린 작업공간·실행 중 표시)", isOn: $state.showStatusItem)
                Toggle("시나리오·AI·녹화가 도는 중이면 창을 닫거나 끄기 전에 묻기", isOn: $state.confirmWhenBusy)
            }
            Section {
                LabeledContent("qakit", value: Kit.version)
                LabeledContent("도구 폴더", value: Kit.dir.map { ($0.path as NSString).abbreviatingWithTildeInPath } ?? "없음")
                LabeledContent("빌드 결과", value: "~/Library/Application Support/qakit")
            }
        }
        .formStyle(.grouped)
    }

    private var nearestIndex: Double {
        let i = AppState.zoomSteps.enumerated().min { abs($0.element - state.zoom) < abs($1.element - state.zoom) }?.offset ?? 5
        return Double(i)
    }
}

private struct UpdateSection: View {
    @ObservedObject var up = Updater.shared

    var body: some View {
        Section("업데이트") {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(status).fontWeight(.medium)
                    if let d = up.lastChecked {
                        Text("마지막 확인 \(d.formatted(date: .abbreviated, time: .shortened))").font(.caption).foregroundColor(.secondary)
                    }
                }
                Spacer()
                switch up.phase {
                case .checking, .installing: ProgressView().controlSize(.small)
                case .downloading(let f): ProgressView(value: f).frame(width: 120)
                default:
                    if up.hasUpdate {
                        if up.canInstall {
                            Button("업데이트하고 다시 켜기") { up.install() }.keyboardShortcut(.defaultAction)
                        } else {
                            Button("릴리스 페이지") { up.openReleasePage() }
                        }
                    }
                    Button("새 버전 확인") { up.check() }
                }
            }
            if up.hasUpdate, !up.canInstall {
                Text("이 앱은 저장소에서 만든 개발용이라 자동으로 바꾸지 않습니다. 릴리스의 DMG로 설치한 앱만 바꿉니다.")
                    .font(.caption).foregroundColor(.secondary)
            }
            Toggle("켤 때 새 버전 확인 (하루 한 번)", isOn: $up.autoCheck)
        }
    }

    private var status: String {
        switch up.phase {
        case .idle: return "qakit \(up.current)"
        case .checking: return "확인하는 중…"
        case .upToDate: return "최신입니다 (\(up.current))"
        case .available: return "새 버전 \(up.latest?.version ?? "") — 지금 \(up.current)"
        case .downloading(let f): return "내려받는 중… \(Int(f * 100))%"
        case .installing: return "바꾸는 중… 앱이 다시 켜집니다"
        case .failed(let e): return e
        }
    }
}

private struct CliTab: View {
    @ObservedObject var state: AppState
    @State private var output = ""
    @State private var working = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("터미널의 `qakit` 명령과 Claude Code·Codex 스킬(/qa-kit, $qa-kit)이 이 앱 안 도구를 쓰게 연결합니다. 앱을 업데이트하면 따라 바뀝니다.")
                .font(.callout).foregroundColor(.secondary).fixedSize(horizontal: false, vertical: true)
            VStack(spacing: 0) {
                ForEach(state.links) { l in
                    HStack(alignment: .top) {
                        Image(systemName: icon(l.state)).foregroundColor(color(l.state)).frame(width: 18)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(l.label).fontWeight(.medium)
                            Text((l.path.path as NSString).abbreviatingWithTildeInPath).font(.caption).foregroundColor(.secondary)
                        }
                        Spacer()
                        Text(describe(l.state)).font(.caption).foregroundColor(.secondary)
                            .multilineTextAlignment(.trailing).lineLimit(2).truncationMode(.middle).frame(maxWidth: 260, alignment: .trailing)
                    }
                    .padding(.vertical, 8)
                    Divider()
                }
            }
            HStack {
                Button(working ? "연결하는 중…" : "이 앱으로 연결") { install() }.disabled(working)
                Button("이 앱 연결 풀기") { state.removeAppLinks() }.disabled(!state.links.contains { if case .app = $0.state { return true }; return false })
                Spacer()
            }
            if hasOther {
                Text("⚠️ 다른 곳(git으로 설치한 qakit 등)을 가리키는 연결이 있습니다. \"이 앱으로 연결\"을 누르면 앱 쪽으로 바뀝니다 — 되돌리려면 그 도구 폴더에서 bin/qakit install-skill.")
                    .font(.caption).foregroundColor(.orange).fixedSize(horizontal: false, vertical: true)
            }
            if !output.isEmpty {
                ScrollView { Text(output).font(.system(.caption, design: .monospaced)).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading) }
                    .frame(maxHeight: 110)
            }
            Spacer()
        }
        .onAppear { state.refreshLinks() }
    }

    private var hasOther: Bool { state.links.contains { if case .other = $0.state { return true }; return false } }

    private func install() {
        if hasOther {
            let a = NSAlert()
            a.messageText = "다른 qakit 설치를 이 앱으로 바꿀까요?"
            a.informativeText = "지금 연결은 다른 도구 폴더(git 설치 등)를 가리킵니다. 바꾸면 터미널의 qakit과 AI 스킬이 이 앱 안 도구를 씁니다."
            a.addButton(withTitle: "바꾸기")
            a.addButton(withTitle: "취소")
            if a.runModal() != .alertFirstButtonReturn { return }
        }
        working = true
        state.installLinks { out in
            working = false
            output = out.trimmingCharacters(in: .whitespacesAndNewlines)
        }
    }

    private func icon(_ s: AppState.Link.State) -> String {
        switch s { case .app: return "checkmark.circle.fill"; case .other: return "arrow.triangle.branch"; case .missing: return "circle"; case .notLink: return "exclamationmark.triangle" }
    }
    private func color(_ s: AppState.Link.State) -> Color {
        switch s { case .app: return .green; case .other: return .orange; case .missing: return .secondary; case .notLink: return .red }
    }
    private func describe(_ s: AppState.Link.State) -> String {
        switch s {
        case .app: return "이 앱"
        case .other(let p): return "다른 곳: " + (p as NSString).abbreviatingWithTildeInPath
        case .missing: return "없음"
        case .notLink: return "링크가 아닌 파일 (직접 확인)"
        }
    }
}

private struct CheckTab: View {
    @ObservedObject var state: AppState

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                if state.checking { ProgressView().controlSize(.small) }
                Text(summary).fontWeight(.medium)
                Spacer()
                Button("다시 점검") { state.runChecks() }.disabled(state.checking)
            }
            if let e = state.checkError {
                Text(e).font(.system(.caption, design: .monospaced)).foregroundColor(.red).textSelection(.enabled)
            }
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(["필수", "AI", "안드로이드"], id: \.self) { need in
                        let rows = state.checks.filter { $0.need == need }
                        if !rows.isEmpty {
                            Text(need == "필수" ? "필수 (iOS QA)" : need == "AI" ? "AI QA (쓸 때만)" : "안드로이드 (쓸 때만)")
                                .font(.subheadline.weight(.semibold)).foregroundColor(.secondary).padding(.top, 10).padding(.bottom, 4)
                            ForEach(rows) { r in CheckRow(row: r) }
                        }
                    }
                }
            }
        }
        .onAppear { if state.checks.isEmpty { state.runChecks() } }
    }

    private var summary: String {
        if state.checking { return "점검하는 중…" }
        if state.checks.isEmpty { return "아직 점검하지 않음" }
        return state.problems == 0 ? "필수 도구가 모두 있습니다" : "필수 도구 \(state.problems)개가 없습니다"
    }
}

private struct CheckRow: View {
    let row: AppState.Check

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: row.ok ? "checkmark.circle.fill" : row.need == "필수" ? "xmark.circle.fill" : "minus.circle")
                .foregroundColor(row.ok ? .green : row.need == "필수" ? .red : .secondary).frame(width: 18)
            VStack(alignment: .leading, spacing: 2) {
                Text(row.name).fontWeight(.medium)
                Text(row.detail).font(.caption).foregroundColor(.secondary).lineLimit(1).truncationMode(.middle)
                if !row.hint.isEmpty {
                    HStack(spacing: 6) {
                        Text(row.hint).font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                        Button {
                            NSPasteboard.general.clearContents()
                            NSPasteboard.general.setString(row.hint, forType: .string)
                        } label: { Image(systemName: "doc.on.doc") }.buttonStyle(.borderless).help("복사")
                    }
                }
            }
            Spacer()
        }
        .padding(.vertical, 6)
    }
}
