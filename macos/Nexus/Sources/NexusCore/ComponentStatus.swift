public enum ComponentState: String, Sendable, Hashable {
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
