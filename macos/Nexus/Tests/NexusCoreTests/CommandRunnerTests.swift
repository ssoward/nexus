import XCTest
@testable import NexusCore

final class CommandRunnerTests: XCTestCase {
    // Regression guard: several probed tools (notably `colima status`) write their
    // status to stderr. CommandRunner must merge stderr into the captured output,
    // or those probes see empty stdout and report .unknown.
    func test_merges_stderr_into_output() throws {
        let r = try CommandRunner().run(
            ["/bin/sh", "-c", "echo to-stdout; echo to-stderr 1>&2"], timeout: 5)
        XCTAssertEqual(r.exitCode, 0)
        XCTAssertTrue(r.stdout.contains("to-stdout"), "missing stdout: \(r.stdout)")
        XCTAssertTrue(r.stdout.contains("to-stderr"), "stderr not merged: \(r.stdout)")
    }
}
