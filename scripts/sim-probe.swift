// sim-probe — 시뮬레이터 기기의 입출력 포트와 그 비공개 프로토콜(메서드·블록 형식)을 출력한다.
// Xcode가 바뀌어 simscreen·simtouch가 안 될 때, 지금 Xcode의 이름·형식을 확인하는 용도 (docs/private-apis.md).
//
//   swift scripts/sim-probe.swift <udid>              # 포트 목록 + 프로토콜 + 블록 형식
//   swift scripts/sim-probe.swift <udid> --frames 5   # + 본 화면의 프레임 콜백을 5초 동안 세기 (화면을 움직여 볼 것)
//
// 읽기만 한다 (화면·입력을 바꾸지 않음). 프레임 콜백 등록은 끝날 때 해제한다.
import Foundation
import IOSurface
import ObjectiveC

func die(_ m: String) -> Never { FileHandle.standardError.write("sim-probe: \(m)\n".data(using: .utf8)!); exit(2) }
var args = Array(CommandLine.arguments.dropFirst())
guard let udid = args.first, !udid.hasPrefix("-") else { die("사용: swift scripts/sim-probe.swift <udid> [--frames 초]") }
let frameSecs = args.firstIndex(of: "--frames").flatMap { $0 + 1 < args.count ? Double(args[$0 + 1]) : nil }

// ── 기기 찾기 (simscreen과 같은 길) ──
guard dlopen("/Library/Developer/PrivateFrameworks/CoreSimulator.framework/CoreSimulator", RTLD_NOW) != nil else { die("CoreSimulator를 열 수 없음") }
func developerDir() -> String {
    if let d = ProcessInfo.processInfo.environment["DEVELOPER_DIR"], !d.isEmpty { return d }
    let p = Process(); p.executableURL = URL(fileURLWithPath: "/usr/bin/xcode-select"); p.arguments = ["-p"]
    let pipe = Pipe(); p.standardOutput = pipe
    try? p.run(); p.waitUntilExit()
    return String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
}
func callWithError(_ target: AnyObject, _ name: String, _ arg: AnyObject?) -> AnyObject? {
    let sel = NSSelectorFromString(name)
    guard let m = (target as? NSObject)?.method(for: sel) ?? class_getClassMethod(object_getClass(target), sel).map({ method_getImplementation($0) }) else { return nil }
    var err: NSError? = nil
    if let arg {
        typealias F = @convention(c) (AnyObject, Selector, AnyObject?, UnsafeMutablePointer<NSError?>) -> Unmanaged<AnyObject>?
        return unsafeBitCast(m, to: F.self)(target, sel, arg, &err)?.takeUnretainedValue()
    }
    typealias G = @convention(c) (AnyObject, Selector, UnsafeMutablePointer<NSError?>) -> Unmanaged<AnyObject>?
    return unsafeBitCast(m, to: G.self)(target, sel, &err)?.takeUnretainedValue()
}
guard let ctxClass = NSClassFromString("SimServiceContext"),
      let ctx = callWithError(ctxClass, "sharedServiceContextForDeveloperDir:error:", developerDir() as NSString),
      let set = callWithError(ctx, "defaultDeviceSetWithError:", nil) as? NSObject else { die("기기 목록을 읽지 못함") }
guard let device = ((set.value(forKey: "devices") as? [NSObject]) ?? [])
        .first(where: { ($0.value(forKey: "UDID") as? NSUUID)?.uuidString == udid.uppercased() }) else { die("기기 없음: \(udid)") }
print("기기: \(device.value(forKey: "name") ?? "?") \(udid) \(device.value(forKey: "stateString") ?? "")")

// ── 원격 객체(ROCK)의 프로토콜: 메서드는 클래스가 아니라 프로토콜에만 보인다. 블록 인자 형식은 확장 형식으로 ──
typealias GetEncoding = @convention(c) (Protocol, Selector, Bool, Bool) -> UnsafePointer<CChar>?
let extendedEncoding = dlsym(UnsafeMutableRawPointer(bitPattern: -2), "_protocol_getMethodTypeEncoding").map { unsafeBitCast($0, to: GetEncoding.self) }
let skip: Set<String> = ["ROCKImpersonateable", "ROCKImpersonatable", "ROCKRemoteInvocationInterface", "NSObject"]
func printProtocols(_ obj: NSObject, indent: String) {
    var seen = Set<String>()
    var cls: AnyClass? = object_getClass(obj)
    while let k = cls, k != NSObject.self {
        var n: UInt32 = 0
        if let list = class_copyProtocolList(k, &n) {
            for i in 0..<Int(n) {
                let p = list[i], name = NSStringFromProtocol(p)
                guard !skip.contains(name), seen.insert(name).inserted else { continue }
                print("\(indent)<\(name)>")
                for required in [true, false] {
                    var m: UInt32 = 0
                    guard let methods = protocol_copyMethodDescriptionList(p, required, true, &m) else { continue }
                    for j in 0..<Int(m) {
                        guard let sel = methods[j].name else { continue }
                        let enc = extendedEncoding?(p, sel, required, true).map { String(cString: $0) } ?? ""
                        print("\(indent)   \(required ? "" : "(선택) ")-\(NSStringFromSelector(sel))   \(enc)")
                    }
                    free(methods)
                }
            }
        }
        cls = class_getSuperclass(k)
    }
}

// ── 포트 ──
guard let io = device.perform(NSSelectorFromString("io"))?.takeUnretainedValue() as? NSObject else { die("io 없음 (기기가 켜져 있나요?)") }
if io.responds(to: NSSelectorFromString("updateIOPorts")) { io.perform(NSSelectorFromString("updateIOPorts")) }
let ports = (io.value(forKey: "ioPorts") as? [NSObject]) ?? []
var mainScreen: (NSObject, IOSurface)?
var printed = Set<String>()
for port in ports {
    let pid = port.perform(NSSelectorFromString("portIdentifier"))?.takeUnretainedValue() as? String ?? "?"
    guard let desc = port.perform(NSSelectorFromString("descriptor"))?.takeUnretainedValue() as? NSObject else { print("\n== \(pid) (descriptor 없음)"); continue }
    var surface = ""
    if desc.responds(to: NSSelectorFromString("framebufferSurface")),
       let obj = desc.perform(NSSelectorFromString("framebufferSurface"))?.takeUnretainedValue() {
        let s = unsafeBitCast(obj, to: IOSurface.self)
        surface = " — IOSurface \(s.width)x\(s.height) id \(IOSurfaceGetID(unsafeBitCast(s, to: IOSurfaceRef.self)))"
        if mainScreen == nil || s.width * s.height > mainScreen!.1.width * mainScreen!.1.height { mainScreen = (desc, s) }
    } else if desc.responds(to: NSSelectorFromString("framebufferSurface")) {
        surface = " — IOSurface 없음 (쓰지 않는 화면 자리)"
    }
    print("\n== \(pid)\(surface)")
    if printed.insert(pid).inserted { printProtocols(desc, indent: "   ") }   // 같은 포트가 여러 개면 프로토콜은 한 번만
}

// ── 프레임 콜백 세기 (선택) ──
guard let secs = frameSecs else { exit(0) }
guard let (screen, surface) = mainScreen else { die("본 화면을 찾지 못함") }
let sel = NSSelectorFromString("registerScreenCallbacksWithUUID:callbackQueue:frameCallback:surfacesChangedCallback:propertiesChangedCallback:")
guard screen.responds(to: sel) else { die("이 Xcode의 SimScreen에는 프레임 콜백 등록이 없음") }
let lock = NSLock()
var frames = 0, seeds = 0, surfacesChanged = 0
let onFrame: @convention(block) () -> Void = { lock.lock(); frames += 1; lock.unlock() }
let onSurfaces: @convention(block) (AnyObject?, AnyObject?) -> Void = { _, _ in lock.lock(); surfacesChanged += 1; lock.unlock() }
let onProperties: @convention(block) (AnyObject?) -> Void = { _ in }
let msgSend = dlsym(UnsafeMutableRawPointer(bitPattern: -2), "objc_msgSend")!
typealias Register = @convention(c) (AnyObject, Selector, NSUUID, DispatchQueue, AnyObject, AnyObject, AnyObject) -> Void
typealias Unregister = @convention(c) (AnyObject, Selector, NSUUID) -> Void
let id = NSUUID()
unsafeBitCast(msgSend, to: Register.self)(screen, sel, id, DispatchQueue(label: "probe.frames"), onFrame as AnyObject, onSurfaces as AnyObject, onProperties as AnyObject)
print("\n프레임 콜백 \(secs)초 세는 중… (화면을 움직여 보세요)")
let start = Date()
Thread {   // seed(화면 메모리가 바뀔 때마다 오르는 번호)도 같이 센다
    var last = surface.seed
    while Date().timeIntervalSince(start) < secs {
        let s = surface.seed
        if s != last { last = s; lock.lock(); seeds += 1; lock.unlock() }
        usleep(500)
    }
}.start()
RunLoop.main.run(until: start.addingTimeInterval(secs))   // 콜백은 메인 런루프로 들어온다 — 이걸 돌리지 않으면 0번
unsafeBitCast(msgSend, to: Unregister.self)(screen, NSSelectorFromString("unregisterScreenCallbacksWithUUID:"), id)
lock.lock()
print("프레임 콜백 \(frames)번 · seed 변화 \(seeds)번 · 화면 메모리 교체 알림 \(surfacesChanged)번 (등록 직후 1번은 정상)")
