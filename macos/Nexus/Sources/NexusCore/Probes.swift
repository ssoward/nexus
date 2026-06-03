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
            [paths.docker, "compose", "ps", "--format", "json"],
            cwd: paths.repoPath, timeout: 5))
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
        final class Box: @unchecked Sendable { var value: Int? }
        let box = Box()
        let sem = DispatchSemaphore(value: 0)
        var req = URLRequest(url: URL(string: "http://127.0.0.1:8000/api/health")!)
        req.timeoutInterval = 3
        let task = URLSession.shared.dataTask(with: req) { _, resp, _ in
            box.value = (resp as? HTTPURLResponse)?.statusCode
            sem.signal()
        }
        task.resume()
        // On timeout, cancel the task so the completion handler cannot write box.value
        // after we've already read it (the semaphore's happens-before only holds on .success).
        if sem.wait(timeout: .now() + 4) == .timedOut {
            task.cancel()
            return StatusParsers.backend(httpStatus: nil)
        }
        return StatusParsers.backend(httpStatus: box.value)
    }
}
