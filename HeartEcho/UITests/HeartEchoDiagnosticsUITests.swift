import XCTest

final class HeartEchoDiagnosticsUITests: XCTestCase {
    func testScreensAndPermissionDenied() {
        let app = XCUIApplication()
        continueAfterFailure = false
        app.launchArguments = ["--diagnostics-ui"]; app.launch()
        XCTAssertTrue(app.buttons["Start listening"].waitForExistence(timeout: 30))
        XCTAssertFalse(app.buttons["Stop & hear recent audio"].isEnabled)
        let measure = XCTAttachment(screenshot: app.screenshot()); measure.name = "Measure"; measure.lifetime = .keepAlways; add(measure)
        reveal(app.buttons["participant"], in: app)
        XCTAssertEqual(app.switches["saveTestAudio"].value as? String, "0")
        app.buttons["participant"].tap(); app.buttons["B · friend"].tap()
        reveal(app.switches["friendConsent"], in: app)
        XCTAssertEqual(app.switches["friendConsent"].value as? String, "0")
        reveal(app.buttons["Start 90-second diagnostic test"], in: app, below: false)
        XCTAssertFalse(app.buttons["Start 90-second diagnostic test"].isEnabled)
        reveal(app.buttons["participant"], in: app)
        app.buttons["participant"].tap(); app.buttons["A · me"].tap()
        app.tabBars.buttons["Compare"].tap()
        XCTAssertTrue(app.navigationBars["Watch comparison"].exists)
        XCTAssertTrue(app.staticTexts["Watch sensor"].firstMatch.exists)
        let auto = app.switches["autoCompare"]
        reveal(auto, in: app); XCTAssertEqual(auto.value as? String, "1")
        print("AUTO_COMPARE_BEFORE", auto.debugDescription)
        let control = XCTAttachment(screenshot: app.screenshot()); control.name = "Auto comparison before tap"; control.lifetime = .keepAlways; add(control)
        auto.switches.firstMatch.tap()
        let changed = XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == %@", "0"), object: auto)
        XCTAssertEqual(XCTWaiter.wait(for: [changed], timeout: 10), .completed)
        auto.switches.firstMatch.tap()
        reveal(app.buttons["Pair reading"], in: app)
        XCTAssertFalse(app.buttons["Pair reading"].isEnabled)
        reveal(app.staticTexts["Session comparison · 0 pairs"], in: app)
        XCTAssertTrue(app.staticTexts["Session comparison · 0 pairs"].exists)
        let compare = XCTAttachment(screenshot: app.screenshot()); compare.name = "Compare"; compare.lifetime = .keepAlways; add(compare)
        app.tabBars.buttons["Measure"].tap()
        reveal(app.buttons["position"], in: app)
        let previous = app.buttons["position"].label
        reveal(app.buttons["Try next position"], in: app); app.buttons["Try next position"].tap()
        reveal(app.buttons["position"], in: app)
        XCTAssertNotEqual(app.buttons["position"].label, previous)
        reveal(app.buttons["Start listening"], in: app, below: false)
        app.buttons["Start listening"].tap()
        XCTAssertTrue(app.buttons["Open microphone settings"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["Start listening"].isEnabled)
        reveal(app.buttons["Clear audio & comparisons"], in: app)
        app.buttons["Clear audio & comparisons"].tap()
        XCTAssertFalse(app.buttons["Open microphone settings"].exists)
    }
    func testFiveCyclePlanSurvivesRelaunch() {
        let app = XCUIApplication(); app.launchArguments = ["--diagnostics-ui"]; app.launch()
        let setup = app.buttons["Set up final validation · 2 cycles"]
        reveal(setup, in: app); setup.tap()
        XCTAssertTrue(app.staticTexts["Cycle 1/2 · Test 1/8 · Quiet"].exists)
        app.terminate(); app.launchArguments = ["--diagnostics-ui"]; app.launch()
        reveal(app.staticTexts["Cycle 1/2 · Test 1/8 · Quiet"], in: app)
        XCTAssertTrue(app.buttons["Ready · start test 1/8"].exists)
        reveal(app.buttons["End test plan"], in: app); app.buttons["End test plan"].tap()
        XCTAssertTrue(app.buttons["Set up final validation · 2 cycles"].exists)
    }
    func testPublicMurmurSamplesWithoutMicrophone() {
        let app = XCUIApplication(); app.launchArguments = ["--diagnostics-ui"]; app.launch()
        app.tabBars.buttons["Murmur"].tap()
        XCTAssertTrue(app.navigationBars["Murmur"].exists)
        XCTAssertTrue(app.staticTexts["This project is a prototype and is not medical advice."].exists)
        // Fixed public samples retain their annotations; expected model outputs can differ.
        for (sample, reference, title) in [("absent", "no murmur annotated", "Unsure"), ("present", "murmur annotated", "Murmur-like pattern"), ("unknown", "uncertain annotation", "Unsure")] {
            let button = app.buttons["murmur.sample.\(sample)"]
            for _ in 0..<10 where !button.isHittable { app.swipeDown() }
            XCTAssertTrue(button.isEnabled); button.tap()
            let result = app.staticTexts["murmur.result"]
            // Form creates offscreen result rows lazily; scroll them into view first.
            for _ in 0..<10 where !result.isHittable { app.swipeUp() }
            XCTAssertTrue(result.waitForExistence(timeout: 30))
            reveal(result, in: app)
            let fresh = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS %@", "reference: " + reference), object: app.staticTexts["murmur.source"])
            XCTAssertEqual(XCTWaiter.wait(for: [fresh], timeout: 30), .completed)
            XCTAssertFalse(app.staticTexts["murmur.error"].exists)
            XCTAssertEqual(result.label, title)
        }
        let shot = XCTAttachment(screenshot: app.screenshot()); shot.name = "Murmur research"; shot.lifetime = .keepAlways; add(shot)
        app.tabBars.buttons["Measure"].tap()
        XCTAssertTrue(app.buttons["Start listening"].exists)
    }
    private func reveal(_ element: XCUIElement, in app: XCUIApplication, below: Bool = true) {
        for _ in 0..<12 {
            if element.exists && !element.frame.isEmpty && element.frame.minY >= 150 && element.frame.maxY <= app.frame.maxY - 110 { return }
            if element.exists && !element.frame.isEmpty {
                if element.frame.minY < 150 { app.swipeDown() } else { app.swipeUp() }
            } else if below { app.swipeUp() } else { app.swipeDown() }
        }
        XCTAssertTrue(element.exists, "The control must exist after scrolling")
    }
}
