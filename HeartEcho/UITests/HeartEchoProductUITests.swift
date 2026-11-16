import XCTest

@MainActor final class HeartEchoProductUITests: XCTestCase {
    func testRealSampleHistoryAndExplanation() {
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["--ui-reset-recordings", "--developer-mode", "--ui-reset-care"]; app.launch()
        XCTAssertTrue(app.descendants(matching: .any)["empty-history"].firstMatch.waitForExistence(timeout: 30))
        XCTAssertFalse(app.staticTexts["72"].exists)
        app.buttons["record-heart-sounds"].tap()
        XCTAssertTrue(app.buttons["start-real-recording"].waitForExistence(timeout: 10))
        let audio = app.switches["keep-recording-audio"]
        reveal(audio, in: app); XCTAssertEqual(audio.value as? String, "0")
        let sample = app.buttons["product.sample.present"]; reveal(sample, in: app); sample.tap()
        let resultTitle = app.staticTexts["recording-result-title"]
        let resultAppeared = resultTitle.waitForExistence(timeout: 45)
        if !resultAppeared { diagnostics(app, "Public sample result did not appear") }
        XCTAssertTrue(resultAppeared)
        XCTAssertEqual(resultTitle.label, "Murmur-like pattern")
        XCTAssertTrue(app.staticTexts["recording-result-example"].exists)
        XCTAssertTrue(app.staticTexts["recording-result-reminder"].label.contains("can be wrong"))
        XCTAssertFalse(app.textFields["assistant-message-input"].exists)
        screenshot(app, "Result before care chat")
        app.buttons["result-find-care"].tap()
        let explanation = app.staticTexts["actual-result-explanation"]
        XCTAssertTrue(explanation.waitForExistence(timeout: 10))
        XCTAssertTrue(explanation.label.contains("Murmur-like pattern"))
        XCTAssertTrue(explanation.label.contains("example"))
        let message = app.textFields["assistant-message-input"]
        XCTAssertTrue(message.waitForExistence(timeout: 10)); message.tap(); message.typeText("What does this result mean?")
        app.buttons["Send message"].tap()
        XCTAssertTrue(app.staticTexts["What does this result mean?"].waitForExistence(timeout: 10))
        app.buttons["BackButton"].tap()
        app.buttons["Close"].tap()
        app.tabBars.buttons["Care"].tap()
        XCTAssertTrue(app.staticTexts["What does this result mean?"].waitForExistence(timeout: 10), "The Care tab opens the same conversation")
        app.terminate(); app.launchArguments = []; app.launch()
        app.tabBars.buttons["Recordings"].tap()
        XCTAssertTrue(app.staticTexts["Public present sample"].waitForExistence(timeout: 15))
        app.staticTexts["Public present sample"].tap()
        XCTAssertEqual(app.staticTexts["saved-murmur-result"].label, "Murmur-like pattern")
        let explain = app.buttons["explain-saved-result"]; reveal(explain, in: app); explain.tap()
        XCTAssertTrue(explanation.waitForExistence(timeout: 10))
        XCTAssertTrue(explanation.label.contains("Murmur-like pattern"))
        app.navigationBars.buttons.element(boundBy: 0).tap()
        let remove = app.buttons["delete-recording"]; reveal(remove, in: app); remove.tap(); app.buttons["Delete"].tap()
        XCTAssertTrue(app.staticTexts["empty-recordings"].waitForExistence(timeout: 10))
        app.terminate(); app.launch()
        app.tabBars.buttons["Recordings"].tap()
        XCTAssertTrue(app.staticTexts["empty-recordings"].exists)
    }
    func testPermissionDenialCreatesNoSuccess() {
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["--ui-reset-recordings", "--developer-mode"]; app.launch()
        app.buttons["record-heart-sounds"].tap()
        let start = app.buttons["start-real-recording"]; XCTAssertTrue(start.waitForExistence(timeout: 10)); reveal(start, in: app); start.tap()
        XCTAssertTrue(app.staticTexts["capture-error"].waitForExistence(timeout: 20))
        XCTAssertFalse(app.staticTexts["actual-result-explanation"].exists)
        app.buttons["Close"].tap(); app.tabBars.buttons["Recordings"].tap()
        XCTAssertTrue(app.staticTexts["empty-recordings"].exists)
    }
    func testUnsureExampleStaysUnsure() {
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["--ui-reset-recordings", "--developer-mode"]; app.launch()
        app.buttons["record-heart-sounds"].tap()
        let sample = app.buttons["product.sample.unknown"]; XCTAssertTrue(app.buttons["start-real-recording"].waitForExistence(timeout: 10)); reveal(sample, in: app); sample.tap()
        let title = app.staticTexts["recording-result-title"]
        XCTAssertTrue(title.waitForExistence(timeout: 45))
        XCTAssertEqual(title.label, "Uncertain")
        let explanation = app.staticTexts["recording-result-explanation"]
        XCTAssertTrue(explanation.label.contains("could not give a clear result"))
        XCTAssertFalse(explanation.label.contains("extra sound may be present"))
        XCTAssertFalse(app.textFields["assistant-message-input"].exists)
        XCTAssertTrue(app.buttons["result-find-care"].exists)
        screenshot(app, "Unsure remains unsure")
    }
    func testTextSummaryShareFromResultAndSavedHistory() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--consumer-mode", "--ui-reset-recordings", "--ui-reset-care"]
        app.launch()
        let examples = app.buttons["try-public-example"]
        XCTAssertTrue(examples.waitForExistence(timeout: 30)); examples.tap()
        let sample = app.buttons["product.sample.present"]
        XCTAssertTrue(sample.waitForExistence(timeout: 10)); reveal(sample, in: app); sample.tap()
        let result = app.staticTexts["recording-result-title"]
        XCTAssertTrue(result.waitForExistence(timeout: 45))
        XCTAssertEqual(result.label, "Murmur-like pattern")

        let immediateShare = app.buttons["result-share-summary"]
        reveal(immediateShare, in: app)
        XCTAssertTrue(immediateShare.isEnabled)
        immediateShare.tap()
        dismissTextShareSheet(in: app, screenshotName: "Share public result summary without sending")
        XCTAssertTrue(result.exists, "Dismissing sharing keeps the analyzed result")

        app.buttons["Close"].tap()
        app.tabBars.buttons["Recordings"].tap()
        let row = app.staticTexts["Public present sample"]
        XCTAssertTrue(row.waitForExistence(timeout: 10)); row.tap()
        let savedResult = app.staticTexts["saved-murmur-result"]
        XCTAssertTrue(savedResult.waitForExistence(timeout: 10))
        XCTAssertEqual(savedResult.label, "Murmur-like pattern")
        let savedShare = app.buttons["saved-share-summary"]
        reveal(savedShare, in: app)
        XCTAssertTrue(savedShare.isEnabled)
        savedShare.tap()
        dismissTextShareSheet(in: app, screenshotName: "Share saved result summary without sending")
        XCTAssertTrue(savedResult.waitForExistence(timeout: 10), "Dismissing sharing returns to the saved result")
        XCTAssertEqual(savedResult.label, "Murmur-like pattern", "Sharing does not change the saved outcome")

        app.navigationBars.buttons.element(boundBy: 0).tap()
        XCTAssertTrue(row.waitForExistence(timeout: 10))
        XCTAssertEqual(app.staticTexts.matching(identifier: "Public present sample").count, 1,
                       "Opening and cancelling sharing must not create extra recordings")
    }
    func testDeveloperSwitchPersistsAndKeepsPublicExamples() {
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["--consumer-mode", "--ui-reset-recordings"]; app.launch()
        app.buttons["Settings"].tap()
        let mode = app.switches["developer-mode"]; XCTAssertTrue(mode.waitForExistence(timeout: 10))
        XCTAssertEqual(mode.value as? String, "0")
        mode.switches.firstMatch.tap(); XCTAssertEqual(mode.value as? String, "1")
        app.buttons["Done"].tap(); reveal(app.buttons["open-diagnostics"], in: app)
        app.terminate(); app.launchArguments = []; app.launch()
        app.buttons["Settings"].tap(); XCTAssertEqual(mode.value as? String, "1")
        mode.switches.firstMatch.tap(); screenshot(app, "Consumer mode in Settings"); app.buttons["Done"].tap()
        for _ in 0..<3 { app.swipeUp() }
        XCTAssertFalse(app.buttons["open-diagnostics"].exists)
        for _ in 0..<4 where !app.buttons["record-heart-sounds"].isHittable { app.swipeDown() }
        app.buttons["record-heart-sounds"].tap()
        for _ in 0..<3 { app.swipeUp() }
        XCTAssertTrue(app.buttons["product.sample.present"].exists)
        screenshot(app, "Consumer recording")
    }
    private func reveal(_ element: XCUIElement, in app: XCUIApplication) {
        for _ in 0..<12 {
            if element.exists && element.isHittable && element.frame.minY >= 150 && element.frame.maxY <= app.frame.maxY - 110 { return }
            if element.exists && element.frame.minY < 150 { app.swipeDown() } else { app.swipeUp() }
        }
        XCTAssertTrue(element.exists && element.isEnabled && element.isHittable, "The control must be visible and enabled before tapping")
    }
    private func dismissTextShareSheet(in app: XCUIApplication, screenshotName: String) {
        // The observed iOS 27 share sheet exposes ActivityListView without a
        // visible Close button. Never choose a recipient or sharing action.
        let activity = app.otherElements["ActivityListView"].firstMatch
        let presented = activity.waitForExistence(timeout: 10)
        if !presented { diagnostics(app, "System share sheet did not appear") }
        XCTAssertTrue(presented, "Share Result Summary must open the system share sheet")
        XCTAssertTrue(activity.navigationBars["Heart Echo result summary"].waitForExistence(timeout: 20),
                      "The system must finish presenting the actual summary preview")
        screenshot(app, screenshotName)
        let scopedClose = activity.buttons["Close"].firstMatch
        let dismissRegion = app.otherElements["PopoverDismissRegion"].firstMatch
        if scopedClose.exists && scopedClose.isHittable {
            scopedClose.tap()
        } else if dismissRegion.exists && activity.frame.minY > app.frame.minY + 100 {
            // iOS can present this as a popover, which closes by tapping its
            // system dismiss region outside the card, rather than dragging.
            let point = CGPoint(x: activity.frame.midX, y: activity.frame.minY - 24)
            XCTAssertTrue(dismissRegion.frame.contains(point))
            XCTAssertFalse(activity.frame.contains(point))
            dismissRegion.coordinate(withNormalizedOffset: .zero)
                .withOffset(CGVector(dx: point.x - dismissRegion.frame.minX,
                                     dy: point.y - dismissRegion.frame.minY)).tap()
        } else {
            // Drag from the sheet's top, away from its recipient/action rows.
            // This exercises the system's interactive dismissal instead of
            // assuming an OS-specific button label or tapping an action.
            let top = activity.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.01))
            let bottom = activity.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.98))
            top.press(forDuration: 0.1, thenDragTo: bottom)
        }
        let dismissed = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: activity)
        let didDismiss = XCTWaiter.wait(for: [dismissed], timeout: 10) == .completed
        if !didDismiss { diagnostics(app, "System share sheet did not dismiss") }
        XCTAssertTrue(didDismiss, "The share sheet must close without selecting a destination or sending anything")
    }
    private func diagnostics(_ app: XCUIApplication, _ name: String) {
        SubmissionEvidence.capture(app, name: name, test: self, includeHierarchy: true)
    }
    private func screenshot(_ app: XCUIApplication, _ name: String) {
        SubmissionEvidence.capture(app, name: name, test: self)
    }
}
