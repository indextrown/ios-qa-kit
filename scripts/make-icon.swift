// 앱 아이콘(App/AppIcon.icns)을 그린다: 둥근 사각형 + 그라데이션 + 확인 표시(SF Symbol checkmark.seal.fill).
//   swift scripts/make-icon.swift      → App/AppIcon.icns  (아이콘을 바꿀 때만, 결과는 커밋)
import AppKit

func render(_ px: Int) -> Data {
    let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: px, pixelsHigh: px, bitsPerSample: 8, samplesPerPixel: 4,
                               hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    let s = CGFloat(px)
    // macOS 아이콘 격자: 1024 중 824 크기의 둥근 사각형 (가장자리 100 여백)
    let inset = s * 100 / 1024, side = s - inset * 2
    let rect = NSRect(x: inset, y: inset, width: side, height: side)
    let path = NSBezierPath(roundedRect: rect, xRadius: side * 0.225, yRadius: side * 0.225)
    NSGraphicsContext.current?.saveGraphicsState()
    let shadow = NSShadow()
    shadow.shadowColor = NSColor.black.withAlphaComponent(0.28)
    shadow.shadowBlurRadius = s * 0.025
    shadow.shadowOffset = NSSize(width: 0, height: -s * 0.012)
    shadow.set()
    NSColor.black.setFill()
    path.fill()
    NSGraphicsContext.current?.restoreGraphicsState()
    NSGradient(colors: [NSColor(srgbRed: 0.33, green: 0.42, blue: 1.0, alpha: 1), NSColor(srgbRed: 0.12, green: 0.20, blue: 0.62, alpha: 1)])!
        .draw(in: path, angle: -90)
    let cfg = NSImage.SymbolConfiguration(pointSize: side * 0.52, weight: .semibold)
        .applying(.init(paletteColors: [NSColor(srgbRed: 0.18, green: 0.27, blue: 0.80, alpha: 1), .white]))
    if let sym = NSImage(systemSymbolName: "checkmark.seal.fill", accessibilityDescription: nil)?.withSymbolConfiguration(cfg) {
        let sz = sym.size
        sym.draw(in: NSRect(x: (s - sz.width) / 2, y: (s - sz.height) / 2, width: sz.width, height: sz.height))
    }
    NSGraphicsContext.restoreGraphicsState()
    return rep.representation(using: .png, properties: [:])!
}

let root = URL(fileURLWithPath: CommandLine.arguments[0]).deletingLastPathComponent().deletingLastPathComponent()
let set = FileManager.default.temporaryDirectory.appendingPathComponent("AppIcon.iconset")
try? FileManager.default.removeItem(at: set)
try! FileManager.default.createDirectory(at: set, withIntermediateDirectories: true)
for base in [16, 32, 128, 256, 512] {
    try! render(base).write(to: set.appendingPathComponent("icon_\(base)x\(base).png"))
    try! render(base * 2).write(to: set.appendingPathComponent("icon_\(base)x\(base)@2x.png"))
}
let out = root.appendingPathComponent("App/AppIcon.icns")
let p = Process()
p.executableURL = URL(fileURLWithPath: "/usr/bin/iconutil")
p.arguments = ["-c", "icns", set.path, "-o", out.path]
try! p.run(); p.waitUntilExit()
print(p.terminationStatus == 0 ? "✅ \(out.path)" : "❌ iconutil 실패")
