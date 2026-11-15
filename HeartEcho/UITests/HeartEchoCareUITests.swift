import XCTest

@MainActor final class HeartEchoCareUITests: XCTestCase {
    func testCareSearchWithoutPairingOrScan() {
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["--consumer-mode", "--ui-reset-care"]; app.launch()
        app.tabBars.buttons["Care"].tap()
        let message = app.textFields["assistant-message-input"]; XCTAssertTrue(message.waitForExistence(timeout: 10))
        message.tap(); message.typeText("Find care in 94303")
        app.buttons["Send message"].tap()
        let listing = app.descendants(matching: .any)["live-care-listing"].firstMatch
        XCTAssertTrue(listing.waitForExistence(timeout: 60)); reveal(listing, in: app)
        XCTAssertTrue(app.buttons["assistant-connection-status"].label.contains("Public directories"))
        let shot = XCTAttachment(screenshot: app.screenshot()); shot.name = "Standalone iPhone public care search"; shot.lifetime = .keepAlways; add(shot)
    }
    func testPublicResultToLiveCareWithoutBPM() async throws {
        continueAfterFailure = false
        // Local setup API is loopback-only; credentials never enter screenshots/logs.
        let (data, response) = try await URLSession.shared.data(from: URL(string: "http://127.0.0.1:4318/api/demo-connection")!)
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200)
        let connection = try JSONSerialization.jsonObject(with: data) as! [String: String]
        let app = XCUIApplication(); app.launchArguments = ["--consumer-mode", "--ui-reset-recordings", "--ui-reset-care"]; app.launch()
        app.buttons["try-public-example"].tap()
        let sample = app.buttons["product.sample.present"]; reveal(sample, in: app); sample.tap()
        let result = app.staticTexts["recording-result-title"]
        XCTAssertTrue(result.waitForExistence(timeout: 45)); XCTAssertEqual(result.label, "Murmur-like pattern")
        XCTAssertFalse(app.textFields["assistant-message-input"].exists)
        app.buttons["result-find-care"].tap()
        let explanation = app.staticTexts["actual-result-explanation"]
        XCTAssertTrue(explanation.waitForExistence(timeout: 10))
        let connect = app.buttons["assistant-connection-status"]; XCTAssertTrue(connect.waitForExistence(timeout: 10)); connect.tap()
        let endpoint = app.textFields["care-endpoint"]; XCTAssertTrue(endpoint.waitForExistence(timeout: 10))
        XCTAssertTrue((endpoint.value as? String)?.hasPrefix("http://127.0.0.1:4318") == true)
        let code = app.secureTextFields["care-pair-code"]
        if app.alerts.buttons["Allow"].exists { app.alerts.buttons["Allow"].tap() }
        code.tap(); code.typeText(connection["pairing_code"]!)
        let pair = app.buttons["care-pair"]; reveal(pair, in: app); pair.tap()
        XCTAssertTrue(app.staticTexts["Care service connected"].waitForExistence(timeout: 15))
        app.buttons["Done"].tap()
        let consent = app.switches["assistant-summary-consent"]
        XCTAssertEqual(consent.value as? String, "0", "The recording summary remains optional")
        let message = app.textFields["assistant-message-input"]; message.tap(); message.typeText("Find care in 94303")
        app.buttons["Send message"].tap()
        let listing = app.descendants(matching: .any)["live-care-listing"].firstMatch
        XCTAssertTrue(listing.waitForExistence(timeout: 150)); reveal(listing, in: app)
        XCTAssertTrue(app.buttons["assistant-connection-status"].label.contains("Gemma-assisted"))
        let dental = app.staticTexts.matching(NSPredicate(format: "label MATCHES %@", "(?i).*\\bdent(?:al|istry|ists?)\\b.*"))
        XCTAssertFalse(dental.firstMatch.exists, "Heart-care results should not show sites explicitly named as dental")
        XCTAssertFalse(app.staticTexts["ILLUSTRATIVE LISTING"].exists)
        let shot = XCTAttachment(screenshot: app.screenshot()); shot.name = "Actual public result to live directory"; shot.lifetime = .keepAlways; add(shot)
    }
    private func reveal(_ element: XCUIElement, in app: XCUIApplication) {
        for _ in 0..<10 {
            if element.exists && element.isHittable && element.frame.minY > 120 && element.frame.maxY < app.frame.maxY-85 { return }
            if element.exists && element.frame.minY < 120 { app.swipeDown() } else { app.swipeUp() }
        }
        XCTAssertTrue(element.exists && element.isHittable)
    }
}
