import AppKit
let directory = CommandLine.arguments[1]
let image = NSImage(size: NSSize(width: 1024, height: 1024))
image.lockFocus()
NSColor(calibratedRed: 0.96, green: 0.85, blue: 0.46, alpha: 1).setFill()
NSBezierPath(roundedRect: NSRect(x: 70, y: 70, width: 884, height: 884), xRadius: 198, yRadius: 198).fill()
NSColor(calibratedRed: 0.16, green: 0.23, blue: 0.18, alpha: 1).setStroke()
let arrows = NSBezierPath()
arrows.lineWidth = 60
arrows.lineCapStyle = .round
arrows.lineJoinStyle = .round
arrows.move(to: NSPoint(x: 365, y: 295)); arrows.line(to: NSPoint(x: 365, y: 720))
arrows.move(to: NSPoint(x: 240, y: 595)); arrows.line(to: NSPoint(x: 365, y: 720)); arrows.line(to: NSPoint(x: 490, y: 595))
arrows.move(to: NSPoint(x: 660, y: 730)); arrows.line(to: NSPoint(x: 660, y: 305))
arrows.move(to: NSPoint(x: 535, y: 430)); arrows.line(to: NSPoint(x: 660, y: 305)); arrows.line(to: NSPoint(x: 785, y: 430))
arrows.stroke()
image.unlockFocus()
try FileManager.default.createDirectory(atPath: directory, withIntermediateDirectories: true)
for size in [16,32,128,256,512] {
    for scale in [1,2] {
        let pixels = size * scale
        let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: pixels, pixelsHigh: pixels, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
        image.draw(in: NSRect(x: 0, y: 0, width: pixels, height: pixels))
        NSGraphicsContext.restoreGraphicsState()
        let name = "icon_\(size)x\(size)" + (scale == 2 ? "@2x" : "") + ".png"
        try rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: directory).appendingPathComponent(name))
    }
}
