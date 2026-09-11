import Foundation
import Vision

struct ScoreRow {
    let file: String
    let aesthetic: Float
    let utility: Bool
    let faceCount: Int
    let bestFaceQuality: Float
    let largestFaceArea: Float
}

guard CommandLine.arguments.count == 2 || CommandLine.arguments.count == 3 else {
    FileHandle.standardError.write(Data("usage: vision_score <preview-directory> [output-tsv]\n".utf8))
    exit(2)
}

let previewDirectory = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
let files = try FileManager.default.contentsOfDirectory(
    at: previewDirectory,
    includingPropertiesForKeys: nil,
    options: [.skipsHiddenFiles]
).filter { ["jpg", "jpeg"].contains($0.pathExtension.lowercased()) }
 .sorted { $0.lastPathComponent < $1.lastPathComponent }

var outputLines = ["file\taesthetic\tutility\tface_count\tbest_face_quality\tlargest_face_area"]

for (index, file) in files.enumerated() {
    autoreleasepool {
        do {
            let aestheticsRequest = VNCalculateImageAestheticsScoresRequest()
            let faceQualityRequest = VNDetectFaceCaptureQualityRequest()
            let handler = VNImageRequestHandler(url: file, options: [:])
            try handler.perform([aestheticsRequest, faceQualityRequest])

            let aesthetics = aestheticsRequest.results?.first
            let faces = faceQualityRequest.results ?? []
            let bestFace = faces.compactMap { $0.faceCaptureQuality }.max() ?? -1
            let largestFaceArea = faces.map { Float($0.boundingBox.width * $0.boundingBox.height) }.max() ?? 0
            let row = ScoreRow(
                file: file.lastPathComponent,
                aesthetic: aesthetics?.overallScore ?? -1,
                utility: aesthetics?.isUtility ?? true,
                faceCount: faces.count,
                bestFaceQuality: bestFace,
                largestFaceArea: largestFaceArea
            )
            outputLines.append(String(format: "%@\t%.6f\t%d\t%d\t%.6f\t%.6f",
                                      row.file,
                                      row.aesthetic,
                                      row.utility ? 1 : 0,
                                      row.faceCount,
                                      row.bestFaceQuality,
                                      row.largestFaceArea))
        } catch {
            FileHandle.standardError.write(Data("warning: \(file.lastPathComponent): \(error)\n".utf8))
            outputLines.append("\(file.lastPathComponent)\t-1\t1\t0\t-1\t0")
        }
    }

    if (index + 1) % 50 == 0 || index + 1 == files.count {
        FileHandle.standardError.write(Data("scored \(index + 1)/\(files.count)\n".utf8))
    }
}

let output = outputLines.joined(separator: "\n") + "\n"
if CommandLine.arguments.count == 3 {
    try Data(output.utf8).write(
        to: URL(fileURLWithPath: CommandLine.arguments[2]),
        options: .atomic
    )
} else {
    print(output, terminator: "")
}
