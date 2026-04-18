#!/usr/bin/env python3
"""Send a failure alert email via Gmail. Called by wrapper scripts on error."""
import base64
import sys
from datetime import datetime
from email.mime.text import MIMEText
from pathlib import Path

RECIPIENT = "gautambiswas2004@gmail.com"


def _get_gmail_service():
    sys.path.insert(0, str(Path(__file__).parent / "real-estate"))
    from listings.utils import get_gmail_service
    return get_gmail_service()


def send_alert(job: str, reason: str, log_path: str) -> None:
    try:
        log_tail = ""
        try:
            lines = Path(log_path).read_text().splitlines()
            log_tail = "\n".join(lines[-40:])
        except Exception:
            log_tail = "(log not readable)"

        body = (
            f"Job:    {job}\n"
            f"Time:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Reason: {reason}\n\n"
            f"--- Last 40 lines of {log_path} ---\n"
            f"{log_tail}\n"
        )
        msg = MIMEText(body, "plain")
        msg["To"] = RECIPIENT
        msg["From"] = RECIPIENT
        msg["Subject"] = f"[ALERT] {job} failed — {reason}"
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service = _get_gmail_service()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        print(f"Alert email sent to {RECIPIENT}")
    except Exception as e:
        print(f"WARNING: Could not send alert email: {e}", file=sys.stderr)


if __name__ == "__main__":
    # Usage: send_alert.py <job> <reason> <log_path>
    if len(sys.argv) != 4:
        print("Usage: send_alert.py <job> <reason> <log_path>", file=sys.stderr)
        sys.exit(1)
    send_alert(sys.argv[1], sys.argv[2], sys.argv[3])
