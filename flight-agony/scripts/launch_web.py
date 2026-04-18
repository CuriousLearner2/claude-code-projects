#!/usr/bin/env python3
"""
Launch the Flight Agony web UI.

Usage:
    python scripts/launch_web.py

Requires streamlit: pip install streamlit plotly
"""

import subprocess
import sys
from pathlib import Path

APP = Path(__file__).parent.parent / "web" / "app.py"

# Suppress Streamlit's first-run email prompt by ensuring credentials exist.
_CREDS = Path.home() / ".streamlit" / "credentials.toml"


def _ensure_credentials() -> None:
    if not _CREDS.exists():
        _CREDS.parent.mkdir(parents=True, exist_ok=True)
        _CREDS.write_text('[general]\nemail = ""\n')


def main() -> None:
    _ensure_credentials()
    subprocess.run(
        [
            sys.executable, "-m", "streamlit", "run", str(APP),
            "--browser.gatherUsageStats", "false",
        ],
        check=True,
    )


if __name__ == "__main__":
    main()
