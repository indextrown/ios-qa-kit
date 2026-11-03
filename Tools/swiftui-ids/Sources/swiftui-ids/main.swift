//
//  main.swift
//  swiftui-ids
//
//  사용법
//    swiftui-ids list <폴더>... [--exclude 이름]... [--json]     ID 목록만 (소스 수정 없음)
//    swiftui-ids insert <폴더>... --manifest <파일> [--exclude 이름]...   소스에 삽입 + manifest 기록
//    swiftui-ids restore --manifest <파일>                        manifest의 원본으로 복원
//
//  insert는 QA 워크트리에서만 쓴다. 개발 폴더에 쓰면 안 된다 (qakit이 워크트리인지 확인한다).
//

import CryptoKit
import Foundation

let excludeDirs: Set<String> = ["Pods", "Carthage", ".build", "build", "DerivedData", "SourcePackages", ".git",
                                "node_modules", "fastlane", "vendor", "Vendor", ".swiftpm", "Derived", ".tuist"]
let excludeSuffixes = ["Tests", "UITests", "Demo", "Preview Content"]

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(("swiftui-ids: " + message + "\n").data(using: .utf8)!)
    exit(1)
}

func swiftFiles(in roots: [String], extraExcludes: Set<String>) -> [String] {
    var out: [String] = []
    let fm = FileManager.default
    for root in roots {
        guard let e = fm.enumerator(atPath: root) else { fail("폴더를 열 수 없음: \(root)") }
        while let rel = e.nextObject() as? String {
            let name = (rel as NSString).lastPathComponent
            var isDir: ObjCBool = false
            let full = (root as NSString).appendingPathComponent(rel)
            fm.fileExists(atPath: full, isDirectory: &isDir)
            if isDir.boolValue {
                if excludeDirs.contains(name) || extraExcludes.contains(name) || excludeSuffixes.contains(where: { name.hasSuffix($0) }) {
                    e.skipDescendants()
                }
                continue
            }
            if name.hasSuffix(".swift") { out.append(full) }
        }
    }
    return out.sorted()
}

func sha(_ s: String) -> String {
    SHA256.hash(data: Data(s.utf8)).map { String(format: "%02x", $0) }.joined()
}

func analyze(roots: [String], extraExcludes: Set<String>) -> (ids: [Assigned], files: Int) {
    let scanner = Scanner()
    for f in swiftFiles(in: roots, extraExcludes: extraExcludes) {
        do { try scanner.scan(file: f) } catch { fail("읽기 실패: \(f): \(error)") }
    }
    var assigner = Assigner(views: scanner.views)
    return (assigner.assign(scanner.candidates), scanner.fileCount)
}

func apply(_ ids: [Assigned], manifestPath: String) {
    let byFile = Dictionary(grouping: ids, by: { $0.file })
    var files: [ManifestFile] = []
    for (path, list) in byFile.sorted(by: { $0.key < $1.key }) {
        guard let original = try? String(contentsOfFile: path, encoding: .utf8) else { fail("읽기 실패: \(path)") }
        var bytes = Array(original.utf8)
        // 뒤에서부터 끼워 넣어야 앞의 오프셋이 안 흔들린다
        for a in list.sorted(by: { $0.offset > $1.offset }) {
            guard a.offset <= bytes.count else { fail("오프셋 오류: \(path):\(a.line)") }
            bytes.insert(contentsOf: Array(a.modifier.utf8), at: a.offset)
        }
        let inserted = String(decoding: bytes, as: UTF8.self)
        do { try inserted.write(toFile: path, atomically: true, encoding: .utf8) } catch { fail("쓰기 실패: \(path): \(error)") }
        files.append(ManifestFile(path: path, original: original, insertedSHA: sha(inserted)))
    }
    let manifest = Manifest(createdAt: ISO8601DateFormatter().string(from: Date()), files: files, ids: ids)
    let enc = JSONEncoder()
    enc.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
    do { try enc.encode(manifest).write(to: URL(fileURLWithPath: manifestPath)) } catch { fail("manifest 쓰기 실패: \(error)") }
}

func restore(manifestPath: String) {
    guard let data = FileManager.default.contents(atPath: manifestPath) else { fail("manifest 없음: \(manifestPath)") }
    guard let manifest = try? JSONDecoder().decode(Manifest.self, from: data) else { fail("manifest 형식 오류") }
    var restored = 0
    for f in manifest.files {
        let current = (try? String(contentsOfFile: f.path, encoding: .utf8)) ?? ""
        if current == f.original { continue }
        if sha(current) != f.insertedSHA {
            FileHandle.standardError.write("경고: 삽입 뒤 손댄 파일을 원본으로 되돌립니다: \(f.path)\n".data(using: .utf8)!)
        }
        do { try f.original.write(toFile: f.path, atomically: true, encoding: .utf8) } catch { fail("복원 실패: \(f.path): \(error)") }
        restored += 1
    }
    try? FileManager.default.removeItem(atPath: manifestPath)
    print("복원 \(restored)개 파일, manifest 삭제")
}

// MARK: - 인자

var args = Array(CommandLine.arguments.dropFirst())
guard let command = args.first else { fail("명령이 필요합니다: list | insert | restore") }
args.removeFirst()

var roots: [String] = []
var excludes: Set<String> = []
var manifestPath: String?
var json = false
var i = 0
while i < args.count {
    switch args[i] {
    case "--exclude": i += 1; excludes.insert(args[i])
    case "--manifest": i += 1; manifestPath = args[i]
    case "--json": json = true
    default: roots.append(args[i])
    }
    i += 1
}

switch command {
case "list":
    guard !roots.isEmpty else { fail("폴더가 필요합니다") }
    let (ids, nfiles) = analyze(roots: roots, extraExcludes: excludes)
    if json {
        let enc = JSONEncoder(); enc.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
        print(String(decoding: try! enc.encode(ids), as: UTF8.self))
    } else {
        for a in ids {
            print("\(a.id)\t\(a.kind)\(a.overridable ? "\t(호출부 ID가 우선)" : "")\t\(a.file):\(a.line)")
        }
        FileHandle.standardError.write("파일 \(nfiles)개, ID \(ids.count)개\n".data(using: .utf8)!)
    }
case "insert":
    guard !roots.isEmpty else { fail("폴더가 필요합니다") }
    guard let manifestPath else { fail("--manifest <파일>이 필요합니다 (복원용)") }
    if FileManager.default.fileExists(atPath: manifestPath) {
        fail("manifest가 이미 있습니다. 먼저 restore 하세요: \(manifestPath)")
    }
    let (ids, nfiles) = analyze(roots: roots, extraExcludes: excludes)
    apply(ids, manifestPath: manifestPath)
    print("파일 \(nfiles)개 중 \(Set(ids.map(\.file)).count)개에 ID \(ids.count)개 삽입 → manifest \(manifestPath)")
case "restore":
    guard let manifestPath else { fail("--manifest <파일>이 필요합니다") }
    restore(manifestPath: manifestPath)
default:
    fail("알 수 없는 명령: \(command)")
}
