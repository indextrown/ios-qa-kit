// simscreen — 시뮬레이터 화면을 창·권한 없이 바로 읽어 JPEG 프레임으로 내보낸다 (qakit ui 라이브 화면).
//
// 시뮬레이터는 화면을 IOSurface(공유 메모리)에 그린다. CoreSimulator(비공개)로 기기의 화면 포트를 찾아
// 그 IOSurface를 잡고, 바뀔 때마다(seed가 달라질 때) 줄여서 JPEG로 내보낸다.
// 비공개 API라 Xcode가 바뀌면 깨질 수 있다 → 실패하면 0이 아닌 코드로 끝나고, qakit은 스크린샷 방식으로 돌아간다.
//
// 사용: simscreen <udid> [--fps 20] [--width 600] [--quality 0.7] [--once out.jpg]
// 인코딩은 하드웨어 JPEG(VideoToolbox), 안 되면 CoreGraphics. SIMSCREEN_NO_HW=1이면 CoreGraphics만.
// 출력(stdout): [4바이트 big-endian 길이][JPEG] 반복. 준비되면 stderr에 "ready <w>x<h>".
//
// 사용: simscreen --encode out.mp4   (qakit mcp 문제 보고 영상)
// 입력(stdin): [8바이트 big-endian double 시각(초)][4바이트 길이][JPEG] 반복 → 그 시각대로 H.264 mp4 (화면이 바뀔 때만
// 온 장면이라 간격이 고르지 않아도 재생 속도가 맞다). 공개 API(AVFoundation)만 쓴다.

import Foundation
import IOSurface
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers
import AVFoundation
import CoreVideo
import VideoToolbox

func die(_ msg: String, _ code: Int32 = 2) -> Never { FileHandle.standardError.write("simscreen: \(msg)\n".data(using: .utf8)!); exit(code) }

var args = Array(CommandLine.arguments.dropFirst())

// ── --encode: JPEG 장면들 → mp4 ──
func decodeJPEG(_ d: Data) -> CGImage? {
    guard let src = CGImageSourceCreateWithData(d as CFData, nil) else { return nil }
    return CGImageSourceCreateImageAtIndex(src, 0, nil)
}

func encode(to path: String) -> Never {
    let data = FileHandle.standardInput.readDataToEndOfFile()
    var frames: [(Double, Data)] = []
    var i = data.startIndex
    while i + 12 <= data.endIndex {
        let t = Double(bitPattern: data[i..<i + 8].reduce(UInt64(0)) { $0 << 8 | UInt64($1) })
        let n = Int(data[i + 8..<i + 12].reduce(UInt32(0)) { $0 << 8 | UInt32($1) })
        guard i + 12 + n <= data.endIndex else { break }
        frames.append((t, data.subdata(in: i + 12..<i + 12 + n)))
        i += 12 + n
    }
    guard let first = frames.first, let img0 = decodeJPEG(first.1) else { die("장면이 없음") }
    let w = img0.width & ~1, h = img0.height & ~1   // H.264는 짝수 크기
    let url = URL(fileURLWithPath: path)
    try? FileManager.default.removeItem(at: url)
    guard let writer = try? AVAssetWriter(outputURL: url, fileType: .mp4) else { die("파일을 만들 수 없음: \(path)") }
    let input = AVAssetWriterInput(mediaType: .video, outputSettings: [
        AVVideoCodecKey: AVVideoCodecType.h264, AVVideoWidthKey: w, AVVideoHeightKey: h])
    let adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: input, sourcePixelBufferAttributes: [
        kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA,
        kCVPixelBufferWidthKey as String: w, kCVPixelBufferHeightKey as String: h])
    writer.add(input)
    guard writer.startWriting() else { die("인코딩 시작 실패: \(writer.error?.localizedDescription ?? "")") }
    writer.startSession(atSourceTime: .zero)
    let t0 = first.0
    var last = -1.0
    // 마지막 장면을 0.5초 더 보여 주도록 한 번 더 넣는다
    for (t, jpg) in frames + [(frames[frames.count - 1].0 + 0.5, frames[frames.count - 1].1)] {
        let pts = max(t - t0, last + 0.001)
        guard let img = decodeJPEG(jpg), let pool = adaptor.pixelBufferPool else { continue }
        var pb: CVPixelBuffer?
        guard CVPixelBufferPoolCreatePixelBuffer(nil, pool, &pb) == kCVReturnSuccess, let buf = pb else { continue }
        CVPixelBufferLockBaseAddress(buf, [])
        if let ctx = CGContext(data: CVPixelBufferGetBaseAddress(buf), width: w, height: h, bitsPerComponent: 8,
                               bytesPerRow: CVPixelBufferGetBytesPerRow(buf), space: CGColorSpaceCreateDeviceRGB(),
                               bitmapInfo: CGImageAlphaInfo.premultipliedFirst.rawValue | CGBitmapInfo.byteOrder32Little.rawValue) {
            ctx.draw(img, in: CGRect(x: 0, y: 0, width: w, height: h))
        }
        CVPixelBufferUnlockBaseAddress(buf, [])
        while !input.isReadyForMoreMediaData { usleep(2_000) }
        if adaptor.append(buf, withPresentationTime: CMTime(seconds: pts, preferredTimescale: 600)) { last = pts }
    }
    input.markAsFinished()
    let sem = DispatchSemaphore(value: 0)
    writer.finishWriting { sem.signal() }
    sem.wait()
    guard writer.status == .completed else { die("인코딩 실패: \(writer.error?.localizedDescription ?? "")") }
    print("\(frames.count) frames \(String(format: "%.1f", last))s")
    exit(0)
}
if args.first == "--encode" {
    guard args.count >= 2 else { die("사용: simscreen --encode out.mp4 < 장면들", 64) }
    encode(to: args[1])
}

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

// ── 하드웨어 JPEG (VideoToolbox): GPU로 줄이고(VTPixelTransfer) 미디어 엔진으로 JPEG. 900px 기준 약 7ms
//    (CoreGraphics + ImageIO는 약 24ms). 만들지 못하면 nil → 위 jpeg()로.
final class HardwareJPEG {
    let w: Int, h: Int, srcW: Int, srcH: Int
    private var session: VTCompressionSession
    private let transfer: VTPixelTransferSession
    private let small: CVPixelBuffer
    private var n: Int64 = 0

    init?(source s: IOSurface, width: Int, quality: Double) {
        srcW = s.width; srcH = s.height
        w = min(width, srcW) & ~1
        h = Int(Double(srcH) * Double(w) / Double(srcW)) & ~1
        guard w > 0, h > 0 else { return nil }
        var t: VTPixelTransferSession?
        guard VTPixelTransferSessionCreate(allocator: nil, pixelTransferSessionOut: &t) == 0, let t else { return nil }
        VTSessionSetProperty(t, key: kVTPixelTransferPropertyKey_ScalingMode, value: kVTScalingMode_Trim)
        var buf: CVPixelBuffer?
        guard CVPixelBufferCreate(nil, w, h, kCVPixelFormatType_32BGRA,
                                  [kCVPixelBufferIOSurfacePropertiesKey: [:]] as CFDictionary, &buf) == kCVReturnSuccess, let buf else { return nil }
        var sess: VTCompressionSession?
        guard VTCompressionSessionCreate(allocator: nil, width: Int32(w), height: Int32(h), codecType: kCMVideoCodecType_JPEG,
                                         encoderSpecification: nil, imageBufferAttributes: nil, compressedDataAllocator: nil,
                                         outputCallback: nil, refcon: nil, compressionSessionOut: &sess) == 0, let sess else { return nil }
        VTSessionSetProperty(sess, key: kVTCompressionPropertyKey_Quality, value: quality as CFNumber)
        VTSessionSetProperty(sess, key: kVTCompressionPropertyKey_RealTime, value: kCFBooleanTrue)
        transfer = t; small = buf; session = sess
    }

    func matches(_ s: IOSurface) -> Bool { s.width == srcW && s.height == srcH }

    func encode(_ s: IOSurface) -> Data? {
        var src: Unmanaged<CVPixelBuffer>?
        guard CVPixelBufferCreateWithIOSurface(nil, unsafeBitCast(s, to: IOSurfaceRef.self), nil, &src) == kCVReturnSuccess,
              let src = src?.takeRetainedValue(),
              VTPixelTransferSessionTransferImage(transfer, from: src, to: small) == 0 else { return nil }
        var out: Data?
        let done = DispatchSemaphore(value: 0)
        n += 1
        let st = VTCompressionSessionEncodeFrame(session, imageBuffer: small, presentationTimeStamp: CMTime(value: n, timescale: 60),
                                                 duration: .invalid, frameProperties: nil, infoFlagsOut: nil) { status, _, sample in
            defer { done.signal() }
            guard status == 0, let sample, let bb = CMSampleBufferGetDataBuffer(sample) else { return }
            let len = CMBlockBufferGetDataLength(bb)
            var d = Data(count: len)
            let ok = d.withUnsafeMutableBytes { CMBlockBufferCopyDataBytes(bb, atOffset: 0, dataLength: len, destination: $0.baseAddress!) } == 0
            if ok { out = d }
        }
        guard st == 0 else { return nil }
        done.wait()
        return out
    }
}

var hw: HardwareJPEG?
var hwFailed = ProcessInfo.processInfo.environment["SIMSCREEN_NO_HW"] != nil

/// 한 장: 하드웨어로, 안 되면 CoreGraphics로
func frame(_ s: IOSurface) -> Data? {
    if !hwFailed {
        if hw == nil || !hw!.matches(s) { hw = HardwareJPEG(source: s, width: width, quality: quality) }
        if let hw, let d = hw.encode(s), d.count > 2, d[0] == 0xFF, d[1] == 0xD8 { return d }
        hwFailed = true
        FileHandle.standardError.write("simscreen: 하드웨어 JPEG 실패 → CoreGraphics\n".data(using: .utf8)!)
    }
    return jpeg(s)
}

var surface = displaySurface()
for _ in 0..<20 where surface == nil { usleep(250_000); surface = displaySurface() }
guard var surf = surface else { die("화면 포트를 찾지 못함 (시뮬레이터가 켜져 있나요?)") }

if let once {
    guard let data = frame(surf) else { die("인코딩 실패") }
    try? data.write(to: URL(fileURLWithPath: once))
    print("\(surf.width)x\(surf.height) \(data.count)B")
    exit(0)
}

FileHandle.standardError.write("ready \(surf.width)x\(surf.height)\n".data(using: .utf8)!)
signal(SIGPIPE, SIG_IGN)
let out = FileHandle.standardOutput
var lastSeed: UInt32 = .max
var lastSent = Date.distantPast
var lastPortCheck = Date()
let interval = 1.0 / fps
while true {
    let start = Date()
    let seed = surf.seed
    // 화면이 안 바뀌어도 2초마다 한 장 (새로 붙은 브라우저가 바로 보게)
    if seed != lastSeed || start.timeIntervalSince(lastSent) > 2 {
        if let data = frame(surf) {
            var n = UInt32(data.count).bigEndian
            do { try out.write(contentsOf: Data(bytes: &n, count: 4) + data) } catch { exit(0) }   // 읽는 쪽이 끝남
            lastSeed = seed; lastSent = start
        }
    }
    // 회전·기기 재시작으로 화면 포트가 바뀌면 다시 잡는다
    //  (3초에 한 번 — 포트 찾기가 한 번에 6~10ms라 매 장 하면 그만큼 느려진다)
    if start.timeIntervalSince(lastPortCheck) > 3 {
        lastPortCheck = start
        if let s = displaySurface(), s !== surf { surf = s; lastSeed = .max }
    }
    let spent = Date().timeIntervalSince(start)
    if spent < interval { usleep(UInt32((interval - spent) * 1_000_000)) }
}
