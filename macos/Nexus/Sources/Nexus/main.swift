import AppKit

let app = NSApplication.shared
app.setActivationPolicy(.accessory)   // no Dock icon (LSUIElement equivalent)
let delegate = AppDelegate()
app.delegate = delegate
app.run()
