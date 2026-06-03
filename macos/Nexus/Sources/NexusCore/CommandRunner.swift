import Foundation

public struct CommandResult: Sendable {
    public let stdout: String
    public let exitCode: Int32

    public init(stdout: String, exitCode: Int32) {
        self.stdout = stdout
        self.exitCode = exitCode
    }
}

public protocol CommandRunning: Sendable {
    /// Runs argv[0] with the rest as arguments. Returns stdout and exit code.
    /// Throws on launch failure. `timeout` seconds enforced via termination.
    /// `cwd` sets the working directory; nil leaves it inherited.
    func run(_ argv: [String], cwd: String?, timeout: TimeInterval) throws -> CommandResult
}

extension CommandRunning {
    public func run(_ argv: [String], timeout: TimeInterval) throws -> CommandResult {
        try run(argv, cwd: nil, timeout: timeout)
    }
}

public struct CommandRunner: CommandRunning {
    public init() {}

    /// stdout and stderr are merged into one stream. Several probed tools write their
    /// status to stderr (notably `colima status`), so capturing both is required for
    /// correct detection; the parsers are tolerant of the extra lines.
    /// NOTE: the merged stream is read only after the process exits/terminates, so a
    /// command writing more than the OS pipe buffer (~64KB) before exiting could
    /// deadlock. Acceptable here — all callers are short-lived probes with tiny output.
    public func run(_ argv: [String], cwd: String?, timeout: TimeInterval) throws -> CommandResult {
        precondition(!argv.isEmpty)
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: argv[0])
        proc.arguments = Array(argv.dropFirst())
        if let cwd { proc.currentDirectoryURL = URL(fileURLWithPath: cwd) }
        let pipe = Pipe()
        proc.standardOutput = pipe
        proc.standardError = pipe   // merge stderr (e.g. `colima status` writes there)
        try proc.run()

        let deadline = Date().addingTimeInterval(timeout)
        while proc.isRunning && Date() < deadline {
            usleep(50_000)  // 50ms
        }
        if proc.isRunning { proc.terminate() }

        // Blocks until the child closes the write end (natural exit or after SIGTERM).
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        proc.waitUntilExit()
        return CommandResult(stdout: String(decoding: data, as: UTF8.self),
                             exitCode: proc.terminationStatus)
    }
}
