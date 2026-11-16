// objc-dump — 바이너리(프레임워크·dylib)를 불러 그 안의 Objective-C 클래스·메서드·변수를 출력한다 (비공개 API 조사용, docs/reverse-engineering.md).
//
//   swift scripts/objc-dump.swift <바이너리 경로>                 # 클래스 이름 목록
//   swift scripts/objc-dump.swift <바이너리 경로> '<정규식>'      # 이름이 맞는 클래스의 메서드(+/-)·형식·변수·프로토콜
//
// 예) swift scripts/objc-dump.swift "$(xcode-select -p)/../SharedFrameworks/SimulatorKit.framework/SimulatorKit" 'LegacyHIDClient'
// 읽기만 한다. CoreSimulator를 먼저 불러 두므로 시뮬레이터 부품도 열린다. Swift 전용 API는 여기 안 보인다 → nm + swift-demangle.
import Foundation
import ObjectiveC

let args = Array(CommandLine.arguments.dropFirst())
guard let path = args.first else {
    FileHandle.standardError.write("사용: swift scripts/objc-dump.swift <바이너리> [클래스 정규식]\n".data(using: .utf8)!)
    exit(64)
}
_ = dlopen("/Library/Developer/PrivateFrameworks/CoreSimulator.framework/CoreSimulator", RTLD_NOW)
guard dlopen(path, RTLD_NOW) != nil else { print("dlopen 실패:", String(cString: dlerror())); exit(1) }
// dyld에 등록된 이름(심볼릭 링크·..을 푼 실제 경로)으로 찾는다
let real = URL(fileURLWithPath: path).resolvingSymlinksInPath().standardizedFileURL.path
var imageCount: UInt32 = 0
let images = objc_copyImageNames(&imageCount)
let image = (0..<Int(imageCount)).map { String(cString: images[$0]) }
    .first { URL(fileURLWithPath: $0).resolvingSymlinksInPath().path == real } ?? real

var count: UInt32 = 0
guard let names = objc_copyClassNamesForImage(image, &count) else { print("클래스 없음: \(image)"); exit(1) }
let classes = (0..<Int(count)).map { String(cString: names[$0]) }.sorted()
guard args.count > 1 else {
    print("\(classes.count)개 클래스")
    classes.forEach { print($0) }
    exit(0)
}
let pattern = args[1]
for name in classes where name.range(of: pattern, options: [.regularExpression, .caseInsensitive]) != nil {
    guard let cls = NSClassFromString(name) else { continue }
    let superName = class_getSuperclass(cls).map { NSStringFromClass($0) } ?? "-"
    var pc: UInt32 = 0
    let protocols = class_copyProtocolList(cls, &pc).map { list in (0..<Int(pc)).map { NSStringFromProtocol(list[$0]) } } ?? []
    print("\n## \(name) : \(superName)\(protocols.isEmpty ? "" : " <" + protocols.joined(separator: ", ") + ">")")
    let owners: [(AnyClass, String)] = [(object_getClass(cls)!, "+"), (cls, "-")]
    for pair in owners {
        let owner: AnyClass = pair.0, mark = pair.1
        var mc: UInt32 = 0
        guard let methods = class_copyMethodList(owner, &mc) else { continue }
        for i in 0..<Int(mc) {
            let m = methods[i]
            let types = method_getTypeEncoding(m).map { String(cString: $0) } ?? ""
            print("  \(mark)\(NSStringFromSelector(method_getName(m)))   \(types)")
        }
        free(methods)
    }
    var ic: UInt32 = 0
    if let ivars = class_copyIvarList(cls, &ic) {
        for i in 0..<Int(ic) {
            let iv = ivars[i]
            print("  ivar \(ivar_getName(iv).map { String(cString: $0) } ?? "?") \(ivar_getTypeEncoding(iv).map { String(cString: $0) } ?? "")")
        }
        free(ivars)
    }
}
