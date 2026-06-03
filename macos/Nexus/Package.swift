// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "Nexus",
    platforms: [.macOS(.v13)],   // .v13 = SMAppService era; we use launchd, but 13+ is fine
    targets: [
        .target(name: "NexusCore"),
        .executableTarget(
            name: "Nexus",
            dependencies: ["NexusCore"]
        ),
        .testTarget(
            name: "NexusCoreTests",
            dependencies: ["NexusCore"]
        ),
    ]
)
