#!/usr/bin/env python3
"""Record dashboard demo as video → convert to GIF."""

import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent.parent
OUTPUT_VIDEO_DIR = ROOT / "assets" / "_video"
OUTPUT_GIF = ROOT / "assets" / "dashboard.gif"

DASHBOARD_URL = "http://127.0.0.1:8420/dashboard.html"
VIEWPORT = {"width": 1200, "height": 900}


def record():
    OUTPUT_VIDEO_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport=VIEWPORT,
            record_video_dir=str(OUTPUT_VIDEO_DIR),
            record_video_size=VIEWPORT,
        )
        page = context.new_page()

        # Load dashboard
        page.goto(DASHBOARD_URL, wait_until="networkidle")
        page.wait_for_timeout(2000)  # Let entrance animations finish

        # Trigger demo via JS (button may be hidden in headless)
        page.evaluate("runDemo()")
        print("Demo started...")

        # Wait for demo to complete (~20s) + buffer
        page.wait_for_timeout(24000)
        print("Demo finished.")

        # Small pause at the end
        page.wait_for_timeout(1000)

        # Close to finalize video
        video_path = page.video.path()
        context.close()
        browser.close()

    print(f"Video saved: {video_path}")
    return video_path


def to_gif(video_path: str):
    """Convert video to optimized GIF using ffmpeg.

    Trims idle intro/outro, scales to 720px, 8fps, 96 colors for ~3-5MB output.
    """
    palette = OUTPUT_VIDEO_DIR / "palette.png"

    # Trim: skip first 2s (idle) and last 3s (idle), keep demo action
    trim_filter = "trim=start=2:end=24,setpts=PTS-STARTPTS,"
    scale_filter = f"{trim_filter}fps=8,scale=720:-1:flags=lanczos"

    # Generate palette
    subprocess.run([
        "ffmpeg", "-y", "-i", str(video_path),
        "-vf", f"{scale_filter},palettegen=max_colors=96:stats_mode=diff",
        str(palette),
    ], capture_output=True)

    # Apply palette to create GIF
    subprocess.run([
        "ffmpeg", "-y", "-i", str(video_path), "-i", str(palette),
        "-lavfi", f"{scale_filter}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3",
        str(OUTPUT_GIF),
    ], capture_output=True)

    # Cleanup
    palette.unlink(missing_ok=True)
    for f in OUTPUT_VIDEO_DIR.glob("*.webm"):
        f.unlink()
    OUTPUT_VIDEO_DIR.rmdir()

    size_mb = OUTPUT_GIF.stat().st_size / (1024 * 1024)
    print(f"GIF saved: {OUTPUT_GIF} ({size_mb:.1f}MB)")
    return str(OUTPUT_GIF)


if __name__ == "__main__":
    video = record()
    gif = to_gif(video)
    print(f"Done! {gif}")
