import Foundation

public struct AppConfig: Sendable, Equatable {
    public let hostUrl: String
    public let repoPath: String
    public let caddyHostPort: String

    public init(hostUrl: String, repoPath: String, caddyHostPort: String) {
        self.hostUrl = hostUrl
        self.repoPath = repoPath
        self.caddyHostPort = caddyHostPort
    }

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
