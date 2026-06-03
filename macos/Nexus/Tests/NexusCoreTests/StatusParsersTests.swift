import XCTest
@testable import NexusCore

// Class (not struct) so it can record the last cwd it was called with for assertions.
// @unchecked Sendable is fine: used synchronously from a single test thread.
final class StubRunner: CommandRunning, @unchecked Sendable {
    let responses: [String: CommandResult]   // keyed by argv[0]
    private(set) var lastCwd: String?
    init(responses: [String: CommandResult]) { self.responses = responses }
    func run(_ argv: [String], cwd: String?, timeout: TimeInterval) throws -> CommandResult {
        lastCwd = cwd
        return responses[argv[0]] ?? CommandResult(stdout: "", exitCode: 127)
    }
}

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

    func test_colima_running() {
        let out = "colima is running\nruntime: docker\n"
        XCTAssertEqual(StatusParsers.colima(stdout: out, exitCode: 0).state, .up)
    }

    func test_colima_stopped() {
        let out = "colima is not running"
        XCTAssertEqual(StatusParsers.colima(stdout: out, exitCode: 1).state, .down)
    }

    func test_colima_unknown_when_no_status_keyword() {
        XCTAssertEqual(StatusParsers.colima(stdout: "colima version 0.8.0", exitCode: 0).state, .unknown)
    }

    func test_caddy_running_from_compose_ps_json() {
        // `docker compose ps --format json` emits one JSON object per line.
        let out = #"{"Name":"nexus-caddy-1","Service":"caddy","State":"running"}"#
        XCTAssertEqual(StatusParsers.caddy(stdout: out, exitCode: 0).state, .up)
    }

    func test_caddy_down_when_no_lines() {
        XCTAssertEqual(StatusParsers.caddy(stdout: "", exitCode: 0).state, .down)
    }

    func test_caddy_restarting_is_starting() {
        let out = #"{"Service":"caddy","State":"restarting"}"#
        XCTAssertEqual(StatusParsers.caddy(stdout: out, exitCode: 0).state, .starting)
    }

    func test_tailscale_route_present() {
        let out = "tcp://0.0.0.0:443\n|-- tcp://localhost:8443\n"
        XCTAssertEqual(StatusParsers.tailscale(stdout: out, exitCode: 0, expectedTarget: "8443").state, .up)
    }

    func test_tailscale_route_absent() {
        let out = "No serve config\n"
        XCTAssertEqual(StatusParsers.tailscale(stdout: out, exitCode: 0, expectedTarget: "8443").state, .down)
    }

    func test_backend_healthy() {
        XCTAssertEqual(StatusParsers.backend(httpStatus: 200).state, .up)
    }

    func test_backend_unreachable() {
        XCTAssertEqual(StatusParsers.backend(httpStatus: nil).state, .down)
    }

    func test_backend_non_200_is_starting() {
        XCTAssertEqual(StatusParsers.backend(httpStatus: 503).state, .starting)
    }

    func test_probe_colima_up() throws {
        let runner = StubRunner(responses: [
            "/opt/homebrew/bin/colima": CommandResult(stdout: "colima is running", exitCode: 0)
        ])
        let probes = Probes(runner: runner,
                            paths: ToolPaths(colima: "/opt/homebrew/bin/colima",
                                             docker: "/d", tailscale: "/t", repoPath: "/r"),
                            caddyHostPort: "8443")
        XCTAssertEqual(probes.colima().state, .up)
    }

    func test_probe_caddy_passes_repo_path_as_cwd() throws {
        let runner = StubRunner(responses: [
            "/d": CommandResult(stdout: #"{"Service":"caddy","State":"running"}"#, exitCode: 0)
        ])
        let probes = Probes(runner: runner,
                            paths: ToolPaths(colima: "/c", docker: "/d",
                                             tailscale: "/t", repoPath: "/repo"),
                            caddyHostPort: "8443")
        XCTAssertEqual(probes.caddy().state, .up)
        XCTAssertEqual(runner.lastCwd, "/repo")
    }
}
