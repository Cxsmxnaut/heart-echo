import AppKit
import Foundation
import ImageIO
import UniformTypeIdentifiers
let root = URL(fileURLWithPath: CommandLine.arguments[1])
let destination = root.appendingPathComponent("HeartEchoApp/Assets.xcassets/AppIcon.appiconset")
try FileManager.default.createDirectory(at: destination, withIntermediateDirectories: true)
try JSONSerialization.data(withJSONObject: ["info": ["author": "Heart Echo", "version": 1]], options: [.prettyPrinted, .sortedKeys]).write(to: destination.deletingLastPathComponent().appendingPathComponent("Contents.json"))
let context = CGContext(data: nil, width: 1024, height: 1024, bitsPerComponent: 8, bytesPerRow: 4096, space: CGColorSpace(name: CGColorSpace.sRGB)!, bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)!
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(cgContext: context, flipped: false)
let background = NSRect(x: 0, y: 0, width: 1024, height: 1024)
NSGradient(starting: NSColor(srgbRed: 0.88, green: 0.17, blue: 0.34, alpha: 1), ending: NSColor(srgbRed: 0.69, green: 0.06, blue: 0.23, alpha: 1))!.draw(in: background, angle: -45)
let heart = NSBezierPath()
heart.move(to: NSPoint(x: 512, y: 240))
heart.curve(to: NSPoint(x: 218, y: 558), controlPoint1: NSPoint(x: 374, y: 345), controlPoint2: NSPoint(x: 218, y: 438))
heart.curve(to: NSPoint(x: 365, y: 772), controlPoint1: NSPoint(x: 218, y: 704), controlPoint2: NSPoint(x: 285, y: 772))
heart.curve(to: NSPoint(x: 512, y: 686), controlPoint1: NSPoint(x: 430, y: 772), controlPoint2: NSPoint(x: 479, y: 730))
heart.curve(to: NSPoint(x: 659, y: 772), controlPoint1: NSPoint(x: 545, y: 730), controlPoint2: NSPoint(x: 594, y: 772))
heart.curve(to: NSPoint(x: 806, y: 558), controlPoint1: NSPoint(x: 739, y: 772), controlPoint2: NSPoint(x: 806, y: 704))
heart.curve(to: NSPoint(x: 512, y: 240), controlPoint1: NSPoint(x: 806, y: 438), controlPoint2: NSPoint(x: 650, y: 345))
heart.close(); NSColor.white.setFill(); heart.fill()
NSGraphicsContext.restoreGraphicsState()
let png = CGImageDestinationCreateWithURL(destination.appendingPathComponent("AppIcon.png") as CFURL, UTType.png.identifier as CFString, 1, nil)!
CGImageDestinationAddImage(png, context.makeImage()!, nil)
precondition(CGImageDestinationFinalize(png))
let contents: [String: Any] = ["images": [["filename": "AppIcon.png", "idiom": "universal", "platform": "ios", "size": "1024x1024"]], "info": ["author": "Heart Echo", "version": 1]]
try JSONSerialization.data(withJSONObject: contents, options: [.prettyPrinted, .sortedKeys]).write(to: destination.appendingPathComponent("Contents.json"))
