import Foundation

public enum LaunchctlControl {
    public static func start(label: String, uid: Int) -> [String] {
        ["launchctl", "kickstart", "-k", "gui/\(uid)/\(label)"]
    }
    public static func stop(label: String, uid: Int) -> [String] {
        ["launchctl", "bootout", "gui/\(uid)/\(label)"]
    }
    public static func bootstrap(plistPath: String, uid: Int) -> [String] {
        ["launchctl", "bootstrap", "gui/\(uid)", plistPath]
    }
    public static var currentUID: Int { Int(getuid()) }
}
