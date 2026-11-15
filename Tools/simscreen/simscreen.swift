// simscreen — 시뮬레이터 화면을 창·권한 없이 바로 읽어 JPEG 프레임으로 내보낸다 (qakit ui 라이브 화면).
//
// 시뮬레이터는 화면을 IOSurface(공유 메모리)에 그린다. CoreSimulator(비공개)로 기기의 화면 포트를 찾아
// 그 IOSurface를 잡고, 바뀔 때마다(seed가 달라질 때) 줄여서 JPEG로 내보낸다.
// 비공개 API라 Xcode가 바뀌면 깨질 수 있다 → 실패하면 0이 아닌 코드로 끝나고, qakit은 스크린샷 방식으로 돌아간다.
//
// 사용: simscreen <udid> [--fps 20] [--width 600] [--quality 0.7] [--once out.jpg]
// 출력(stdout): [4바이트 big-endian 길이][JPEG] 반복. 준비되면 stderr에 "ready <w>x<h>".

import Foundation
import IOSurface
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers

func die(_ msg: String, _ code: Int32 = 2) -> Never { FileHandle.standardError.write("simscreen: \(msg)\n".data(using: .utf8)!); exit(code) }

var args = Array(CommandLine.arguments.dropFirst())
guard let udid = args.first, !udid.hasPrefix("-") else { die("사용: simscreen <udid> [--fps N] [--width N] [--quality Q] [--once out.jpg]", 64) }
args.removeFirst()
var fps = 20.0, width = 600, quality = 0.7, once: String? = nil
while !args.isEmpty {
    let k = args.removeFirst(); let v = args.isEmpty ? "" : args.removeFirst()
    switch k {
    case "--fps": fps = max(1, min(60, Double(v) ?? fps))
    case "--width": width = max(100, Int(v) ?? width)
    case "--quality": quality = max(0.1, min(1, Double(v) ?? quality))
    case "--once": once = v
    default: die("모르는 인자: \(k)", 64)
    }
}

// ── CoreSimulator: 기기 찾기 ──
guard dlopen("/Library/Developer/PrivateFrameworks/CoreSimulator.framework/CoreSimulator", RTLD_NOW) != nil else { die("CoreSimulator를 열 수 없음") }

func developerDir() -> String {
    if let d = ProcessInfo.processInfo.environment["DEVELOPER_DIR"], !d.isEmpty { return d }
    let p = Process(); p.executableURL = URL(fileURLWithPath: "/usr/bin/xcode-select"); p.arguments = ["-p"]
    let pipe = Pipe(); p.standardOutput = pipe
    try? p.run(); p.waitUntilExit()
    return String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
}

/// -(id)sel:(id)arg error:(NSError**) 꼴 호출
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

guard let ctxClass = NSClassFromString("SimServiceContext") else { die("SimServiceContext 없음") }
guard let ctx = callWithError(ctxClass, "sharedServiceContextForDeveloperDir:error:", developerDir() as NSString) else { die("서비스 연결 실패") }
guard let set = callWithError(ctx, "defaultDeviceSetWithError:", nil) as? NSObject else { die("기기 목록 실패") }
let devices = (set.value(forKey: "devices") as? [NSObject]) ?? []
guard let device = devices.first(where: { ($0.value(forKey: "UDID") as? NSUUID)?.uuidString == udid.uppercased() }) else { die("기기 없음: \(udid)") }

// ── 화면 포트 → IOSurface ──
func displaySurface() -> IOSurface? {
    guard let io = device.perform(NSSelectorFromString("io"))?.takeUnretainedValue() as? NSObject else { return nil }
    if io.responds(to: NSSelectorFromString("updateIOPorts")) { io.perform(NSSelectorFromString("updateIOPorts")) }
    guard let ports = io.value(forKey: "ioPorts") as? [NSObject] else { return nil }
    var best: IOSurface? = nil
    for port in ports {
        guard let pid = port.perform(NSSelectorFromString("portIdentifier"))?.takeUnretainedValue() as? String,
              pid == "com.apple.framebuffer.display",
              let desc = port.perform(NSSelectorFromString("descriptor"))?.takeUnretainedValue() as? NSObject,
              desc.responds(to: NSSelectorFromString("framebufferSurface")),
              let obj = desc.perform(NSSelectorFromString("framebufferSurface"))?.takeUnretainedValue() else { continue }
        let s = unsafeBitCast(obj, to: IOSurface.self)
        if best == nil || s.width * s.height > best!.width * best!.height { best = s }   // 가장 큰 화면 = 본 화면
    }
    return best
}

// ── IOSurface → 줄인 JPEG ──
func jpeg(_ s: IOSurface) -> Data? {
    s.lock(options: .readOnly, seed: nil); defer { s.unlock(options: .readOnly, seed: nil) }
    let w = s.width, h = s.height
    guard w > 0, h > 0,
          let src = CGContext(data: s.baseAddress, width: w, height: h, bitsPerComponent: 8, bytesPerRow: s.bytesPerRow,
                              space: CGColorSpaceCreateDeviceRGB(),
                              bitmapInfo: CGImageAlphaInfo.premultipliedFirst.rawValue | CGBitmapInfo.byteOrder32Little.rawValue),
          let full = src.makeImage() else { return nil }
    let tw = min(width, w), th = Int(Double(h) * Double(tw) / Double(w))
    guard let dst = CGContext(data: nil, width: tw, height: th, bitsPerComponent: 8, bytesPerRow: 0, space: CGColorSpaceCreateDeviceRGB(),
                              bitmapInfo: CGImageAlphaInfo.noneSkipFirst.rawValue | CGBitmapInfo.byteOrder32Little.rawValue) else { return nil }
    dst.interpolationQuality = .medium
    dst.draw(full, in: CGRect(x: 0, y: 0, width: tw, height: th))
    guard let small = dst.makeImage() else { return nil }
    let out = NSMutableData()
    guard let d = CGImageDestinationCreateWithData(out, UTType.jpeg.identifier as CFString, 1, nil) else { return nil }
    CGImageDestinationAddImage(d, small, [kCGImageDestinationLossyCompressionQuality: quality] as CFDictionary)
    return CGImageDestinationFinalize(d) ? out as Data : nil
}

var surface = displaySurface()
for _ in 0..<20 where surface == nil { usleep(250_000); surface = displaySurface() }
guard var surf = surface else { die("화면 포트를 찾지 못함 (시뮬레이터가 켜져 있나요?)") }

if let once {
    guard let data = jpeg(surf) else { die("인코딩 실패") }
    try? data.write(to: URL(fileURLWithPath: once))
    print("\(surf.width)x\(surf.height) \(data.count)B")
    exit(0)
}

FileHandle.standardError.write("ready \(surf.width)x\(surf.height)\n".data(using: .utf8)!)
signal(SIGPIPE, SIG_IGN)
let out = FileHandle.standardOutput
var lastSeed: UInt32 = .max
var lastSent = Date.distantPast
let interval = 1.0 / fps
while true {
    let start = Date()
    let seed = surf.seed
    // 화면이 안 바뀌어도 2초마다 한 장 (새로 붙은 브라우저가 바로 보게)
    if seed != lastSeed || start.timeIntervalSince(lastSent) > 2 {
        if let data = jpeg(surf) {
            var n = UInt32(data.count).bigEndian
            do { try out.write(contentsOf: Data(bytes: &n, count: 4) + data) } catch { exit(0) }   // 읽는 쪽이 끝남
            lastSeed = seed; lastSent = start
        }
    }
    // 회전·기기 재시작으로 화면 포트가 바뀌면 다시 잡는다
    if Int(start.timeIntervalSince1970) % 3 == 0, let s = displaySurface(), s !== surf { surf = s; lastSeed = .max }
    let spent = Date().timeIntervalSince(start)
    if spent < interval { usleep(UInt32((interval - spent) * 1_000_000)) }
}
