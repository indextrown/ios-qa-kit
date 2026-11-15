// simtouch — 시뮬레이터 화면에 터치 신호를 직접 넣는다 (손가락처럼, 좌표로). qakit AI QA 직접 터치 모드 (docs/PLAN.md "AI QA 직접 터치").
//
// 계속 떠 있으면서 stdin으로 한 줄씩 명령을 받고, stdout으로 한 줄씩 답한다. 시작이 준비되면 "ready <ms>".
//   tap x y [누르는ms]         · 기본 60ms (UISwitch는 아주 짧은 탭을 무시)
//   press x y 초               · 길게 누르기
//   swipe x1 y1 x2 y2 초        · 끌기·쓸기 (중간 12번)
//   down x y · move x y · up x y
//   ping
// 좌표는 화면 대비 0~1. 답: "ok <명령> <ms>" 또는 "err <이유>". stdin이 닫히면 끝난다.
//   simtouch <udid> --once tap 0.5 0.5     · 한 번만 (확인용)
//
// 경로: SimulatorKit(비공개) SimDeviceLegacyHIDClient + IOKit 디지타이저 손가락 이벤트 → IndigoHIDMessageForTrackpadEventFromHIDEventRef,
// 메시지 0x6c(·0x10c)에 경로 표시 UInt32(0x32). 디지타이저 함수가 없으면 IndigoHIDMessageForMouseNSEvent.
// 주의: XCUITest가 켠 앱은 자동화 모드라 이 신호를 무시한다 — 앱은 simctl로 켜고 실행기는 붙기만 할 것.
// 비공개 API라 Xcode가 바뀌면 깨질 수 있다 → 시작에 실패하면 0이 아닌 코드로 끝나고, qakit은 XCUITest 탭으로 돌아간다.

import Foundation
import CoreGraphics

setvbuf(stdout, nil, _IOLBF, 0)
func die(_ m: String, _ c: Int32 = 2) -> Never { FileHandle.standardError.write("simtouch: \(m)\n".data(using: .utf8)!); exit(c) }
let started = Date()
var argv = Array(CommandLine.arguments.dropFirst())
guard let udid = argv.first, !udid.hasPrefix("-") else { die("사용: simtouch <udid> [--once <명령>]", 64) }
argv.removeFirst()
let once: [String]? = argv.first == "--once" ? Array(argv.dropFirst()) : nil

// ── SimulatorKit·기기 ──
func developerDir() -> String {
    if let d = ProcessInfo.processInfo.environment["DEVELOPER_DIR"], !d.isEmpty { return d }
    let p = Process(); p.executableURL = URL(fileURLWithPath: "/usr/bin/xcode-select"); p.arguments = ["-p"]
    let pipe = Pipe(); p.standardOutput = pipe
    try? p.run(); p.waitUntilExit()
    return String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
}
let dev = developerDir()
guard dlopen("/Library/Developer/PrivateFrameworks/CoreSimulator.framework/CoreSimulator", RTLD_NOW) != nil else { die("CoreSimulator를 열 수 없음") }
let kitPaths = [URL(fileURLWithPath: dev).deletingLastPathComponent().appendingPathComponent("SharedFrameworks/SimulatorKit.framework/SimulatorKit").path,
                dev + "/Library/PrivateFrameworks/SimulatorKit.framework/SimulatorKit"]   // Xcode 27 · 이전
guard let kitPath = kitPaths.first(where: { FileManager.default.fileExists(atPath: $0) }), let kit = dlopen(kitPath, RTLD_NOW | RTLD_GLOBAL)
else { die("SimulatorKit을 찾지 못함 (\(kitPaths.joined(separator: ", ")))") }

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
      let ctx = callWithError(ctxClass, "sharedServiceContextForDeveloperDir:error:", dev as NSString),
      let set = callWithError(ctx, "defaultDeviceSetWithError:", nil) as? NSObject else { die("기기 목록을 읽지 못함") }
guard let device = ((set.value(forKey: "devices") as? [NSObject]) ?? [])
        .first(where: { ($0.value(forKey: "UDID") as? NSUUID)?.uuidString == udid.uppercased() }) else { die("기기 없음: \(udid)") }

// ── 터치 연결 ──
guard let hidClass = NSClassFromString("_TtC12SimulatorKit24SimDeviceLegacyHIDClient") else { die("SimDeviceLegacyHIDClient 없음") }
typealias AllocFn = @convention(c) (AnyClass, Selector) -> Unmanaged<NSObject>
let allocSel = NSSelectorFromString("alloc")
let allocated = unsafeBitCast(class_getMethodImplementation(object_getClass(hidClass), allocSel)!, to: AllocFn.self)(hidClass, allocSel).takeRetainedValue()
typealias InitFn = @convention(c) (NSObject, Selector, NSObject, UnsafeMutablePointer<NSError?>) -> Unmanaged<NSObject>?
let initSel = NSSelectorFromString("initWithDevice:error:")
var initErr: NSError?
guard let client = unsafeBitCast(class_getMethodImplementation(type(of: allocated), initSel)!, to: InitFn.self)(allocated, initSel, device, &initErr)?
        .takeUnretainedValue() else { die("터치 연결 실패: \(initErr?.localizedDescription ?? "")") }
typealias SendFn = @convention(c) (NSObject, Selector, UnsafeMutableRawPointer, Bool, AnyObject?, AnyObject?) -> Void
let sendSel = NSSelectorFromString("sendWithMessage:freeWhenDone:completionQueue:completion:")
let sendMsg = unsafeBitCast(class_getMethodImplementation(type(of: client), sendSel)!, to: SendFn.self)

// 디지타이저 (IOKit 손가락 이벤트) — 없으면 마우스 방식
let iokit = dlopen("/System/Library/Frameworks/IOKit.framework/IOKit", RTLD_NOW | RTLD_GLOBAL)
typealias DigiFn = @convention(c) (OpaquePointer?, UInt64, UInt32, UInt32, UInt32, UInt32, UInt32, Double, Double, Double, Double, Double, UInt32, UInt32, UInt32) -> OpaquePointer?
typealias FingerFn = @convention(c) (OpaquePointer?, UInt64, UInt32, UInt32, UInt32, Double, Double, Double, Double, Double, UInt32, UInt32, UInt32) -> OpaquePointer?
typealias AppendFn = @convention(c) (OpaquePointer, OpaquePointer, UInt32) -> Void
typealias WrapFn = @convention(c) (OpaquePointer) -> UnsafeMutableRawPointer?
typealias MouseFn = @convention(c) (UnsafeMutablePointer<CGPoint>, UnsafeMutablePointer<CGPoint>?, UInt32, UInt, CGSize, UInt32) -> UnsafeMutableRawPointer?
let mkDigi = dlsym(iokit, "IOHIDEventCreateDigitizerEvent").map { unsafeBitCast($0, to: DigiFn.self) }
let mkFinger = dlsym(iokit, "IOHIDEventCreateDigitizerFingerEvent").map { unsafeBitCast($0, to: FingerFn.self) }
let appendEv = dlsym(iokit, "IOHIDEventAppendEvent").map { unsafeBitCast($0, to: AppendFn.self) }
let wrapTrackpad = dlsym(kit, "IndigoHIDMessageForTrackpadEventFromHIDEventRef").map { unsafeBitCast($0, to: WrapFn.self) }
let mouseMsg = dlsym(kit, "IndigoHIDMessageForMouseNSEvent").map { unsafeBitCast($0, to: MouseFn.self) }
let digitizer = mkDigi != nil && mkFinger != nil && appendEv != nil && wrapTrackpad != nil
guard digitizer || mouseMsg != nil else { die("터치 메시지 함수를 찾지 못함") }

enum Phase { case down, move, up }

/// 손가락 하나의 한 순간을 보낸다. 실패하면 이유
@discardableResult
func send(_ x: Double, _ y: Double, _ phase: Phase) -> String? {
    guard (0...1).contains(x), (0...1).contains(y) else { return "좌표는 0~1 (\(x), \(y))" }
    if digitizer, let mkDigi, let mkFinger, let appendEv, let wrapTrackpad {
        let ts = mach_absolute_time()
        let mask: UInt32 = phase == .up ? 0x06 : 0x07   // Touch|Position (+Range)
        let contact: UInt32 = phase == .up ? 0 : 1
        guard let parent = mkDigi(nil, ts, 2, 0, 1, mask, 0, x, y, 0, 0, 0, contact, contact, 0),
              let finger = mkFinger(nil, ts, 1, 1, mask, x, y, 0, 0, 0, contact, contact, 0) else { return "손가락 이벤트를 만들지 못함" }
        appendEv(parent, finger, 0)
        guard let msg = wrapTrackpad(parent) else { return "터치 메시지를 만들지 못함" }
        msg.storeBytes(of: UInt32(0x32), toByteOffset: 0x6c, as: UInt32.self)   // 경로 표시: 디지타이저로 (없으면 모든 터치가 무시됨)
        if malloc_size(msg) >= 0x110 { msg.storeBytes(of: UInt32(0x32), toByteOffset: 0x10c, as: UInt32.self) }
        sendMsg(client, sendSel, msg, true, nil, nil)
        return nil
    }
    var p = CGPoint(x: x, y: y)
    let type: UInt = phase == .down ? 1 : phase == .up ? 2 : 6
    guard let msg = mouseMsg!(&p, nil, 0x32, type, CGSize(width: 1, height: 1), 0) else { return "터치 메시지를 만들지 못함" }
    sendMsg(client, sendSel, msg, true, nil, nil)
    return nil
}

func wait(_ sec: Double) { RunLoop.current.run(until: Date().addingTimeInterval(max(0, sec))) }   // 기다리는 동안 실행 루프를 돌린다

/// 명령 한 줄 → 답 한 줄
func handle(_ line: String) -> String {
    let parts = line.split(separator: " ").map(String.init)
    guard let cmd = parts.first else { return "err 빈 명령" }
    let n = parts.dropFirst().compactMap(Double.init)
    let t = Date()
    var err: String?
    switch cmd {
    case "ping": break
    case "tap" where n.count >= 2:
        err = send(n[0], n[1], .down)
        if err == nil { wait((n.count >= 3 ? n[2] : 60) / 1000); err = send(n[0], n[1], .up) }
    case "press" where n.count >= 3:
        err = send(n[0], n[1], .down)
        if err == nil { wait(n[2]); err = send(n[0], n[1], .up) }
    case "swipe" where n.count >= 5:
        let steps = 12
        err = send(n[0], n[1], .down)
        for i in 1...steps where err == nil {
            wait(n[4] / Double(steps))
            let f = Double(i) / Double(steps)
            err = send(n[0] + (n[2] - n[0]) * f, n[1] + (n[3] - n[1]) * f, .move)
        }
        if err == nil { err = send(n[2], n[3], .up) }
    case "down" where n.count >= 2: err = send(n[0], n[1], .down)
    case "move" where n.count >= 2: err = send(n[0], n[1], .move)
    case "up" where n.count >= 2: err = send(n[0], n[1], .up)
    default: return "err 모르는 명령 또는 인자 부족: \(line)"
    }
    if let err { return "err \(err)" }
    wait(0.02)   // 보낸 메시지가 나가도록
    return "ok \(cmd) \(Int(Date().timeIntervalSince(t) * 1000))"
}

// 연결 직후의 첫 신호가 버려지지 않게 잠깐 (측정: 연결 뒤 바로 보낸 입력은 무시될 수 있음)
wait(0.25)
if let once {
    let r = handle(once.joined(separator: " "))
    wait(0.25)
    print(r)
    exit(r.hasPrefix("ok") ? 0 : 1)
}
print("ready \(Int(Date().timeIntervalSince(started) * 1000)) \(digitizer ? "digitizer" : "mouse")")
while let line = readLine() {
    let l = line.trimmingCharacters(in: .whitespaces)
    if l.isEmpty { continue }
    print(handle(l))
}
