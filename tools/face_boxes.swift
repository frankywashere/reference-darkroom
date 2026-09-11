import Foundation
import Vision
import ImageIO

guard CommandLine.arguments.count >= 2 else {
    FileHandle.standardError.write(Data("usage: face_boxes <image>...\n".utf8))
    exit(2)
}

for path in CommandLine.arguments.dropFirst() {
    let url = URL(fileURLWithPath: path)
    guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
          let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
          let width = properties[kCGImagePropertyPixelWidth] as? Int,
          let height = properties[kCGImagePropertyPixelHeight] as? Int else {
        print("\(url.lastPathComponent)\terror=metadata")
        continue
    }

    do {
        let request = VNDetectFaceRectanglesRequest()
        try VNImageRequestHandler(url: url, options: [:]).perform([request])
        let faces = (request.results ?? []).sorted {
            ($0.boundingBox.width * $0.boundingBox.height) > ($1.boundingBox.width * $1.boundingBox.height)
        }
        if let face = faces.first {
            let b = face.boundingBox
            let x = Int((b.minX * CGFloat(width)).rounded())
            let y = Int(((1.0 - b.maxY) * CGFloat(height)).rounded())
            let w = Int((b.width * CGFloat(width)).rounded())
            let h = Int((b.height * CGFloat(height)).rounded())
            print("\(url.lastPathComponent)\t\(width)x\(height)\tx=\(x) y=\(y) w=\(w) h=\(h)")
        } else {
            print("\(url.lastPathComponent)\t\(width)x\(height)\tno-face")
        }
    } catch {
        print("\(url.lastPathComponent)\terror=\(error)")
    }
}
