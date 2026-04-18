"""
tests/conftest.py

Session-wide pytest setup for the flight-agony test suite.

Adds the scripts/ directory to sys.path so that `search_flights` is importable
by both the backend scoring tests and the UI tests that patch it.
"""

import sys
from pathlib import Path

# Ensure search_flights is importable before any test (or autouse fixture) runs.
# AppTest re-executes the app script on each run(), which does the same sys.path
# insert internally — this just guarantees it's available from the start so that
# patch("search_flights.search_flights", ...) can locate the module to patch.
SCRIPTS_DIR = str(Path(__file__).parent.parent / "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)
