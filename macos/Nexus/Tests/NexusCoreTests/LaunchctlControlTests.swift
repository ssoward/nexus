import XCTest
@testable import NexusCore

final class LaunchctlControlTests: XCTestCase {
    let label = "com.nexus.stack"

    func test_start_uses_kickstart() {
        let argv = LaunchctlControl.start(label: label, uid: 501)
        XCTAssertEqual(argv, ["launchctl", "kickstart", "-k", "gui/501/com.nexus.stack"])
    }

    func test_stop_uses_bootout() {
        let argv = LaunchctlControl.stop(label: label, uid: 501)
        XCTAssertEqual(argv, ["launchctl", "bootout", "gui/501/com.nexus.stack"])
    }

    func test_bootstrap_includes_plist_path() {
        let argv = LaunchctlControl.bootstrap(plistPath: "/p/com.nexus.stack.plist", uid: 501)
        XCTAssertEqual(argv, ["launchctl", "bootstrap", "gui/501", "/p/com.nexus.stack.plist"])
    }
}
