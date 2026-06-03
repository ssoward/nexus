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
        // Match ":443" (colon-prefixed) so we don't false-positive on ports like
        // 4430 or relay hostnames that merely contain the digits "443".
        let present = exitCode == 0 && stdout.contains(expectedTarget) && stdout.contains(":443")
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
