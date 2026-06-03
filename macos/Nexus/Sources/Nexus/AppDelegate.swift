import AppKit
import NexusCore

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    private var statusItem: NSStatusItem!
    private var timer: Timer?
    private let runner = CommandRunner()
    private var config: AppConfig!
    private var probes: Probes!

    private let menubarLabel = "com.nexus.menubar"
    private let stackLabel = "com.nexus.stack"
    // Single source of truth for the docker binary path, shared by the probes
    // (via ToolPaths) and the explicit `compose stop caddy` call in stopAll().
    private let dockerBin = "/Applications/Docker.app/Contents/Resources/bin/docker"

    func applicationDidFinishLaunching(_ notification: Notification) {
        config = (try? AppConfig.loadDefault())
            ?? AppConfig(hostUrl: "https://ssowardm5.tail040188.ts.net",
                         repoPath: NSHomeDirectory(), caddyHostPort: "8443")
        let paths = ToolPaths(
            colima: "/opt/homebrew/bin/colima",
            docker: dockerBin,
            tailscale: "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
            repoPath: config.repoPath)
        probes = Probes(runner: runner, paths: paths, caddyHostPort: config.caddyHostPort)

        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem.button?.title = "◐"
        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.refresh() }
        }
    }

    private func dot(_ s: ComponentState) -> String {
        switch s { case .up: return "🟢"; case .starting: return "🟡"
                   case .down: return "🔴"; case .unknown: return "⚪️" }
    }

    private func refresh() {
        let probes = self.probes!   // Sendable snapshot for the background queue
        DispatchQueue.global(qos: .utility).async { [weak self] in
            let statuses = [probes.colima(), probes.caddy(),
                            probes.tailscale(), probes.backend()]
            DispatchQueue.main.async { self?.render(statuses) }
        }
    }

    private func render(_ statuses: [ComponentStatus]) {
        let overall = ComponentState.worst(statuses.map(\.state))
        statusItem.button?.title = dot(overall)

        let menu = NSMenu()
        for s in statuses {
            let item = NSMenuItem(title: "\(dot(s.state))  \(s.name): \(s.detail)",
                                  action: nil, keyEquivalent: "")
            item.isEnabled = false
            menu.addItem(item)
        }
        menu.addItem(.separator())
        menu.addItem(action("Start All", #selector(startAll)))
        menu.addItem(action("Stop All", #selector(stopAll)))
        menu.addItem(action("Restart", #selector(restartAll)))
        menu.addItem(.separator())
        menu.addItem(action("Open in Browser", #selector(openBrowser)))
        menu.addItem(action("View Logs", #selector(viewLogs)))
        let loginItem = action("Launch at Login", #selector(toggleLogin))
        loginItem.state = agentLoaded(menubarLabel) ? .on : .off
        menu.addItem(loginItem)
        menu.addItem(.separator())
        menu.addItem(action("Quit", #selector(quit)))
        statusItem.menu = menu
    }

    private func action(_ title: String, _ sel: Selector) -> NSMenuItem {
        let i = NSMenuItem(title: title, action: sel, keyEquivalent: "")
        i.target = self
        return i
    }

    /// Runs a LaunchctlControl-built argv. Those builders put the bare word
    /// "launchctl" at index 0; we drop it and substitute the absolute path.
    private func launchctl(_ argv: [String]) {
        _ = try? runner.run(["/bin/launchctl"] + Array(argv.dropFirst()), timeout: 10)
    }

    @objc private func startAll() {
        let uid = LaunchctlControl.currentUID
        // Stop All boots the KeepAlive agent OUT of launchd, so a plain kickstart
        // would fail ("service not loaded"). Bootstrap it if it's gone, else kickstart.
        if agentLoaded(stackLabel) {
            launchctl(LaunchctlControl.start(label: stackLabel, uid: uid))
        } else {
            launchctl(LaunchctlControl.bootstrap(plistPath: plistPath(stackLabel), uid: uid))
        }
        refresh()
    }
    @objc private func stopAll() {
        launchctl(LaunchctlControl.stop(label: stackLabel, uid: LaunchctlControl.currentUID))
        // Leave colima + tailscale up by design; stop Caddy explicitly.
        let repoPath = config.repoPath
        _ = try? runner.run(
            [dockerBin, "compose", "stop", "caddy"],
            cwd: repoPath, timeout: 15)
        refresh()
    }
    @objc private func restartAll() { startAll() }

    @objc private func openBrowser() {
        if let url = URL(string: config.hostUrl) { NSWorkspace.shared.open(url) }
    }
    @objc private func viewLogs() {
        let p = (("~/.nexus/logs") as NSString).expandingTildeInPath
        NSWorkspace.shared.open(URL(fileURLWithPath: p))
    }

    private func plistPath(_ label: String) -> String {
        (("~/Library/LaunchAgents/\(label).plist") as NSString).expandingTildeInPath
    }
    /// True if the given LaunchAgent label is currently bootstrapped in the GUI domain.
    private func agentLoaded(_ label: String) -> Bool {
        let r = try? runner.run(
            ["/bin/launchctl", "print", "gui/\(LaunchctlControl.currentUID)/\(label)"],
            timeout: 2)   // launchctl print is normally <50ms; 2s is an ample upper bound
        return (r?.exitCode ?? 1) == 0
    }
    @objc private func toggleLogin() {
        let uid = LaunchctlControl.currentUID
        if agentLoaded(menubarLabel) {
            launchctl(LaunchctlControl.stop(label: menubarLabel, uid: uid))
        } else {
            launchctl(LaunchctlControl.bootstrap(plistPath: plistPath(menubarLabel), uid: uid))
        }
        refresh()
    }

    @objc private func quit() { NSApplication.shared.terminate(nil) }
}
