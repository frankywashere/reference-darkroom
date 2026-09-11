import Cocoa
import WebKit

private let editorURL = URL(string: "http://127.0.0.1:8765")!

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKScriptMessageHandler {
    private var window: NSWindow!
    private var webView: WKWebView!
    private var backend: Process?
    private var launchAttempts = 0

    func applicationDidFinishLaunching(_ notification: Notification) {
        buildMenu()
        buildWindow()
        showStartupPage("Starting the photo engine…")
        checkExistingBackend()
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }

    func applicationWillTerminate(_ notification: Notification) {
        if let process = backend, process.isRunning {
            process.terminate()
            process.waitUntilExit()
        }
    }

    private func buildWindow() {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()
        configuration.userContentController.add(self, name: "chooseProjectPath")
        webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = self
        webView.setValue(false, forKey: "drawsBackground")

        let visibleFrame = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        let width = min(1500, max(1040, visibleFrame.width * 0.92))
        let height = min(980, max(700, visibleFrame.height * 0.92))
        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: width, height: height),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.title = "Reference Darkroom"
        window.titlebarAppearsTransparent = true
        window.isMovableByWindowBackground = true
        window.backgroundColor = NSColor(calibratedWhite: 0.06, alpha: 1)
        window.contentView = webView
        window.center()
        window.setFrameAutosaveName("ReferenceDarkroomMainWindow")
        window.makeKeyAndOrderFront(nil)
    }

    private func buildMenu() {
        let mainMenu = NSMenu()
        let appItem = NSMenuItem()
        mainMenu.addItem(appItem)
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "About Reference Darkroom", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Quit Reference Darkroom", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu

        let viewItem = NSMenuItem()
        mainMenu.addItem(viewItem)
        let viewMenu = NSMenu(title: "View")
        let reload = NSMenuItem(title: "Reload Editor", action: #selector(reloadEditor), keyEquivalent: "r")
        reload.target = self
        viewMenu.addItem(reload)
        viewMenu.addItem(.separator())
        viewMenu.addItem(withTitle: "Enter Full Screen", action: #selector(NSWindow.toggleFullScreen(_:)), keyEquivalent: "f")
        viewItem.submenu = viewMenu
        NSApp.mainMenu = mainMenu
    }

    @objc private func reloadEditor() {
        webView.reload()
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.frameInfo.isMainFrame,
              message.frameInfo.securityOrigin.host == "127.0.0.1",
              message.frameInfo.securityOrigin.port == 8765,
              let body = message.body as? [String: String],
              let requestID = body["id"] else { return }
        let picker = NSOpenPanel()
        picker.canChooseDirectories = body["kind"] == "folder"
        picker.canChooseFiles = !picker.canChooseDirectories
        picker.allowsMultipleSelection = false
        picker.canCreateDirectories = picker.canChooseDirectories
        picker.title = picker.canChooseDirectories ? "Choose folder" : "Choose a Reference Darkroom catalog"
        picker.beginSheetModal(for: window) { [weak self] response in
            let result: [String: Any] = ["id": requestID, "path": response == .OK ? (picker.url?.path as Any? ?? NSNull()) : NSNull()]
            if let data = try? JSONSerialization.data(withJSONObject: result), let json = String(data: data, encoding: .utf8) {
                self?.webView.evaluateJavaScript("window.dispatchEvent(new CustomEvent('darkroomPathChosen', {detail: \(json)}))")
            }
        }
    }

    private var projectRoot: URL {
        if let override = ProcessInfo.processInfo.environment["REFERENCE_DARKROOM_ROOT"], !override.isEmpty {
            return URL(fileURLWithPath: override, isDirectory: true)
        }
        return Bundle.main.bundleURL.deletingLastPathComponent()
    }

    private func checkExistingBackend() {
        var request = URLRequest(url: editorURL.appendingPathComponent("api/config"))
        request.timeoutInterval = 0.8
        URLSession.shared.dataTask(with: request) { [weak self] _, response, _ in
            let healthy = (response as? HTTPURLResponse)?.statusCode == 200
            DispatchQueue.main.async {
                guard let self else { return }
                if healthy {
                    self.loadEditor()
                } else {
                    self.startBackend()
                }
            }
        }.resume()
    }

    private func startBackend() {
        guard backend == nil else {
            waitForBackend()
            return
        }

        let editorDirectory = projectRoot.appendingPathComponent("photo_editor", isDirectory: true)
        let appScript = editorDirectory.appendingPathComponent("app.py")
        guard FileManager.default.fileExists(atPath: appScript.path) else {
            showFailure("The editor source could not be found at:\n\(appScript.path)\n\nKeep “Reference Darkroom.app” beside the photo_editor folder.")
            return
        }

        let pythonCandidates = [
            "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3",
            "/opt/homebrew/bin/python3",
            "/usr/local/bin/python3",
            "/usr/bin/python3"
        ]
        guard let python = pythonCandidates.first(where: { FileManager.default.isExecutableFile(atPath: $0) }) else {
            showFailure("Python 3 could not be found. Reinstall Python or rebuild the app with an available runtime.")
            return
        }

        let logs = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Logs/Reference Darkroom", isDirectory: true)
        try? FileManager.default.createDirectory(at: logs, withIntermediateDirectories: true)
        let logFile = logs.appendingPathComponent("server.log")
        FileManager.default.createFile(atPath: logFile.path, contents: nil)
        let logHandle = try? FileHandle(forWritingTo: logFile)

        let process = Process()
        process.executableURL = URL(fileURLWithPath: python)
        process.arguments = [appScript.path]
        process.currentDirectoryURL = editorDirectory
        process.environment = ProcessInfo.processInfo.environment.merging([
            "PYTHONUNBUFFERED": "1",
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
        ]) { _, new in new }
        process.standardOutput = logHandle
        process.standardError = logHandle
        process.terminationHandler = { [weak self] process in
            DispatchQueue.main.async {
                guard let self, NSApp.isRunning, process.terminationStatus != 0 else { return }
                self.showFailure("The photo engine stopped unexpectedly.\n\nLog: \(logFile.path)")
            }
        }

        do {
            try process.run()
            backend = process
            waitForBackend()
        } catch {
            showFailure("The photo engine could not start:\n\(error.localizedDescription)\n\nLog: \(logFile.path)")
        }
    }

    private func waitForBackend() {
        launchAttempts += 1
        guard launchAttempts <= 80 else {
            showFailure("The photo engine did not become ready.\n\nCheck ~/Library/Logs/Reference Darkroom/server.log")
            return
        }
        var request = URLRequest(url: editorURL.appendingPathComponent("api/config"))
        request.timeoutInterval = 0.5
        URLSession.shared.dataTask(with: request) { [weak self] _, response, _ in
            let healthy = (response as? HTTPURLResponse)?.statusCode == 200
            DispatchQueue.main.asyncAfter(deadline: .now() + (healthy ? 0 : 0.15)) {
                guard let self else { return }
                if healthy { self.loadEditor() } else { self.waitForBackend() }
            }
        }.resume()
    }

    private func loadEditor() {
        launchAttempts = 0
        webView.load(URLRequest(url: editorURL))
    }

    private func showStartupPage(_ message: String) {
        let html = """
        <!doctype html><meta name="color-scheme" content="dark">
        <style>body{margin:0;background:#101214;color:#e8e4dc;font:14px -apple-system;display:grid;place-items:center;height:100vh}.box{text-align:center}.mark{margin:auto;width:58px;height:58px;border:1px solid #d6975f;color:#d6975f;display:grid;place-items:center;font:700 16px Georgia;letter-spacing:.1em}h1{font-size:18px;margin:18px 0 6px}p{color:#92969a}</style>
        <div class="box"><div class="mark">RD</div><h1>Reference Darkroom</h1><p>\(message)</p></div>
        """
        webView.loadHTMLString(html, baseURL: nil)
    }

    private func showFailure(_ message: String) {
        let escaped = message
            .replacingOccurrences(of: "&", with: "&amp;")
            .replacingOccurrences(of: "<", with: "&lt;")
            .replacingOccurrences(of: ">", with: "&gt;")
            .replacingOccurrences(of: "\n", with: "<br>")
        let html = """
        <!doctype html><meta name="color-scheme" content="dark">
        <style>body{margin:0;background:#101214;color:#e8e4dc;font:14px -apple-system;display:grid;place-items:center;height:100vh}.box{max-width:650px;padding:40px;text-align:center}.mark{color:#e07a67;font-size:32px}h1{font-size:20px}p{color:#c1b9b2;line-height:1.55}</style>
        <div class="box"><div class="mark">!</div><h1>Reference Darkroom could not open</h1><p>\(escaped)</p></div>
        """
        webView.loadHTMLString(html, baseURL: nil)
    }
}

@main
struct ReferenceDarkroomMain {
    private static let delegate = AppDelegate()

    static func main() {
        let app = NSApplication.shared
        app.setActivationPolicy(.regular)
        app.delegate = delegate
        app.run()
    }
}
