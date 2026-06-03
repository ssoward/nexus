# Nexus macOS Menu Bar App + Launch-at-Login Stack — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a native macOS menu bar app that controls and monitors the full Nexus stack (colima → Caddy → tailscale serve → backend), backed by a launchd LaunchAgent that brings the stack up at login and keeps it alive.

**Architecture:** A `LaunchAgent` (`com.nexus.stack`, RunAtLoad + KeepAlive) runs an idempotent bash bring-up script (`scripts/nexus-launch.sh`) that ensures colima, Caddy, and the tailscale route are up, then `exec`s uvicorn. A separate Swift/AppKit `NSStatusItem` app (`macos/Nexus`) is a thin controller + status dashboard that drives the agent via `launchctl` and polls each component. Heavy one-time setup (venv, deps, frontend build) lives in `scripts/nexus-setup.sh` so the agent's restart loop stays fast. Tool paths are detected at install time (tailscale is only at the app-bundle path; docker is Docker Desktop's binary) and written to `scripts/nexus-paths.sh`, sourced by the scripts.

**Tech Stack:** Swift 6.3 / AppKit (SwiftPM library `NexusCore` + executable `Nexus`, XCTest), bash (zero-dependency tests via PATH-shimmed mocks), launchd plists, `codesign` ad-hoc signing. Target: M5 only.

---

## File Structure

```
macos/
  Nexus/
    Package.swift                         # SwiftPM: NexusCore lib + Nexus executable + tests
    Sources/
      NexusCore/
        ComponentStatus.swift             # status enum + Component model
        StatusParsers.swift               # pure parsers for colima/docker/tailscale/health
        CommandRunner.swift               # Process wrapper + protocol for injection
        Probes.swift                      # async per-component probes (use CommandRunner)
        AppConfig.swift                   # load ~/.nexus/menubar.json
        LaunchctlControl.swift            # build launchctl/docker control argv
      Nexus/
        main.swift                        # NSApplication bootstrap, LSUIElement
        AppDelegate.swift                 # NSStatusItem, menu, timer, action handlers
    Tests/
      NexusCoreTests/
        StatusParsersTests.swift
        AppConfigTests.swift
        LaunchctlControlTests.swift
  com.nexus.stack.plist.template          # stack LaunchAgent (paths templated)
  com.nexus.menubar.plist.template        # menu bar app LaunchAgent (login launch)
  install.sh
  uninstall.sh
scripts/
  nexus-paths.sh.template                 # absolute tool paths (rendered by install.sh)
  nexus-lib.sh                            # sourced probe/ensure functions (testable)
  nexus-launch.sh                         # ordered idempotent bring-up (agent runs this)
  nexus-setup.sh                          # one-time heavy setup
  tests/
    test_nexus_lib.sh                     # zero-dep bash tests with PATH-shimmed mocks
```

No backend Python or existing frontend source changes. `start.sh` is unchanged.

---

## Conventions used by every task

- Commit messages follow Conventional Commits and end with the trailer
  `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>` (per CLAUDE.md).
- Run all `swift` commands from `macos/Nexus/`. Run bash tests from repo root.
- Host URL for M5: `https://ssowardm5.tail040188.ts.net` (derived from `config.yml` `webauthn.origin`).

---

### Task 1: Scaffold the SwiftPM package and prove the test harness

**Files:**
- Create: `macos/Nexus/Package.swift`
- Create: `macos/Nexus/Sources/NexusCore/ComponentStatus.swift`
- Create: `macos/Nexus/Sources/Nexus/main.swift`
- Test: `macos/Nexus/Tests/NexusCoreTests/StatusParsersTests.swift`

- [ ] **Step 1: Write `Package.swift`**

```swift
// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "Nexus",
    platforms: [.macOS(.v13)],   // .v13 = SMAppService era; we use launchd, but 13+ is fine
    targets: [
        .target(name: "NexusCore"),
        .executableTarget(
            name: "Nexus",
            dependencies: ["NexusCore"]
        ),
        .testTarget(
            name: "NexusCoreTests",
            dependencies: ["NexusCore"]
        ),
    ]
)
```

- [ ] **Step 2: Write the status model so the package compiles**

`Sources/NexusCore/ComponentStatus.swift`:

```swift
import Foundation

public enum ComponentState: String, Sendable {
    case up        // green
    case starting  // amber
    case down      // red
    case unknown   // gray
}

public struct ComponentStatus: Sendable, Equatable {
    public let name: String
    public let state: ComponentState
    public let detail: String

    public init(name: String, state: ComponentState, detail: String) {
        self.name = name
        self.state = state
        self.detail = detail
    }
}

extension ComponentState {
    /// The overall icon shows the worst state present. Order = severity.
    public static func worst(_ states: [ComponentState]) -> ComponentState {
        let severity: [ComponentState: Int] = [.up: 0, .starting: 1, .unknown: 2, .down: 3]
        return states.max(by: { (severity[$0] ?? 0) < (severity[$1] ?? 0) }) ?? .unknown
    }
}
```

- [ ] **Step 3: Write a placeholder executable entry point**

`Sources/Nexus/main.swift`:

```swift
// Replaced with full AppKit bootstrap in Task 8.
import NexusCore
print(ComponentState.worst([.up, .down]).rawValue)
```

- [ ] **Step 4: Write the first failing test**

`Tests/NexusCoreTests/StatusParsersTests.swift`:

```swift
import XCTest
@testable import NexusCore

final class StatusParsersTests: XCTestCase {
    func test_worst_returns_down_when_any_down() {
        XCTAssertEqual(ComponentState.worst([.up, .starting, .down]), .down)
    }

    func test_worst_returns_up_when_all_up() {
        XCTAssertEqual(ComponentState.worst([.up, .up]), .up)
    }
}
```

- [ ] **Step 5: Run tests, expect PASS**

Run: `cd macos/Nexus && swift test`
Expected: `Executed 2 tests, with 0 failures`. (If `swift test` fails to resolve, run `swift build` first.)

- [ ] **Step 6: Commit**

```bash
git add macos/Nexus
git commit -m "feat: scaffold Nexus menu bar SwiftPM package

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 2: Status parsers (pure functions, TDD)

These convert raw CLI output into `ComponentStatus`. Pure, no I/O — fully unit-testable.

**Files:**
- Create: `macos/Nexus/Sources/NexusCore/StatusParsers.swift`
- Modify: `macos/Nexus/Tests/NexusCoreTests/StatusParsersTests.swift`

- [ ] **Step 1: Write failing tests for all four parsers**

Add to `StatusParsersTests.swift`:

```swift
func test_colima_running() {
    let out = "colima is running\nruntime: docker\n"
    XCTAssertEqual(StatusParsers.colima(stdout: out, exitCode: 0).state, .up)
}

func test_colima_stopped() {
    let out = "colima is not running"
    XCTAssertEqual(StatusParsers.colima(stdout: out, exitCode: 1).state, .down)
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
```

- [ ] **Step 2: Run tests, expect FAIL**

Run: `cd macos/Nexus && swift test`
Expected: compile error — `StatusParsers` not defined.

- [ ] **Step 3: Implement the parsers**

`Sources/NexusCore/StatusParsers.swift`:

```swift
import Foundation

public enum StatusParsers {
    public static func colima(stdout: String, exitCode: Int32) -> ComponentStatus {
        let lower = stdout.lowercased()
        let state: ComponentState
        if exitCode == 0 && lower.contains("running") && !lower.contains("not running") {
            state = .up
        } else if lower.contains("not running") || exitCode != 0 {
            state = .down
        } else {
            state = .unknown
        }
        return ComponentStatus(name: "colima", state: state,
                               detail: state == .up ? "running" : "stopped")
    }

    public static func caddy(stdout: String, exitCode: Int32) -> ComponentStatus {
        let lines = stdout.split(whereSeparator: \.isNewline)
            .map(String.init).filter { $0.contains("{") }
        guard exitCode == 0, !lines.isEmpty else {
            return ComponentStatus(name: "Caddy", state: .down, detail: "down")
        }
        // Look at the first caddy line's "State".
        let joined = lines.joined().lowercased()
        if joined.contains("\"state\":\"running\"") {
            return ComponentStatus(name: "Caddy", state: .up, detail: "running")
        }
        if joined.contains("restarting") || joined.contains("created") || joined.contains("starting") {
            return ComponentStatus(name: "Caddy", state: .starting, detail: "starting")
        }
        return ComponentStatus(name: "Caddy", state: .down, detail: "down")
    }

    public static func tailscale(stdout: String, exitCode: Int32, expectedTarget: String) -> ComponentStatus {
        let present = exitCode == 0 && stdout.contains(expectedTarget) && stdout.contains("443")
        return ComponentStatus(name: "tailscale", state: present ? .up : .down,
                               detail: present ? ":443→\(expectedTarget)" : "no route")
    }

    public static func backend(httpStatus: Int?) -> ComponentStatus {
        switch httpStatus {
        case .some(200): return ComponentStatus(name: "backend", state: .up, detail: ":8000 healthy")
        case .some(let code): return ComponentStatus(name: "backend", state: .starting, detail: "HTTP \(code)")
        case .none: return ComponentStatus(name: "backend", state: .down, detail: "unreachable")
        }
    }
}
```

- [ ] **Step 4: Run tests, expect PASS**

Run: `cd macos/Nexus && swift test`
Expected: all parser tests pass.

- [ ] **Step 5: Commit**

```bash
git add macos/Nexus
git commit -m "feat: status parsers for stack components

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 3: CommandRunner + AppConfig + LaunchctlControl (logic, TDD)

**Files:**
- Create: `macos/Nexus/Sources/NexusCore/CommandRunner.swift`
- Create: `macos/Nexus/Sources/NexusCore/AppConfig.swift`
- Create: `macos/Nexus/Sources/NexusCore/LaunchctlControl.swift`
- Test: `macos/Nexus/Tests/NexusCoreTests/AppConfigTests.swift`
- Test: `macos/Nexus/Tests/NexusCoreTests/LaunchctlControlTests.swift`

- [ ] **Step 1: Write failing tests for AppConfig and LaunchctlControl**

`Tests/NexusCoreTests/AppConfigTests.swift`:

```swift
import XCTest
@testable import NexusCore

final class AppConfigTests: XCTestCase {
    func test_decode_from_json() throws {
        let json = #"{"hostUrl":"https://ssowardm5.tail040188.ts.net","repoPath":"/Users/x/nexus","caddyHostPort":"8443"}"#
        let cfg = try AppConfig.decode(Data(json.utf8))
        XCTAssertEqual(cfg.hostUrl, "https://ssowardm5.tail040188.ts.net")
        XCTAssertEqual(cfg.repoPath, "/Users/x/nexus")
        XCTAssertEqual(cfg.caddyHostPort, "8443")
    }

    func test_default_caddy_port_when_missing() throws {
        let json = #"{"hostUrl":"https://h","repoPath":"/r"}"#
        let cfg = try AppConfig.decode(Data(json.utf8))
        XCTAssertEqual(cfg.caddyHostPort, "8443")
    }
}
```

`Tests/NexusCoreTests/LaunchctlControlTests.swift`:

```swift
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
```

- [ ] **Step 2: Run tests, expect FAIL (types undefined)**

Run: `cd macos/Nexus && swift test`
Expected: compile errors for `AppConfig`, `LaunchctlControl`.

- [ ] **Step 3: Implement CommandRunner**

`Sources/NexusCore/CommandRunner.swift`:

```swift
import Foundation

public struct CommandResult: Sendable {
    public let stdout: String
    public let exitCode: Int32
}

public protocol CommandRunning: Sendable {
    /// Runs argv[0] with the rest as arguments. Returns combined stdout (stderr discarded)
    /// and exit code. Throws on launch failure. `timeout` seconds enforced via termination.
    func run(_ argv: [String], timeout: TimeInterval) throws -> CommandResult
}

public struct CommandRunner: CommandRunning {
    public init() {}

    public func run(_ argv: [String], timeout: TimeInterval) throws -> CommandResult {
        precondition(!argv.isEmpty)
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: argv[0])
        proc.arguments = Array(argv.dropFirst())
        let pipe = Pipe()
        proc.standardOutput = pipe
        proc.standardError = Pipe()   // discard stderr noise
        try proc.run()

        let deadline = Date().addingTimeInterval(timeout)
        while proc.isRunning && Date() < deadline {
            usleep(50_000)  // 50ms
        }
        if proc.isRunning { proc.terminate() }

        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        proc.waitUntilExit()
        return CommandResult(stdout: String(decoding: data, as: UTF8.self),
                             exitCode: proc.terminationStatus)
    }
}
```

- [ ] **Step 4: Implement AppConfig**

`Sources/NexusCore/AppConfig.swift`:

```swift
import Foundation

public struct AppConfig: Sendable, Equatable {
    public let hostUrl: String
    public let repoPath: String
    public let caddyHostPort: String

    private struct Raw: Decodable {
        let hostUrl: String
        let repoPath: String
        let caddyHostPort: String?
    }

    public static func decode(_ data: Data) throws -> AppConfig {
        let raw = try JSONDecoder().decode(Raw.self, from: data)
        return AppConfig(hostUrl: raw.hostUrl,
                         repoPath: raw.repoPath,
                         caddyHostPort: raw.caddyHostPort ?? "8443")
    }

    public static func loadDefault() throws -> AppConfig {
        let path = ("~/.nexus/menubar.json" as NSString).expandingTildeInPath
        return try decode(Data(contentsOf: URL(fileURLWithPath: path)))
    }
}
```

- [ ] **Step 5: Implement LaunchctlControl**

`Sources/NexusCore/LaunchctlControl.swift`:

```swift
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
```

- [ ] **Step 6: Run tests, expect PASS**

Run: `cd macos/Nexus && swift test`
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add macos/Nexus
git commit -m "feat: command runner, app config, launchctl control

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 4: Probes — wire parsers to CommandRunner

**Files:**
- Create: `macos/Nexus/Sources/NexusCore/Probes.swift`
- Modify: `macos/Nexus/Tests/NexusCoreTests/StatusParsersTests.swift` (add probe tests with a stub runner)

- [ ] **Step 1: Write failing test using a stub CommandRunning**

Add to `StatusParsersTests.swift`:

```swift
struct StubRunner: CommandRunning {
    let responses: [String: CommandResult]   // keyed by argv[0]
    func run(_ argv: [String], timeout: TimeInterval) throws -> CommandResult {
        responses[argv[0]] ?? CommandResult(stdout: "", exitCode: 127)
    }
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
```

- [ ] **Step 2: Run tests, expect FAIL (`Probes`, `ToolPaths` undefined)**

Run: `cd macos/Nexus && swift test`
Expected: compile error.

- [ ] **Step 3: Implement Probes**

`Sources/NexusCore/Probes.swift`:

```swift
import Foundation

public struct ToolPaths: Sendable {
    public let colima: String
    public let docker: String
    public let tailscale: String
    public let repoPath: String
    public init(colima: String, docker: String, tailscale: String, repoPath: String) {
        self.colima = colima; self.docker = docker
        self.tailscale = tailscale; self.repoPath = repoPath
    }
}

public struct Probes: Sendable {
    let runner: CommandRunning
    let paths: ToolPaths
    let caddyHostPort: String

    public init(runner: CommandRunning, paths: ToolPaths, caddyHostPort: String) {
        self.runner = runner; self.paths = paths; self.caddyHostPort = caddyHostPort
    }

    public func colima() -> ComponentStatus {
        let r = (try? runner.run([paths.colima, "status"], timeout: 4))
            ?? CommandResult(stdout: "", exitCode: 127)
        return StatusParsers.colima(stdout: r.stdout, exitCode: r.exitCode)
    }

    public func caddy() -> ComponentStatus {
        let r = (try? runner.run(
            [paths.docker, "compose", "ps", "--format", "json"], timeout: 5))
            ?? CommandResult(stdout: "", exitCode: 127)
        return StatusParsers.caddy(stdout: r.stdout, exitCode: r.exitCode)
    }

    public func tailscale() -> ComponentStatus {
        let r = (try? runner.run([paths.tailscale, "serve", "status"], timeout: 4))
            ?? CommandResult(stdout: "", exitCode: 127)
        return StatusParsers.tailscale(stdout: r.stdout, exitCode: r.exitCode,
                                       expectedTarget: caddyHostPort)
    }

    /// Synchronous HTTP health check against the local backend.
    public func backend() -> ComponentStatus {
        var status: Int? = nil
        let sem = DispatchSemaphore(value: 0)
        var req = URLRequest(url: URL(string: "http://127.0.0.1:8000/api/health")!)
        req.timeoutInterval = 3
        URLSession.shared.dataTask(with: req) { _, resp, _ in
            status = (resp as? HTTPURLResponse)?.statusCode
            sem.signal()
        }.resume()
        _ = sem.wait(timeout: .now() + 4)
        return StatusParsers.backend(httpStatus: status)
    }
}
```

Note: the `caddy()` probe runs `docker compose` from the repo dir; the AppKit layer sets the runner's working dir indirectly by passing absolute `-f` is avoided — instead Task 8 runs probes with `paths.repoPath` as CWD by giving CommandRunner a cwd. Add cwd support:

- [ ] **Step 4: Add optional working directory to CommandRunner**

Edit `CommandRunner.swift` — change the protocol and impl:

```swift
public protocol CommandRunning: Sendable {
    func run(_ argv: [String], cwd: String?, timeout: TimeInterval) throws -> CommandResult
}

extension CommandRunning {
    public func run(_ argv: [String], timeout: TimeInterval) throws -> CommandResult {
        try run(argv, cwd: nil, timeout: timeout)
    }
}
```

In `CommandRunner.run`, after creating `proc`:

```swift
if let cwd { proc.currentDirectoryURL = URL(fileURLWithPath: cwd) }
```

And update the `caddy()` probe call to pass `cwd: paths.repoPath`:

```swift
let r = (try? runner.run([paths.docker, "compose", "ps", "--format", "json"],
                         cwd: paths.repoPath, timeout: 5)) ?? ...
```

Update `StubRunner` in the test to match the new protocol signature (add `cwd: String?`).

- [ ] **Step 5: Run tests, expect PASS**

Run: `cd macos/Nexus && swift test`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add macos/Nexus
git commit -m "feat: component probes backed by command runner

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 5: Shared bash library `nexus-lib.sh` (TDD with PATH-shimmed mocks)

**Files:**
- Create: `scripts/nexus-paths.sh.template`
- Create: `scripts/nexus-lib.sh`
- Test: `scripts/tests/test_nexus_lib.sh`

- [ ] **Step 1: Write the paths template**

`scripts/nexus-paths.sh.template` (install.sh substitutes `@VAR@` tokens):

```bash
# Generated by macos/install.sh — absolute tool paths for the launch scripts.
COLIMA_BIN="@COLIMA_BIN@"
DOCKER_BIN="@DOCKER_BIN@"
TAILSCALE_BIN="@TAILSCALE_BIN@"
REPO_ROOT="@REPO_ROOT@"
CADDY_HOST_PORT="${CADDY_HOST_PORT:-8443}"
```

- [ ] **Step 2: Write failing tests**

`scripts/tests/test_nexus_lib.sh`:

```bash
#!/usr/bin/env bash
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"

fail=0
assert_eq() { # $1 expected $2 actual $3 msg
  if [[ "$1" != "$2" ]]; then echo "FAIL: $3 (expected '$1', got '$2')"; fail=1
  else echo "ok: $3"; fi
}

# Build a temp dir of fake tools we control via env-driven exit codes.
MOCKBIN="$(mktemp -d)"
trap 'rm -rf "$MOCKBIN"' EXIT

cat > "$MOCKBIN/colima" <<'EOF'
#!/usr/bin/env bash
[[ "$1" == "status" ]] && { echo "$COLIMA_OUT"; exit "${COLIMA_RC:-0}"; }
exit 0
EOF
cat > "$MOCKBIN/docker" <<'EOF'
#!/usr/bin/env bash
echo "$DOCKER_OUT"; exit "${DOCKER_RC:-0}"
EOF
cat > "$MOCKBIN/tailscale" <<'EOF'
#!/usr/bin/env bash
echo "$TS_OUT"; exit "${TS_RC:-0}"
EOF
chmod +x "$MOCKBIN"/*

# Source the lib with paths pointing at the mocks.
COLIMA_BIN="$MOCKBIN/colima"
DOCKER_BIN="$MOCKBIN/docker"
TAILSCALE_BIN="$MOCKBIN/tailscale"
CADDY_HOST_PORT="8443"
REPO_ROOT="$REPO_ROOT"
source "$REPO_ROOT/scripts/nexus-lib.sh"

COLIMA_OUT="colima is running" COLIMA_RC=0
colima_running; assert_eq "0" "$?" "colima_running true when running"

COLIMA_OUT="colima is not running" COLIMA_RC=1
colima_running; assert_eq "1" "$?" "colima_running false when stopped"

TS_OUT="tcp://0.0.0.0:443 -> tcp://localhost:8443" TS_RC=0
tailscale_route_present; assert_eq "0" "$?" "tailscale route present"

TS_OUT="No serve config" TS_RC=0
tailscale_route_present; assert_eq "1" "$?" "tailscale route absent"

exit $fail
```

- [ ] **Step 3: Run tests, expect FAIL**

Run: `bash scripts/tests/test_nexus_lib.sh`
Expected: failures because `nexus-lib.sh` does not exist.

- [ ] **Step 4: Implement `nexus-lib.sh`**

`scripts/nexus-lib.sh`:

```bash
# Sourced helper functions for the Nexus launch scripts.
# Requires COLIMA_BIN, DOCKER_BIN, TAILSCALE_BIN, REPO_ROOT, CADDY_HOST_PORT in env
# (normally provided by nexus-paths.sh).

log() { echo "$(date '+%Y-%m-%dT%H:%M:%S') nexus: $*" >&2; }

colima_running() {
  local out
  out="$("$COLIMA_BIN" status 2>&1)" || return 1
  [[ "$out" == *"running"* && "$out" != *"not running"* ]]
}

caddy_running() {
  "$DOCKER_BIN" compose ps --format json 2>/dev/null \
    | grep -q '"State":"running"'
}

tailscale_route_present() {
  "$TAILSCALE_BIN" serve status 2>/dev/null | grep -q "$CADDY_HOST_PORT"
}

backend_healthy() {
  curl -fsS --max-time 3 http://127.0.0.1:8000/api/health >/dev/null 2>&1
}

# Bring colima up and wait until the docker socket answers (bounded).
ensure_colima() {
  if colima_running; then return 0; fi
  log "starting colima"
  "$COLIMA_BIN" start || return 1
  for _ in $(seq 1 30); do
    "$DOCKER_BIN" info >/dev/null 2>&1 && return 0
    sleep 2
  done
  log "ERROR: docker did not become ready"
  return 1
}

ensure_caddy() {
  caddy_running && return 0
  log "starting Caddy"
  ( cd "$REPO_ROOT" && "$DOCKER_BIN" compose up -d caddy )
}

ensure_tailscale_route() {
  tailscale_route_present && return 0
  log "applying tailscale serve route :443 -> ${CADDY_HOST_PORT}"
  "$TAILSCALE_BIN" serve --bg --tcp=443 "tcp://localhost:${CADDY_HOST_PORT}"
}
```

- [ ] **Step 5: Run tests, expect PASS**

Run: `bash scripts/tests/test_nexus_lib.sh`
Expected: all `ok:` lines, exit 0.

- [ ] **Step 6: Commit**

```bash
git add scripts/nexus-lib.sh scripts/nexus-paths.sh.template scripts/tests/test_nexus_lib.sh
git commit -m "feat: nexus-lib bash helpers with mocked tests

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 6: `nexus-launch.sh` (agent entry point) and `nexus-setup.sh`

**Files:**
- Create: `scripts/nexus-launch.sh`
- Create: `scripts/nexus-setup.sh`

- [ ] **Step 1: Write `nexus-launch.sh`**

```bash
#!/usr/bin/env bash
# Ordered, idempotent bring-up of the Nexus stack, then exec uvicorn.
# Run by the com.nexus.stack LaunchAgent (KeepAlive). Safe to re-run.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$HERE/nexus-paths.sh"
# shellcheck source=/dev/null
source "$HERE/nexus-lib.sh"

cd "$REPO_ROOT"

# Load secrets / CADDY_HOST_PORT from .env if present.
if [[ -f "$REPO_ROOT/.env" ]]; then set -a; source "$REPO_ROOT/.env"; set +a; fi
export CONFIG_PATH="$REPO_ROOT/config.yml"

VENV="$REPO_ROOT/backend/.venv"
if [[ ! -x "$VENV/bin/uvicorn" ]]; then
  log "ERROR: venv/uvicorn missing — run scripts/nexus-setup.sh first"
  exit 1
fi
if [[ ! -f "$REPO_ROOT/static/index.html" ]]; then
  log "ERROR: static/ not built — run scripts/nexus-setup.sh first"
  exit 1
fi

ensure_colima        || { log "colima not ready"; exit 1; }
ensure_caddy         || log "WARN: caddy up failed (continuing)"
ensure_tailscale_route || log "WARN: tailscale route failed (continuing)"

log "starting backend on 127.0.0.1:8000"
cd "$REPO_ROOT/backend"
exec "$VENV/bin/uvicorn" app.main:app --host 127.0.0.1 --port 8000 --log-level info
```

- [ ] **Step 2: Write `nexus-setup.sh` (heavy one-time setup)**

```bash
#!/usr/bin/env bash
# One-time / on-demand heavy setup: venv, python deps, frontend build, static copy.
# NOT run by the LaunchAgent. Run by install.sh and manually after dep changes.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$REPO_ROOT/backend"
FRONTEND="$REPO_ROOT/frontend"

if [[ ! -d "$BACKEND/.venv" ]]; then
  echo "Creating venv..."; python3 -m venv "$BACKEND/.venv"
fi
# shellcheck source=/dev/null
source "$BACKEND/.venv/bin/activate"
pip install -q --upgrade pip
pip install -q -r "$BACKEND/requirements.txt"

echo "Building frontend..."
( cd "$FRONTEND" && npm install --silent && npm run build --silent )

echo "Copying dist -> static..."
mkdir -p "$REPO_ROOT/static"
cp -r "$FRONTEND/dist/." "$REPO_ROOT/static/"
echo "Setup complete."
```

- [ ] **Step 3: Make both executable and shellcheck-clean**

Run:
```bash
chmod +x scripts/nexus-launch.sh scripts/nexus-setup.sh
bash -n scripts/nexus-launch.sh && bash -n scripts/nexus-setup.sh && echo "syntax ok"
```
Expected: `syntax ok`.

- [ ] **Step 4: Smoke-test setup (real, slow — verifies end state)**

Run: `bash scripts/nexus-setup.sh`
Expected: exits 0; then verify:
```bash
test -x backend/.venv/bin/uvicorn && test -f static/index.html && echo "setup OK"
```
Expected: `setup OK`.

- [ ] **Step 5: Commit**

```bash
git add scripts/nexus-launch.sh scripts/nexus-setup.sh
git commit -m "feat: nexus-launch and nexus-setup scripts

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 7: LaunchAgent plist templates

**Files:**
- Create: `macos/com.nexus.stack.plist.template`
- Create: `macos/com.nexus.menubar.plist.template`

- [ ] **Step 1: Write the stack agent template**

`macos/com.nexus.stack.plist.template` (`@REPO_ROOT@`, `@PATH@`, `@HOME@` substituted by install.sh):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.nexus.stack</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>@REPO_ROOT@/scripts/nexus-launch.sh</string>
  </array>
  <key>WorkingDirectory</key><string>@REPO_ROOT@</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>@PATH@</string>
    <key>HOME</key><string>@HOME@</string>
  </dict>
  <key>StandardOutPath</key><string>@HOME@/.nexus/logs/stack.out.log</string>
  <key>StandardErrorPath</key><string>@HOME@/.nexus/logs/stack.err.log</string>
</dict>
</plist>
```

- [ ] **Step 2: Write the menu bar agent template**

`macos/com.nexus.menubar.plist.template`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.nexus.menubar</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Applications/Nexus.app/Contents/MacOS/Nexus</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><false/>
  <key>StandardOutPath</key><string>@HOME@/.nexus/logs/menubar.out.log</string>
  <key>StandardErrorPath</key><string>@HOME@/.nexus/logs/menubar.err.log</string>
</dict>
</plist>
```

Note: the menu bar app's "Launch at login" toggle loads/unloads `com.nexus.menubar` (chosen over `SMAppService` for reliability with ad-hoc signing and consistency with the stack agent).

- [ ] **Step 3: Validate plist syntax**

Run:
```bash
plutil -lint macos/com.nexus.stack.plist.template macos/com.nexus.menubar.plist.template
```
Expected: both report `OK` (plutil tolerates the `@TOKENS@` as string values).

- [ ] **Step 4: Commit**

```bash
git add macos/com.nexus.stack.plist.template macos/com.nexus.menubar.plist.template
git commit -m "feat: launchd plist templates for stack and menu bar

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 8: AppKit menu bar UI (`AppDelegate` + `main`)

No unit tests (UI/integration); verified manually in Task 10. All logic it relies on is already tested in NexusCore.

**Files:**
- Modify: `macos/Nexus/Sources/Nexus/main.swift`
- Create: `macos/Nexus/Sources/Nexus/AppDelegate.swift`

- [ ] **Step 1: Replace `main.swift` with the AppKit bootstrap**

```swift
import AppKit

let app = NSApplication.shared
app.setActivationPolicy(.accessory)   // no Dock icon (LSUIElement equivalent)
let delegate = AppDelegate()
app.delegate = delegate
app.run()
```

- [ ] **Step 2: Write `AppDelegate.swift`**

```swift
import AppKit
import NexusCore

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var statusItem: NSStatusItem!
    private var timer: Timer?
    private let runner = CommandRunner()
    private var config: AppConfig!
    private var probes: Probes!

    private let menubarLabel = "com.nexus.menubar"
    private let stackLabel = "com.nexus.stack"

    func applicationDidFinishLaunching(_ notification: Notification) {
        config = (try? AppConfig.loadDefault())
            ?? AppConfig(hostUrl: "https://ssowardm5.tail040188.ts.net",
                         repoPath: NSHomeDirectory(), caddyHostPort: "8443")
        let paths = ToolPaths(
            colima: "/opt/homebrew/bin/colima",
            docker: "/Applications/Docker.app/Contents/Resources/bin/docker",
            tailscale: "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
            repoPath: config.repoPath)
        probes = Probes(runner: runner, paths: paths, caddyHostPort: config.caddyHostPort)

        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem.button?.title = "◐"
        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in
            self?.refresh()
        }
    }

    private func dot(_ s: ComponentState) -> String {
        switch s { case .up: return "🟢"; case .starting: return "🟡"
                   case .down: return "🔴"; case .unknown: return "⚪️" }
    }

    private func refresh() {
        DispatchQueue.global(qos: .utility).async { [weak self] in
            guard let self else { return }
            let statuses = [self.probes.colima(), self.probes.caddy(),
                            self.probes.tailscale(), self.probes.backend()]
            DispatchQueue.main.async { self.render(statuses) }
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
        loginItem.state = loginAgentInstalled() ? .on : .off
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

    private func launchctl(_ argv: [String]) {
        _ = try? runner.run(["/bin/launchctl"] + Array(argv.dropFirst()), timeout: 10)
    }

    @objc private func startAll() {
        launchctl(LaunchctlControl.start(label: stackLabel, uid: LaunchctlControl.currentUID))
        refresh()
    }
    @objc private func stopAll() {
        launchctl(LaunchctlControl.stop(label: stackLabel, uid: LaunchctlControl.currentUID))
        // Leave colima + tailscale up by design; stop Caddy explicitly.
        _ = try? runner.run(
            ["/Applications/Docker.app/Contents/Resources/bin/docker", "compose", "stop", "caddy"],
            cwd: config.repoPath, timeout: 15)
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

    private var menubarPlistPath: String {
        (("~/Library/LaunchAgents/com.nexus.menubar.plist") as NSString).expandingTildeInPath
    }
    private func loginAgentInstalled() -> Bool {
        let r = try? runner.run(
            ["/bin/launchctl", "print", "gui/\(LaunchctlControl.currentUID)/\(menubarLabel)"],
            timeout: 5)
        return (r?.exitCode ?? 1) == 0
    }
    @objc private func toggleLogin() {
        let uid = LaunchctlControl.currentUID
        if loginAgentInstalled() {
            launchctl(LaunchctlControl.stop(label: menubarLabel, uid: uid))
        } else {
            launchctl(LaunchctlControl.bootstrap(plistPath: menubarPlistPath, uid: uid))
        }
        refresh()
    }

    @objc private func quit() { NSApplication.shared.terminate(nil) }
}
```

- [ ] **Step 3: Build the executable**

Run: `cd macos/Nexus && swift build -c release`
Expected: `Compiling`/`Build complete!` with no errors.

- [ ] **Step 4: Smoke-run (manual, ~5s)**

Run: `cd macos/Nexus && swift run Nexus &` then observe a dot appears in the menu bar; click it to confirm the menu renders component rows + actions. Then `kill %1`.
Expected: menu bar icon appears; menu lists colima/Caddy/tailscale/backend and the action items.

- [ ] **Step 5: Commit**

```bash
git add macos/Nexus/Sources/Nexus
git commit -m "feat: AppKit menu bar UI with status polling and controls

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 9: `install.sh` / `uninstall.sh`

**Files:**
- Create: `macos/install.sh`
- Create: `macos/uninstall.sh`

- [ ] **Step 1: Write `install.sh`**

```bash
#!/usr/bin/env bash
# Install the Nexus stack LaunchAgent + menu bar app on M5.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOME_DIR="$HOME"
LA_DIR="$HOME/Library/LaunchAgents"
mkdir -p "$LA_DIR" "$HOME/.nexus/logs"

# 1. Detect tool paths (tailscale only exists at the app bundle path).
COLIMA_BIN="$(command -v colima || echo /opt/homebrew/bin/colima)"
DOCKER_BIN="$(command -v docker || echo /Applications/Docker.app/Contents/Resources/bin/docker)"
TAILSCALE_BIN="/Applications/Tailscale.app/Contents/MacOS/Tailscale"
[[ -x "$TAILSCALE_BIN" ]] || TAILSCALE_BIN="$(command -v tailscale || true)"

# 2. Heavy setup (venv, deps, frontend build, static copy).
bash "$REPO_ROOT/scripts/nexus-setup.sh"

# 3. Render scripts/nexus-paths.sh.
sed -e "s#@COLIMA_BIN@#$COLIMA_BIN#g" \
    -e "s#@DOCKER_BIN@#$DOCKER_BIN#g" \
    -e "s#@TAILSCALE_BIN@#$TAILSCALE_BIN#g" \
    -e "s#@REPO_ROOT@#$REPO_ROOT#g" \
    "$REPO_ROOT/scripts/nexus-paths.sh.template" > "$REPO_ROOT/scripts/nexus-paths.sh"

# 4. Build + assemble + ad-hoc-sign Nexus.app.
( cd "$REPO_ROOT/macos/Nexus" && swift build -c release )
BIN="$REPO_ROOT/macos/Nexus/.build/release/Nexus"
APP="/Applications/Nexus.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"
cp "$BIN" "$APP/Contents/MacOS/Nexus"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Nexus</string>
  <key>CFBundleIdentifier</key><string>net.ts.nexus.menubar</string>
  <key>CFBundleExecutable</key><string>Nexus</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0.0</string>
  <key>LSUIElement</key><true/>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
</dict></plist>
PLIST
codesign --force --deep -s - "$APP"

# 5. Render + install plists.
PATH_VALUE="/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:$REPO_ROOT/backend/.venv/bin"
for label in stack menubar; do
  sed -e "s#@REPO_ROOT@#$REPO_ROOT#g" \
      -e "s#@HOME@#$HOME_DIR#g" \
      -e "s#@PATH@#$PATH_VALUE#g" \
      "$REPO_ROOT/macos/com.nexus.$label.plist.template" \
      > "$LA_DIR/com.nexus.$label.plist"
  plutil -lint "$LA_DIR/com.nexus.$label.plist"
done

# 6. Write menu bar config.
ORIGIN="$(grep -E '^[[:space:]]*origin:' "$REPO_ROOT/config.yml" | head -1 | sed 's/.*origin:[[:space:]]*//')"
cat > "$HOME/.nexus/menubar.json" <<JSON
{"hostUrl":"$ORIGIN","repoPath":"$REPO_ROOT","caddyHostPort":"${CADDY_HOST_PORT:-8443}"}
JSON

# 7. (Re)bootstrap the stack agent.
UID_NUM="$(id -u)"
launchctl bootout "gui/$UID_NUM/com.nexus.stack" 2>/dev/null || true
launchctl bootstrap "gui/$UID_NUM" "$LA_DIR/com.nexus.stack.plist"

echo "Installed. Open /Applications/Nexus.app, then enable 'Launch at Login' from its menu."
echo "Stack agent loaded; check: launchctl print gui/$UID_NUM/com.nexus.stack"
```

- [ ] **Step 2: Write `uninstall.sh`**

```bash
#!/usr/bin/env bash
set -uo pipefail
UID_NUM="$(id -u)"
LA_DIR="$HOME/Library/LaunchAgents"
for label in stack menubar; do
  launchctl bootout "gui/$UID_NUM/com.nexus.$label" 2>/dev/null || true
  rm -f "$LA_DIR/com.nexus.$label.plist"
done
rm -rf /Applications/Nexus.app
echo "Uninstalled launch agents and app. ~/.nexus data left intact."
```

- [ ] **Step 3: Syntax check both**

Run: `chmod +x macos/install.sh macos/uninstall.sh && bash -n macos/install.sh && bash -n macos/uninstall.sh && echo ok`
Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add macos/install.sh macos/uninstall.sh
git commit -m "feat: install/uninstall scripts for menu bar + stack agent

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 10: End-to-end install + verification on M5

No new files. This task validates the whole system.

- [ ] **Step 1: Run the installer**

Run: `bash macos/install.sh`
Expected: ends with the "Installed." message; no errors from `plutil`/`codesign`/`launchctl`.

- [ ] **Step 2: Verify the stack agent loaded and backend came up**

Run:
```bash
launchctl print "gui/$(id -u)/com.nexus.stack" | grep -E 'state|pid' | head
sleep 15
curl -fsS http://127.0.0.1:8000/api/health && echo " <- backend OK"
```
Expected: agent shows a running pid; health endpoint returns JSON.

- [ ] **Step 3: Verify external reachability (tailscale + Caddy)**

Run: `curl -ks https://ssowardm5.tail040188.ts.net/api/health && echo " <- https OK"`
Expected: JSON health response over HTTPS.

- [ ] **Step 4: Verify the menu bar app**

Open `/Applications/Nexus.app`. Confirm: a dot appears in the menu bar; the menu lists colima/Caddy/tailscale/backend with colored dots; click **Stop All**, watch backend dot go red within ~10s; **Start All** brings it back; **Open in Browser** opens the host URL; toggle **Launch at Login** and confirm `launchctl print gui/$(id -u)/com.nexus.menubar` exit code flips.

- [ ] **Step 5: Verify crash-restart (KeepAlive)**

Run:
```bash
pkill -f 'uvicorn app.main:app'
sleep 15
curl -fsS http://127.0.0.1:8000/api/health && echo " <- auto-restarted OK"
```
Expected: backend is back up (launchd re-ran `nexus-launch.sh`).

- [ ] **Step 6: No commit (verification only)** — record results in the PR description.

---

### Task 11: README + Definition-of-Done wrap

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a README section**

Insert after the "Quick Start → Start backend" section a new H3 **"Run as a macOS menu bar app (launch at login)"** documenting: prerequisites (Xcode CLT, colima, Docker, Tailscale), `bash macos/install.sh`, what gets installed (`~/Library/LaunchAgents/com.nexus.stack.plist`, `com.nexus.menubar.plist`, `/Applications/Nexus.app`, `~/.nexus/menubar.json`, logs in `~/.nexus/logs/`), the menu actions, the Stop-All semantics (colima + tailscale left up), `scripts/nexus-setup.sh` re-run after dependency changes, and `bash macos/uninstall.sh`. State explicitly that M1 install is not yet covered.

- [ ] **Step 2: Run the full test suites (regression gate)**

Run:
```bash
cd macos/Nexus && swift test && cd -
bash scripts/tests/test_nexus_lib.sh
cd backend && python -m pytest -q && cd -
```
Expected: Swift tests pass; bash tests exit 0; backend suite passes (untouched).

- [ ] **Step 3: Frontend build check (Definition of Done)**

Per CLAUDE.md DoD: frontend was NOT changed, so a rebuild is not strictly required; the build is still exercised by `nexus-setup.sh` in Task 10. State this explicitly in the PR. (If you want belt-and-suspenders: `cd frontend && npm run build`.)

- [ ] **Step 4: Commit + push**

```bash
git add README.md
git commit -m "docs: document macOS menu bar app and launch-at-login

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git push origin main
```

- [ ] **Step 5: Note deferred M1 deploy**

In the PR/commit body, state explicitly: **M1 redeploy deferred** — this iteration is M5-only per the design; M1 install is a follow-up (parameterize `install.sh` for SSH + Homebrew/node PATH).

---

## Self-Review

**Spec coverage:**
- Architecture (agent + thin controller): Tasks 7, 8, 9. ✓
- Full-stack scope (colima→Caddy→tailscale→backend): `nexus-lib.sh` + `nexus-launch.sh` (Tasks 5, 6), probes (Tasks 2, 4). ✓
- launchd-backed supervision (RunAtLoad + KeepAlive): Task 7 stack plist; crash-restart verified Task 10 Step 5. ✓
- At-login (LaunchAgent, not LaunchDaemon): Task 7. ✓
- Status dots / per-component probes: Tasks 2, 4, 8. ✓
- Controls (Start/Stop/Restart, Open, Launch-at-login, Logs): Task 8. ✓
- Stop-All leaves colima+tailscale up: Task 8 `stopAll()`; documented Task 11. ✓
- nexus-setup vs nexus-launch split (fast hot path): Task 6. ✓
- Detected tool paths (tailscale app-bundle path, Docker Desktop docker): Task 5 template + Task 9 detection. ✓
- Ad-hoc signing, install/uninstall: Task 9. ✓
- README + DoD + M1 deferred: Task 11. ✓
- Error handling (bounded colima wait, missing venv/dist exit, probe timeouts): `nexus-launch.sh` + `ensure_colima` (Task 6/5), CommandRunner timeout + URLSession timeout (Tasks 3, 4). ✓
- Testing strategy (script tests, Swift unit tests, manual integration): Tasks 2–6, 10, 11. ✓

**Decision deviation from spec (intentional, noted):** spec mentioned `SMAppService` for the app's own login launch; the plan uses a dedicated `com.nexus.menubar` LaunchAgent instead, for reliability under ad-hoc signing and consistency with the stack agent. Captured in Task 7 Step 2.

**Placeholder scan:** no TBD/TODO; every code step contains full code; every command has expected output.

**Type consistency:** `ComponentStatus`/`ComponentState` (Task 1) used consistently in 2/4/8; `CommandRunning.run(_:cwd:timeout:)` finalized in Task 4 Step 4 and used in 8; `LaunchctlControl.start/stop/bootstrap` signatures (Task 3) match calls in Task 8; `ToolPaths` fields (Task 4) match install detection (Task 9) and paths.sh template (Task 5).
