"""
tests/test_browser.py

Playwright end-to-end tests for web/app.py.

These complement the AppTest unit tests by exercising real browser interactions
that AppTest cannot simulate: row clicks on the canvas-based dataframe,
keyboard submission, and visual state after reruns.

Architecture:
  - A session-scoped mock HTTP server impersonates the Duffel API (server-side
    Python makes requests, so page.route() won't work — we need a real server).
  - DUFFEL_BASE_URL env var points the Streamlit process at the mock server.
  - A session-scoped Streamlit process serves the app on port 8502.

Coverage:
  - Search form submits on Enter key
  - Valid search produces a results table
  - Clicking a result row renders the per-factor breakdown (regression test)
  - Results table persists after row click (regression test)

Requirements (dev only):
    pip install pytest-playwright
    playwright install chromium

Run:
    pytest tests/test_browser.py
    pytest tests/test_browser.py -v --headed   # watch in a real browser
"""

import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths / ports
# ---------------------------------------------------------------------------

APP_PATH   = str(Path(__file__).parent.parent / "web" / "app.py")
APP_PORT   = 8502   # Streamlit — separate from the dev server on 8501
MOCK_PORT  = 9876   # Local Duffel mock
BASE_URL   = f"http://localhost:{APP_PORT}"

# ---------------------------------------------------------------------------
# Mock Duffel API response
# ---------------------------------------------------------------------------

def _seg(dep, arr, orig, dest, carrier):
    return {
        "departing_at": dep, "arriving_at": arr,
        "origin": {"iata_code": orig}, "destination": {"iata_code": dest},
        "operating_carrier": {"iata_code": carrier},
    }


MOCK_DUFFEL_BODY = json.dumps({
    "data": {
        "offers": [
            {
                "slices": [
                    {"segments": [_seg("2026-06-15T09:00:00", "2026-06-15T17:00:00", "JFK", "LHR", "BA")], "duration": "PT8H00M"},
                    {"segments": [_seg("2026-06-22T10:00:00", "2026-06-22T18:00:00", "LHR", "JFK", "BA")], "duration": "PT8H00M"},
                ],
                "total_amount": "450.00", "total_currency": "USD",
            },
            {
                "slices": [
                    {"segments": [_seg("2026-06-15T07:00:00", "2026-06-15T17:00:00", "JFK", "LHR", "AA")], "duration": "PT10H00M"},
                    {"segments": [_seg("2026-06-22T08:00:00", "2026-06-22T18:00:00", "LHR", "JFK", "AA")], "duration": "PT10H00M"},
                ],
                "total_amount": "310.00", "total_currency": "USD",
            },
        ]
    }
}).encode()


class _DuffelMockHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(MOCK_DUFFEL_BODY)

    def log_message(self, *_):
        pass  # suppress access log noise in test output


# ---------------------------------------------------------------------------
# Session fixtures: mock server + Streamlit process
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def mock_duffel_server():
    """Run a tiny HTTP server that returns mock Duffel offers for the session."""
    server = HTTPServer(("localhost", MOCK_PORT), _DuffelMockHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://localhost:{MOCK_PORT}"
    server.shutdown()


@pytest.fixture(scope="session")
def streamlit_url(mock_duffel_server):
    """Start a Streamlit process pointed at the mock Duffel server."""
    env = {
        **os.environ,
        "DUFFEL_API_KEY":   "duffel_test_playwright_fake",
        "DUFFEL_BASE_URL":  mock_duffel_server,
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

    # Wait up to 30 s for the server to respond
    for _ in range(30):
        try:
            urllib.request.urlopen(BASE_URL, timeout=1)
            break
        except Exception:
            time.sleep(1)
    else:
        proc.terminate()
        pytest.fail(f"Streamlit server did not start on {BASE_URL}")

    yield BASE_URL

    proc.terminate()
    proc.wait()


# ---------------------------------------------------------------------------
# Per-test helpers
# ---------------------------------------------------------------------------

def _fill_and_search(page, origin="JFK", destination="LHR"):
    # Wait for Streamlit to render and the server to be ready.
    # The 1 200 ms pause gives the shared server time to close the previous test's
    # WebSocket session before we submit a new search.  800 ms was occasionally
    # insufficient mid-suite when the server is warm from prior tests — bumped to
    # 1 200 ms to absorb that variance without masking real failures.
    page.wait_for_selector('[data-testid="stFormSubmitButton"]', timeout=15_000)
    page.wait_for_timeout(1_200)
    page.get_by_role("textbox", name="From").fill(origin)
    page.get_by_role("textbox", name="To").fill(destination)
    page.locator('[data-testid="stFormSubmitButton"]').click()
    # 45 s gives headroom for city-name resolution (two CSV lookups) on top of
    # the normal Duffel mock round-trip.  Tests later in the suite see a warmer
    # server and occasionally need the extra margin.
    page.wait_for_selector('[data-testid="stDataFrame"]', timeout=45_000)


def _select_row(page, row: int = 0, prev_heading: str = "") -> str:
    """Select a row via the 'Score breakdown for:' selectbox and return the new heading.

    `row` is 0-based.  Option list layout (0-based):
      index 0  →  placeholder "— select a flight —"
      index 1  →  row 0  (#1 …)
      index 2  →  row 1  (#2 …)

    If `prev_heading` is supplied, waits until the heading changes away from that
    value so back-to-back calls don't return stale text.
    """
    sel = page.locator('[data-testid="stSelectbox"]').filter(has_text="Score breakdown for")
    sel.click()   # open the dropdown
    opts = page.locator('[role="option"]')
    opts.nth(row + 1).click()   # +1 to skip the placeholder at index 0

    if prev_heading:
        # Wait until the heading is different (i.e., the rerun has settled with new text)
        page.wait_for_function(
            "h => document.body.innerText.includes('Score breakdown —') && "
            "!document.body.innerText.includes(h)",
            arg=prev_heading,
            timeout=20_000,
        )
    else:
        page.wait_for_selector("text=Score breakdown —", timeout=20_000)

    return page.locator("text=Score breakdown —").first.inner_text()


def _select_first_row(page):
    _select_row(page, row=0)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBrowserInteractions:

    def test_search_produces_results_table(self, page, streamlit_url):
        """Smoke test: a valid search renders the results dataframe."""
        page.goto(streamlit_url)
        _fill_and_search(page)
        assert page.locator('[data-testid="stDataFrame"]').is_visible()

    def test_enter_key_submits_form(self, page, streamlit_url):
        """Pressing Enter in the From field must trigger the search."""
        page.goto(streamlit_url)
        page.wait_for_selector('[data-testid="stFormSubmitButton"]', timeout=15_000)
        page.wait_for_timeout(1_200)  # same settle pause as _fill_and_search
        page.get_by_role("textbox", name="From").fill("JFK")
        page.get_by_role("textbox", name="To").fill("LHR")
        page.get_by_role("textbox", name="From").press("Enter")
        page.wait_for_selector('[data-testid="stDataFrame"]', timeout=30_000)
        assert page.locator('[data-testid="stDataFrame"]').is_visible()

    def test_row_select_keeps_results_table(self, page, streamlit_url):
        """Results table must still be visible after a row is selected.

        Regression: before the session-state fix, any rerun wiped the results
        block because results were only rendered inside `if search_clicked:`.
        """
        page.goto(streamlit_url)
        _fill_and_search(page)

        _select_first_row(page)

        assert page.locator('[data-testid="stDataFrame"]').is_visible()

    def test_row_select_shows_breakdown(self, page, streamlit_url):
        """Selecting a row in the dropdown must render the per-factor breakdown."""
        page.goto(streamlit_url)
        _fill_and_search(page)

        _select_first_row(page)

        assert page.locator("text=Score breakdown —").is_visible()

    # -----------------------------------------------------------------------
    # New tests
    # -----------------------------------------------------------------------

    def test_empty_form_shows_warning(self, page, streamlit_url):
        """Clicking Search with empty fields must show a warning in the browser."""
        page.goto(streamlit_url)
        page.locator('[data-testid="stFormSubmitButton"]').click()
        page.wait_for_selector('[data-testid="stAlert"]', timeout=5_000)
        warning_text = page.locator('[data-testid="stAlert"]').first.inner_text()
        assert "origin" in warning_text.lower() or "destination" in warning_text.lower()

    def test_city_name_search_resolves_and_returns_results(self, page, streamlit_url):
        """Typing city names instead of IATA codes must still produce results.

        End-to-end test of the full _resolve_iata pipeline: city name →
        metro/airport code → Duffel request → scored results table.
        Would have caught the missing airports.csv bug before it reached the browser.
        """
        page.goto(streamlit_url)
        _fill_and_search(page, origin="New York", destination="London")
        assert page.locator('[data-testid="stDataFrame"]').is_visible()

    def test_selecting_different_rows_updates_breakdown(self, page, streamlit_url):
        """Switching the selectbox from row 1 to row 2 must update the breakdown.

        Confirms that selecting a different option changes the displayed breakdown,
        not just shows a stale one from the first selection.
        """
        page.goto(streamlit_url)
        _fill_and_search(page)

        # Select row 0, capture heading, then switch to row 1 and confirm it changed.
        heading_row0 = _select_row(page, row=0)
        heading_row1 = _select_row(page, row=1, prev_heading=heading_row0)

        assert heading_row0 != heading_row1, (
            f"Breakdown heading did not change after selecting row 1: '{heading_row1}'"
        )

    def test_checkbox_click_shows_breakdown(self, page, streamlit_url):
        """Clicking a row checkbox must show the per-factor score breakdown.

        This is the end-to-end regression test for the checkbox interaction path.
        It verifies the full chain: checkbox click → on_select rerun → breakdown
        session state updated → breakdown charts rendered.

        Prior regressions caught by this test:
          - on_select removed → checkbox column disappears entirely
          - on_select present but not wired to breakdown → canvas repaints
            (row highlights) but breakdown never appears
        """
        page.goto(streamlit_url)
        _fill_and_search(page)

        df = page.locator('[data-testid="stDataFrame"]').first
        bbox = df.bounding_box()

        # Click the row-selector checkbox column (~20 px from the left edge)
        page.mouse.click(bbox["x"] + 20, bbox["y"] + 58)

        # The breakdown must appear — a canvas repaint alone is not sufficient
        page.wait_for_selector("text=Score breakdown —", timeout=20_000)
        assert page.locator("text=Score breakdown —").is_visible()
