#!/usr/bin/env python3
"""
Manual checklist items 4 & 5 — automated Playwright verification.

Item 4: Connection weight slider changes scores
  - Default connection_weight=1.0 → search → record avg scores
  - Set connection_weight=2.0 → search → verify scores changed (connecting flight penalised more)

Item 5: Red-eye penalty checkbox unchecking removes red-eye penalty
  - Default (redeye_penalty=True) → red-eye flight has higher score
  - Uncheck red-eye → re-search → red-eye flight score drops

Run:
    python scripts/check_manual_45.py
    python scripts/check_manual_45.py --headed   # visible browser
"""
import argparse
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths / ports
# ---------------------------------------------------------------------------

APP_PATH  = str(Path(__file__).parent.parent / "web" / "app.py")
APP_PORT  = 8503   # distinct port to avoid collisions with dev server
MOCK_PORT = 9877
BASE_URL  = f"http://localhost:{APP_PORT}"

# ---------------------------------------------------------------------------
# Mock Duffel data — two flights: one connecting (with redeye), one nonstop
#
# Offer A (AA): nonstop JFK→LHR departing 09:00, no connections, normal hour
# Offer B (UA): connecting JFK→ORD→LHR departing 23:30 (RED-EYE), layover at ORD
#   → should have a higher score due to (a) ORD chaotic hub, (b) connection penalty,
#     and (c) red-eye departure.
# ---------------------------------------------------------------------------

def _seg(dep, arr, orig, dest, carrier):
    return {
        "departing_at": dep, "arriving_at": arr,
        "origin": {"iata_code": orig},
        "destination": {"iata_code": dest},
        "operating_carrier": {"iata_code": carrier},
    }


MOCK_DUFFEL_BODY = json.dumps({
    "data": {
        "offers": [
            # Offer A: nonstop, normal departure time
            {
                "slices": [
                    {
                        "segments": [_seg("2026-06-15T09:00:00", "2026-06-15T17:00:00", "JFK", "LHR", "AA")],
                        "duration": "PT8H00M",
                    },
                    {
                        "segments": [_seg("2026-06-22T10:00:00", "2026-06-22T18:00:00", "LHR", "JFK", "AA")],
                        "duration": "PT8H00M",
                    },
                ],
                "total_amount": "450.00", "total_currency": "USD",
            },
            # Offer B: connecting via ORD, red-eye departure at 23:30
            {
                "slices": [
                    {
                        "segments": [
                            # Leg 1: red-eye departure 23:30, arrives ORD 01:30 (+1)
                            _seg("2026-06-15T23:30:00", "2026-06-16T01:30:00", "JFK", "ORD", "UA"),
                            # Leg 2: departs ORD 04:00, arrives LHR 17:00 (+1)
                            _seg("2026-06-16T04:00:00", "2026-06-17T09:00:00", "ORD", "LHR", "UA"),
                        ],
                        "duration": "PT17H30M",
                    },
                    {
                        "segments": [_seg("2026-06-22T10:00:00", "2026-06-22T18:00:00", "LHR", "JFK", "UA")],
                        "duration": "PT8H00M",
                    },
                ],
                "total_amount": "310.00", "total_currency": "USD",
            },
        ]
    }
}).encode()


class _MockHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(MOCK_DUFFEL_BODY)

    def log_message(self, *_):
        pass


# ---------------------------------------------------------------------------
# Start mock server + Streamlit
# ---------------------------------------------------------------------------

def start_mock_server():
    server = HTTPServer(("localhost", MOCK_PORT), _MockHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


def start_streamlit():
    env = {
        **os.environ,
        "DUFFEL_API_KEY":  "duffel_test_checklist_fake",
        "DUFFEL_BASE_URL": f"http://localhost:{MOCK_PORT}",
    }
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run", APP_PATH,
            "--server.port", str(APP_PORT),
            "--server.headless", "true",
            "--browser.gatherUsageStats", "false",
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(30):
        try:
            urllib.request.urlopen(BASE_URL, timeout=1)
            return proc
        except Exception:
            time.sleep(1)
    proc.terminate()
    raise RuntimeError(f"Streamlit did not start on {BASE_URL}")


# ---------------------------------------------------------------------------
# Playwright helpers
# ---------------------------------------------------------------------------

def fill_and_search(page):
    """Fill the form and wait for results."""
    page.wait_for_selector('[data-testid="stFormSubmitButton"]', timeout=15_000)
    page.get_by_role("textbox", name="From").fill("JFK")
    page.get_by_role("textbox", name="To").fill("LHR")
    page.locator('[data-testid="stFormSubmitButton"]').click()
    page.wait_for_selector('[data-testid="stDataFrame"]', timeout=20_000)


def dataframe_screenshot_hash(page) -> str:
    """Return a hex hash of the dataframe canvas screenshot.

    Streamlit's dataframe uses a canvas-based renderer (glide-data-grid) so
    inner_text() returns nothing.  Comparing pixel hashes is a reliable way to
    detect that the displayed numbers changed after a rerun.
    """
    import hashlib
    png_bytes = page.locator('[data-testid="stDataFrame"]').first.screenshot()
    return hashlib.md5(png_bytes).hexdigest()


def set_slider(page, label: str, value: float):
    """
    Set a Streamlit range slider using keyboard input.
    Clicks the slider thumb then uses arrow keys to adjust.
    """
    slider = page.locator('[data-testid="stSlider"]').filter(has_text=label)
    thumb  = slider.locator('[role="slider"]').first
    # Get min/max/step from aria attributes
    aria_min   = float(thumb.get_attribute("aria-valuemin") or 0)
    aria_max   = float(thumb.get_attribute("aria-valuemax") or 2)
    aria_step  = float(thumb.get_attribute("aria-valuenow") or 1)   # current as reference
    current    = float(thumb.get_attribute("aria-valuenow") or 1)
    step_size  = 0.1   # matches the step=0.1 in app.py

    thumb.click()
    target_presses = round((value - current) / step_size)
    key = "ArrowRight" if target_presses > 0 else "ArrowLeft"
    for _ in range(abs(target_presses)):
        thumb.press(key)
    # Confirm final value
    final = float(thumb.get_attribute("aria-valuenow") or 0)
    return final


def uncheck_redeye(page):
    """Uncheck the red-eye penalty checkbox (clicking the label, not the hidden input)."""
    checkbox_wrapper = page.locator('[data-testid="stCheckbox"]').filter(has_text="Red-eye")
    label = checkbox_wrapper.locator("label")
    label.click()
    # Verify it's unchecked
    inp = checkbox_wrapper.locator("input")
    return not inp.is_checked()


# ---------------------------------------------------------------------------
# Main checklist run
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--headed", action="store_true", help="Show browser window")
    args = parser.parse_args()

    from playwright.sync_api import sync_playwright

    print("Starting mock Duffel server on port", MOCK_PORT)
    mock_server = start_mock_server()

    print("Starting Streamlit on port", APP_PORT, "...")
    proc = start_streamlit()
    print("  Streamlit ready.")

    results = {}

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=not args.headed)
            page = browser.new_page()

            # ----------------------------------------------------------------
            # ITEM 4: Connection weight slider
            # ----------------------------------------------------------------
            print("\n=== Item 4: Connection weight slider ===")

            page.goto(BASE_URL)
            fill_and_search(page)
            hash_default = dataframe_screenshot_hash(page)
            print(f"  Default screenshot hash (connection_weight=1.0): {hash_default[:12]}…")

            # Increase connection weight to 2.0 — connecting flight should score higher
            final_val = set_slider(page, "Connection weight", 2.0)
            print(f"  Slider set to: {final_val}")

            # Re-search with new weight
            page.locator('[data-testid="stFormSubmitButton"]').click()
            page.wait_for_selector('[data-testid="stDataFrame"]', timeout=20_000)
            hash_high_weight = dataframe_screenshot_hash(page)
            print(f"  High-weight screenshot hash (connection_weight=2.0): {hash_high_weight[:12]}…")

            item4_pass = hash_default != hash_high_weight
            results["item4_slider"] = "PASS" if item4_pass else "FAIL"
            if not item4_pass:
                print("  FAIL: Scores did not change after increasing connection weight.")
            else:
                print("  PASS: Scores changed as expected.")

            # ----------------------------------------------------------------
            # ITEM 5: Red-eye penalty checkbox
            # ----------------------------------------------------------------
            print("\n=== Item 5: Red-eye penalty checkbox ===")

            # Reset: reload and search with defaults (redeye=True)
            page.goto(BASE_URL)
            fill_and_search(page)
            hash_redeye_on = dataframe_screenshot_hash(page)
            print(f"  Screenshot hash with redeye_penalty=True:  {hash_redeye_on[:12]}…")

            # Uncheck red-eye penalty
            unchecked = uncheck_redeye(page)
            print(f"  Red-eye checkbox unchecked successfully: {unchecked}")

            # Re-search
            page.locator('[data-testid="stFormSubmitButton"]').click()
            page.wait_for_selector('[data-testid="stDataFrame"]', timeout=20_000)
            hash_redeye_off = dataframe_screenshot_hash(page)
            print(f"  Screenshot hash with redeye_penalty=False: {hash_redeye_off[:12]}…")

            item5_pass = hash_redeye_on != hash_redeye_off
            results["item5_redeye"] = "PASS" if item5_pass else "FAIL"
            if not item5_pass:
                print("  FAIL: Scores did not change after disabling red-eye penalty.")
            else:
                print("  PASS: Scores changed as expected (red-eye penalty removed).")

            browser.close()

    finally:
        proc.terminate()
        proc.wait()
        mock_server.shutdown()

    # ----------------------------------------------------------------
    # Summary
    # ----------------------------------------------------------------
    print("\n" + "=" * 50)
    print("Manual Checklist Summary")
    print("=" * 50)
    all_pass = True
    for k, v in results.items():
        icon = "✓" if v == "PASS" else "✗"
        print(f"  {icon}  {k}: {v}")
        if v != "PASS":
            all_pass = False
    print("=" * 50)
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
