// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "owner-signer",
    platforms: [.macOS(.v13)],
    targets: [
        .executableTarget(
            name: "owner-signer",
            linkerSettings: [
                .linkedFramework("CryptoKit"),
                .linkedFramework("LocalAuthentication"),
                .linkedFramework("Security"),
            ]
        ),
    ]
)
