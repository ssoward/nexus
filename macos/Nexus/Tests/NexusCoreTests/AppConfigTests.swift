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
