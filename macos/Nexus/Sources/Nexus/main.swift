import AppKit
import NexusCore

// Single-instance: if another Nexus is already running (e.g. opened manually AND
// launched by the com.nexus.menubar login agent), exit so we don't add a 2nd icon.
let lockPath = ("~/.nexus/menubar.lock" as NSString).expandingTildeInPath
guard SingleInstance.acquire(lockPath: lockPath) else { exit(0) }

let app = NSApplication.shared
app.setActivationPolicy(.accessory)   // no Dock icon (LSUIElement equivalent)
let delegate = AppDelegate()
app.delegate = delegate
app.run()
