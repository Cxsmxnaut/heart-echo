import XCTest

@MainActor final class HeartEchoSubmissionUITests: XCTestCase {
    func testRecordingCoachPreviewAtLargeTextSize() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--consumer-mode", "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
        app.launchEnvironment["HEART_ECHO_PREVIEW_SCREEN"] = "record"
        app.launchEnvironment["HEART_ECHO_PREVIEW_APPEARANCE"] = "dark"
        app.launch()
        let title = app.staticTexts["recording-guidance-title"]
        reveal(title, in: app)
        XCTAssertEqual(title.label, "Recording guide preview")
        XCTAssertTrue(app.staticTexts["recording-guidance-detail"].label.contains("microphone is off"))
        XCTAssertEqual(app.staticTexts["live-product-bpm"].label, "Microphone off")
        XCTAssertFalse(app.staticTexts["72 BPM"].exists)
        attach(app, "Recording coach — large text, microphone off")
    }

    func testPublicResultSharingAtLargeTextSize() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--consumer-mode", "--ui-reset-recordings", "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
        app.launch()
        let examples = app.buttons["try-public-example"]
        reveal(examples, in: app); examples.tap()
        let sample = app.buttons["product.sample.present"]
        reveal(sample, in: app); sample.tap()
        let title = app.staticTexts["recording-result-title"]
        XCTAssertTrue(title.waitForExistence(timeout: 45))
        XCTAssertEqual(title.label, "Murmur-like pattern")
        let share = app.buttons["result-share-summary"]
        reveal(share, in: app)
        XCTAssertGreaterThan(share.frame.height, 0)
        XCTAssertGreaterThanOrEqual(share.frame.minX, 0)
        XCTAssertLessThanOrEqual(share.frame.maxX, app.frame.maxX)
        attach(app, "Public result summary — large text")
    }

    private func reveal(_ element: XCUIElement, in app: XCUIApplication) {
        for _ in 0..<18 {
            let bounds = visibleBounds(in: app)
            if element.exists {
                let frame = element.frame
                if element.isHittable && frame.minY > bounds.top && frame.maxY < bounds.bottom { return }
                scroll(in: app, down: frame.minY <= bounds.top)
            } else {
                // SwiftUI can omit an offscreen view from the accessibility tree.
                // Scroll to instantiate it instead of waiting without moving.
                scroll(in: app, down: false)
            }
        }
        let visible: Bool
        if element.exists {
            let frame = element.frame
            let bounds = visibleBounds(in: app)
            visible = element.isHittable && frame.minY > bounds.top && frame.maxY < bounds.bottom
        } else {
            visible = false
        }
        if !visible {
            SubmissionEvidence.capture(app, name: "Control missing or offscreen after reveal", test: self,
                                       includeHierarchy: true)
        }
        XCTAssertTrue(visible, "The control must exist and be visibly hittable after scrolling")
    }

    private func visibleBounds(in app: XCUIApplication) -> (top: CGFloat, bottom: CGFloat) {
        let navigationBottom = app.navigationBars.allElementsBoundByIndex
            .filter(\.isHittable).map { $0.frame.maxY }.max() ?? 110
        let top = max(110, navigationBottom + 8)
        let care = app.buttons["result-find-care"]
        let bottom = care.exists ? min(app.frame.maxY - 100, care.frame.minY - 16) : app.frame.maxY - 100
        return (top, bottom)
    }

    private func scroll(in app: XCUIApplication, down: Bool) {
        // Full-screen swipes can jump past a large-text control in both
        // directions. A short drag with a held endpoint avoids that fling.
        let start = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: down ? 0.35 : 0.65))
        let end = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: down ? 0.60 : 0.40))
        start.press(forDuration: 0.1, thenDragTo: end, withVelocity: .slow, thenHoldForDuration: 0.15)
    }

    private func attach(_ app: XCUIApplication, _ name: String) {
        SubmissionEvidence.capture(app, name: name, test: self)
    }
}
