#!/usr/bin/env python3
"""Probe Streamlit selectbox DOM structure to find the right Playwright selectors."""
import json, os, subprocess, sys, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

APP_PATH  = str(Path(__file__).parent.parent / "web" / "app.py")
APP_PORT  = 8505
MOCK_PORT = 9879
BASE_URL  = f"http://localhost:{APP_PORT}"

def _seg(dep, arr, orig, dest, carrier):
    return {"departing_at": dep, "arriving_at": arr,
            "origin": {"iata_code": orig}, "destination": {"iata_code": dest},
            "operating_carrier": {"iata_code": carrier}}

MOCK_BODY = json.dumps({"data": {"offers": [
    {"slices": [
        {"segments": [_seg("2026-06-15T09:00:00","2026-06-15T17:00:00","JFK","LHR","BA")],"duration":"PT8H00M"},
        {"segments": [_seg("2026-06-22T10:00:00","2026-06-22T18:00:00","LHR","JFK","BA")],"duration":"PT8H00M"},
    ], "total_amount":"450.00","total_currency":"USD"},
    {"slices": [
        {"segments": [_seg("2026-06-15T07:00:00","2026-06-15T17:00:00","JFK","LHR","AA")],"duration":"PT10H00M"},
        {"segments": [_seg("2026-06-22T08:00:00","2026-06-22T18:00:00","LHR","JFK","AA")],"duration":"PT10H00M"},
    ], "total_amount":"310.00","total_currency":"USD"},
]}}).encode()

class _H(BaseHTTPRequestHandler):
    def do_POST(self):
        self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers()
        self.wfile.write(MOCK_BODY)
    def log_message(self,*_): pass

def start():
    s = HTTPServer(("localhost",MOCK_PORT),_H)
    threading.Thread(target=s.serve_forever,daemon=True).start()
    env = {**os.environ,"DUFFEL_API_KEY":"fake","DUFFEL_BASE_URL":f"http://localhost:{MOCK_PORT}"}
    p = subprocess.Popen([sys.executable,"-m","streamlit","run",APP_PATH,
        "--server.port",str(APP_PORT),"--server.headless","true","--browser.gatherUsageStats","false"],
        env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    for _ in range(30):
        try: urllib.request.urlopen(BASE_URL,timeout=1); break
        except: time.sleep(1)
    return s, p

from playwright.sync_api import sync_playwright

mock, proc = start()
try:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width":1400,"height":900})
        page.goto(BASE_URL)
        page.wait_for_selector('[data-testid="stFormSubmitButton"]', timeout=15_000)
        page.get_by_role("textbox", name="From").fill("JFK")
        page.get_by_role("textbox", name="To").fill("LHR")
        page.locator('[data-testid="stFormSubmitButton"]').click()
        page.wait_for_selector('[data-testid="stDataFrame"]', timeout=20_000)

        # Probe selectbox structure
        sb = page.locator('[data-testid="stSelectbox"]').filter(has_text="Score breakdown for")
        print("Selectbox count:", sb.count())
        print("Selectbox outer HTML (first 800 chars):")
        print(sb.first.inner_html()[:800])
        print()

        # Try clicking it
        sb.first.click()
        time.sleep(0.5)
        page.screenshot(path="/tmp/probe_after_click.png")
        print("Screenshot after click: /tmp/probe_after_click.png")

        # Look for open dropdown
        print("Listbox count:", page.locator('[role="listbox"]').count())
        print("Option count:", page.locator('[role="option"]').count())

        # Try getting all visible text after click
        options = page.locator('[role="option"]').all()
        print(f"Options found: {len(options)}")
        for i, opt in enumerate(options):
            print(f"  [{i}] text={opt.inner_text()!r}")

        browser.close()
finally:
    proc.terminate(); proc.wait(); mock.shutdown()
