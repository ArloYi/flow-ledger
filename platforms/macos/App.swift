import AppKit
import WebKit

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate {
    var status: NSStatusItem!
    var window: NSWindow!
    var web: WKWebView!
    let popover = NSPopover()
    var popoverTimer: Timer?
    var outsideSince: Date?
    var openedAt = Date()
    var popupLabels: [NSTextField] = []
    var process: Process?
    var timer: Timer?
    var baseURL: URL?
    var downItem = NSMenuItem(title: "下载：等待采样", action: nil, keyEquivalent: "")
    var upItem = NSMenuItem(title: "上传：等待采样", action: nil, keyEquivalent: "")
    var todayItem = NSMenuItem(title: "今日已记录：等待采样", action: nil, keyEquivalent: "")
    var stateItem = NSMenuItem(title: "正在启动采集…", action: nil, keyEquivalent: "")
    var starting = true
    var buffer = ""
    let dataDir = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/流量手账")

    func applicationDidFinishLaunching(_ notification: Notification) {
        let running = NSRunningApplication.runningApplications(withBundleIdentifier: Bundle.main.bundleIdentifier ?? "local.arlo.network-meter")
        if let other = running.first(where: { $0.processIdentifier != ProcessInfo.processInfo.processIdentifier }) {
            if !CommandLine.arguments.contains("--background") { other.activate(options: [.activateAllWindows]) }
            NSApp.terminate(nil)
            return
        }
        status = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        status.button?.title = "⇅ 启动中"
        status.button?.font = .monospacedDigitSystemFont(ofSize: 11, weight: .medium)
        buildPopover()
        status.button?.target = self
        status.button?.action = #selector(togglePopover)
        buildWindow()
        launchCollector()
    }

    func buildPopover() {
        let controller = NSViewController()
        let view = NSView(frame: NSRect(x: 0, y: 0, width: 290, height: 325))
        let stack = NSStackView()
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 9
        stack.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(stack)
        NSLayoutConstraint.activate([stack.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 18), stack.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -18), stack.topAnchor.constraint(equalTo: view.topAnchor, constant: 16)])
        for item in [stateItem, downItem, upItem, todayItem] {
            let label = NSTextField(labelWithString: item.title)
            label.font = .monospacedDigitSystemFont(ofSize: 12, weight: .regular)
            if item === stateItem { label.textColor = .secondaryLabelColor }
            stack.addArrangedSubview(label)
            popupLabels.append(label)
        }
        let separator = NSBox(); separator.boxType = .separator
        stack.addArrangedSubview(separator)
        separator.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true
        for (title, action) in [("打开流量手账", #selector(showWindow)), ("导出分钟明细…", #selector(exportCSV)), ("打开数据文件夹", #selector(openData)), ("退出并停止记录", #selector(quit))] {
            let button = NSButton(title: title, target: self, action: action)
            button.bezelStyle = .recessed
            button.isBordered = false
            button.alignment = .left
            button.font = .systemFont(ofSize: 13)
            stack.addArrangedSubview(button)
            button.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true
            button.heightAnchor.constraint(equalToConstant: 27).isActive = true
        }
        let loginButton = NSButton(checkboxWithTitle: "登录 Mac 后自动记录", target: self, action: #selector(toggleLogin(_:)))
        loginButton.state = FileManager.default.fileExists(atPath: loginFile.path) ? .on : .off
        stack.addArrangedSubview(loginButton)
        controller.view = view
        popover.contentViewController = controller
        popover.contentSize = view.frame.size
        popover.behavior = .transient
        popover.animates = false
    }
    var loginFile: URL { FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/LaunchAgents/local.arlo.network-meter.plist") }
    @objc func toggleLogin(_ sender: NSButton) {
        do {
            if sender.state == .on {
                let config: [String: Any] = ["Label": "local.arlo.network-meter", "ProgramArguments": [Bundle.main.executableURL!.path, "--background"], "RunAtLoad": true, "LimitLoadToSessionType": "Aqua", "ProcessType": "Interactive"]
                try FileManager.default.createDirectory(at: loginFile.deletingLastPathComponent(), withIntermediateDirectories: true)
                try PropertyListSerialization.data(fromPropertyList: config, format: .xml, options: 0).write(to: loginFile, options: .atomic)
            } else if FileManager.default.fileExists(atPath: loginFile.path) {
                try FileManager.default.removeItem(at: loginFile)
            }
        } catch {
            sender.state = sender.state == .on ? .off : .on
            fail("无法修改登录启动：\(error.localizedDescription)")
        }
    }
    func refreshPopover() {
        for (label,item) in zip(popupLabels,[stateItem,downItem,upItem,todayItem]) { label.stringValue = item.title }
    }
    @objc func togglePopover() {
        if popover.isShown { popover.close(); return }
        guard let button = status.button else { return }
        refreshPopover()
        openedAt = Date()
        outsideSince = nil
        popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
        popoverTimer?.invalidate()
        popoverTimer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] timer in
            guard let self = self, self.popover.isShown else { timer.invalidate(); return }
            let point = NSEvent.mouseLocation
            let frame = self.popover.contentViewController?.view.window?.frame ?? .zero
            let buttonRect = button.window?.convertToScreen(button.convert(button.bounds, to: nil)) ?? .zero
            if frame.insetBy(dx: -5, dy: -5).contains(point) || buttonRect.insetBy(dx: -4, dy: -4).contains(point) {
                self.outsideSince = nil
            } else if Date().timeIntervalSince(self.openedAt) > 0.4 {
                if let since = self.outsideSince, Date().timeIntervalSince(since) > 0.2 { self.popover.close(); timer.invalidate() }
                else if self.outsideSince == nil { self.outsideSince = Date() }
            }
        }
    }

    func buildWindow() {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .nonPersistent()
        web = WKWebView(frame: .zero, configuration: config)
        web.navigationDelegate = self
        web.uiDelegate = self
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 920, height: 760), styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "流量手账"
        window.minSize = NSSize(width: 380, height: 540)
        window.isReleasedWhenClosed = false
        window.backgroundColor = NSColor(red: 0.965, green: 0.961, blue: 0.937, alpha: 1)
        window.setFrameAutosaveName("NetworkMeterV2")
        window.contentView = web
        window.center()
    }

    func launchCollector() {
        guard let resources = Bundle.main.resourceURL else { return }
        do { try FileManager.default.createDirectory(at: dataDir, withIntermediateDirectories: true) }
        catch { fail("无法创建数据文件夹：\(error.localizedDescription)"); return }
        let child = Process()
        child.executableURL = resources.appendingPathComponent("runtime/bin/python3")
        child.arguments = ["-B", resources.appendingPathComponent("server.py").path, "--port", "0", "--data-dir", dataDir.path, "--parent-pid", String(ProcessInfo.processInfo.processIdentifier)]
        var environment = ProcessInfo.processInfo.environment
        environment["PYTHONHOME"] = resources.appendingPathComponent("runtime").path
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PYTHONNOUSERSITE"] = "1"
        child.environment = environment
        let out = Pipe()
        child.standardOutput = out
        let errors = Pipe()
        child.standardError = errors
        errors.fileHandleForReading.readabilityHandler = { handle in
            if handle.availableData.isEmpty { handle.readabilityHandler = nil }
        }
        out.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            if data.isEmpty { handle.readabilityHandler = nil; return }
            guard let text = String(data: data, encoding: .utf8) else { return }
            DispatchQueue.main.async { self?.receive(text) }
        }
        child.terminationHandler = { [weak self] _ in
            DispatchQueue.main.async {
                guard let self = self else { return }
                self.timer?.invalidate()
                self.status?.button?.title = "⇅ 已停止"
                self.stateItem.title = "采集已停止，请退出后重新打开"
                self.refreshPopover()
            }
        }
        process = child
        do { try child.run() }
        catch { fail("无法启动本机采集：\(error.localizedDescription)"); return }
        DispatchQueue.main.asyncAfter(deadline: .now() + 12) { [weak self] in
            if self?.starting == true { self?.fail("采集启动超时，请退出工具后重试。请检查应用是否完整。") }
        }
    }

    func receive(_ text: String) {
        buffer += text
        guard starting, let match = buffer.range(of: #"http://127\.0\.0\.1:\d+"#, options: .regularExpression), let url = URL(string: String(buffer[match])) else { return }
        starting = false
        baseURL = url
        if !CommandLine.arguments.contains("--background") { showWindow() }
        poll()
        timer = Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { [weak self] _ in self?.poll() }
    }

    func format(_ value: Double, speed: Bool = false) -> String {
        let units = ["B", "KB", "MB", "GB", "TB"]
        var n = value
        var i = 0
        while n >= 1000 && i < 4 { n /= 1000; i += 1 }
        return String(format: i == 0 ? "%.0f %@" : "%.1f %@", n, units[i]) + (speed ? "/s" : "")
    }

    func poll() {
        guard let url = baseURL?.appendingPathComponent("api/stats") else { return }
        var request = URLRequest(url: url)
        request.timeoutInterval = 4
        URLSession.shared.dataTask(with: request) { [weak self] data, _, error in
            guard let self = self else { return }
            guard let data = data, error == nil, let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                DispatchQueue.main.async { self.status.button?.title = "⇅ 连接中断"; self.stateItem.title = "无法连接采集程序"; self.refreshPopover() }
                return
            }
            DispatchQueue.main.async {
                if let error = json["error"] as? String {
                    self.status.button?.title = "⇅ 采集异常"
                    self.stateItem.title = error
                    self.refreshPopover()
                    return
                }
                let points = json["points"] as? [[String: Any]] ?? []
                let last = points.last ?? [:]
                let down = (last["down"] as? Double) ?? 0
                let up = (last["up"] as? Double) ?? 0


                self.downItem.title = "下载：\(self.format(down, speed: true))"
                self.upItem.title = "上传：\(self.format(up, speed: true))"
                let stamp = String((json["updated"] as? String ?? "").dropFirst(11).prefix(8))
                self.stateItem.title = "正在记录 · 最近采样 " + stamp
                let today = json["today"] as? String ?? ""
                let days = json["days"] as? [[String: Any]] ?? []
                let row = days.first { $0["day"] as? String == today } ?? [:]
                let total = (row["down"] as? Double ?? 0) + (row["up"] as? Double ?? 0)
                self.todayItem.title = "今日总流量：\(self.format(total))"
                self.status.button?.title = String(format: "%.1fG", total / 1_000_000_000)
                self.status.button?.toolTip = "今日上传 + 下载：\(self.format(total))"
                self.refreshPopover()
            }
        }.resume()
    }

    @objc func showWindow() {
        popover.close()
        NSApp.activate(ignoringOtherApps: true)
        if web.url == nil, let url = baseURL { web.load(URLRequest(url: url)) }
        window.makeKeyAndOrderFront(nil)
    }
    @objc func openData() { popover.close(); NSWorkspace.shared.open(dataDir) }
    @objc func quit() { NSApp.terminate(nil) }
    @objc func exportCSV() { saveCSV(path: "export-minutes.csv") }
    func saveCSV(path: String) {
        popover.close()
        guard let url = baseURL?.appendingPathComponent(path) else { return }
        NSApp.activate(ignoringOtherApps: true)
        let panel = NSSavePanel()
        panel.nameFieldStringValue = path == "export-minutes.csv" ? "网络流量分钟记录.csv" : "网络流量每日汇总.csv"
        panel.canCreateDirectories = true
        guard panel.runModal() == .OK, let destination = panel.url else { return }
        URLSession.shared.dataTask(with: url) { [weak self] data, response, error in
            guard let data = data, error == nil, (response as? HTTPURLResponse)?.statusCode == 200 else {
                DispatchQueue.main.async { self?.fail("导出失败，请确认采集程序仍在运行。") }; return
            }
            do { try data.write(to: destination, options: .atomic) }
            catch { DispatchQueue.main.async { self?.fail("无法保存 CSV：\(error.localizedDescription)") } }
        }.resume()
    }
    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if let path = action.request.url?.path, ["/export.csv", "/export-minutes.csv"].contains(path) { decisionHandler(.cancel); saveCSV(path: String(path.dropFirst())); return }
        if action.request.url?.absoluteString == "https://test.ustc.edu.cn/", action.navigationType == .linkActivated { NSWorkspace.shared.open(action.request.url!); decisionHandler(.cancel); return }
        guard action.request.url?.host == "127.0.0.1" else { decisionHandler(.cancel); return }
        decisionHandler(.allow)
    }
    func fail(_ message: String) {
        starting = false
        let alert = NSAlert()
        alert.messageText = "流量手账"
        alert.informativeText = message
        alert.runModal()
    }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool { showWindow(); return true }
    func applicationWillTerminate(_ notification: Notification) {
        timer?.invalidate()
        popoverTimer?.invalidate()
        if process?.isRunning == true { process?.terminate(); process?.waitUntilExit() }
    }
}
let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
