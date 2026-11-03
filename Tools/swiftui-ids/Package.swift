// swift-tools-version:5.9
// swiftui-ids — SwiftUI 소스에 accessibilityIdentifier를 끼워 넣는 도구 (QA 워크트리 빌드 전용)
import PackageDescription

let package = Package(
    name: "swiftui-ids",
    platforms: [.macOS(.v13)],
    dependencies: [
        .package(url: "https://github.com/swiftlang/swift-syntax.git", from: "604.0.0"),
    ],
    targets: [
        .executableTarget(
            name: "swiftui-ids",
            dependencies: [
                .product(name: "SwiftSyntax", package: "swift-syntax"),
                .product(name: "SwiftParser", package: "swift-syntax"),
            ],
            path: "Sources/swiftui-ids"
        ),
    ]
)
