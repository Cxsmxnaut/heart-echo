// swift-tools-version: 6.0
import PackageDescription
let package = Package(
    name: "ChestBPMCareIntegration",
    platforms: [.macOS(.v13), .iOS(.v17)],
    products: [.library(name: "ChestBPMCare", targets: ["ChestBPMCare"]), .executable(name: "CareHandoffExample", targets: ["CareHandoffExample"])],
    targets: [.target(name: "ChestBPMCare"), .executableTarget(name: "CareHandoffExample", dependencies: ["ChestBPMCare"]), .testTarget(name: "ChestBPMCareTests", dependencies: ["ChestBPMCare"])]
)
