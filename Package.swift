// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "QAKit",
    platforms: [.iOS(.v17)],
    products: [
        .library(name: "QAKit", targets: ["QAKit"]),
    ],
    targets: [
        .target(
            name: "QAKit",
            path: "Sources/QAKit",
            linkerSettings: [.linkedFramework("XCTest")]
        ),
    ]
)
