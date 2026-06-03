import XCTest
@testable import NexusCore

final class SingleInstanceTests: XCTestCase {
    func test_second_acquire_on_same_path_fails() {
        let path = NSTemporaryDirectory() + "nexus-si-\(UUID().uuidString).lock"
        XCTAssertTrue(SingleInstance.acquire(lockPath: path), "first acquire should succeed")
        XCTAssertFalse(SingleInstance.acquire(lockPath: path), "second acquire should fail while first holds the lock")
    }

    func test_distinct_paths_both_acquire() {
        let a = NSTemporaryDirectory() + "nexus-si-\(UUID().uuidString).lock"
        let b = NSTemporaryDirectory() + "nexus-si-\(UUID().uuidString).lock"
        XCTAssertTrue(SingleInstance.acquire(lockPath: a))
        XCTAssertTrue(SingleInstance.acquire(lockPath: b))
    }
}
