import XCTest
@testable import NexusCore

final class StatusParsersTests: XCTestCase {
    func test_worst_returns_down_when_any_down() {
        XCTAssertEqual(ComponentState.worst([.up, .starting, .down]), .down)
    }

    func test_worst_returns_up_when_all_up() {
        XCTAssertEqual(ComponentState.worst([.up, .up]), .up)
    }

    func test_worst_returns_unknown_when_empty() {
        XCTAssertEqual(ComponentState.worst([]), .unknown)
    }
}
