#!/usr/bin/env python3
"""Capture actual Debug simulator screens without changing simulator appearance settings."""
import argparse
import os
from pathlib import Path
import subprocess
import time
from PIL import Image, ImageStat

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = "app.heartecho.designpreview"
SCREENS = [
    ("summary", "light"),
    ("recordings", "light"),
    ("care", "light"),
    ("prepare", "light"),
    ("record", "light"),
    ("record-finished", "light"),
    ("result", "light"),
    ("assistant-chat", "light"),
    ("summary", "dark"),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", required=True, help="A booted iPhone simulator UUID")
    parser.add_argument("--screen", action="append", choices=sorted({screen for screen, _ in SCREENS}), help="Capture selected screens; may be repeated")
    parser.add_argument("--appearance", choices=("light", "dark"), default="light", help="Appearance for selected screens")
    parser.add_argument("--output-dir", type=Path, help="Screenshot folder; defaults to the project's Previews folder")
    parser.add_argument("--skip-install", action="store_true", help="Reuse the same build already installed by a previous capture")
    args = parser.parse_args()
    app = ROOT / "build/Build/Products/Debug-iphonesimulator/HeartEchoApp.app"
    if not app.exists():
        parser.error("Build the Debug simulator app first; see README.md.")
    output = args.output_dir or ROOT / "Previews"
    output.mkdir(parents=True, exist_ok=True)

    def simctl(*arguments, env=None):
        subprocess.run(["xcrun", "simctl", *arguments], check=True, env=env, timeout=180)

    if not args.skip_install:
        simctl("install", args.device, str(app))
    selected = [(screen, args.appearance) for screen in args.screen] if args.screen else SCREENS
    for screen, appearance in selected:
        env = os.environ.copy()
        env["SIMCTL_CHILD_HEART_ECHO_PREVIEW_SCREEN"] = "record" if screen == "record-finished" else screen
        env["SIMCTL_CHILD_HEART_ECHO_PREVIEW_APPEARANCE"] = appearance
        simctl("launch", "--terminate-running-process", args.device, BUNDLE, env=env)
        if screen == "record-finished":
            # Exercise the real 20-second preview timer and its automatic handoff.
            time.sleep(30)
        destination = output / f"{screen}-{appearance}.png"
        for attempt in range(12):
            time.sleep(3)
            simctl("io", args.device, "screenshot", str(destination))
            # Cold launches can show a blank launch screen for several seconds.
            # Analyze the central content, excluding the status and tab bars.
            with Image.open(destination) as screenshot:
                width, height = screenshot.size
                center = screenshot.convert("L").crop((width * .1, height * .2, width * .9, height * .85))
                if ImageStat.Stat(center).stddev[0] > 12:
                    break
        else:
            raise RuntimeError(f"The {screen} screen did not finish rendering.")
        print(f"Captured {destination.name}", flush=True)

    # Leave the app in its regular launch state, following system appearance.
    simctl("launch", "--terminate-running-process", args.device, BUNDLE)


if __name__ == "__main__":
    main()
