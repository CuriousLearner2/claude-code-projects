#!/usr/bin/env python3
"""
Gmail Search — search your Gmail using natural language.

Setup (one-time):
  1. Go to https://console.cloud.google.com/
  2. Create a project → Enable the Gmail API
  3. Create OAuth 2.0 credentials (Desktop app) → download as credentials.json
  4. Place credentials.json in the same directory as this script
  5. Set your Anthropic API key: export ANTHROPIC_API_KEY=sk-...
  6. pip3 install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client anthropic

Usage:
  python3 gmail_search.py "emails from my boss last week"
  python3 gmail_search.py "unread invoices with attachments" --max 20
  python3 gmail_search.py "newsletters I haven't read"
  python3 gmail_search.py --raw "from:boss@example.com"   # skip AI, use Gmail syntax directly
"""

import argparse
import base64
import os
import sys
from datetime import datetime

import anthropic
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
TOKEN_FILE = os.path.join(os.path.dirname(__file__), "token.json")
CREDS_FILE = os.path.join(os.path.dirname(__file__), "credentials.json")

SYSTEM_PROMPT = """You are a Gmail search query translator. Convert natural language into valid Gmail search syntax.

Gmail search operators:
- from:email      — sender
- to:email        — recipient
- subject:text    — subject line
- label:name      — label/folder
- is:unread       — unread messages
- is:read         — read messages
- is:starred      — starred messages
- has:attachment  — has attachments
- filename:ext    — attachment type (e.g. filename:pdf)
- after:YYYY/M/D  — received after date
- before:YYYY/M/D — received before date
- newer_than:Nd   — last N days (e.g. newer_than:7d)
- older_than:Nd   — older than N days
- in:inbox        — in inbox
- in:spam         — in spam
- in:trash        — in trash
- "exact phrase"  — exact phrase match
- OR              — either term
- -term           — exclude term

Respond with ONLY the Gmail search query string — no explanation, no quotes around it, no markdown.
If the request is ambiguous, make a reasonable best-guess query.

Examples:
  "emails from my boss about the project" → from:boss subject:project
  "unread emails with PDF attachments" → is:unread has:attachment filename:pdf
  "newsletters from last week" → subject:newsletter newer_than:7d
  "emails about invoices I haven't replied to" → subject:invoice is:unread
  "messages from amazon in the last month" → from:amazon newer_than:30d"""


def natural_language_to_query(user_input: str) -> str:
    """Use Claude to translate natural language into a Gmail search query."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("WARNING: ANTHROPIC_API_KEY not set — using your input as a raw Gmail query.")
        return user_input

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_input}],
    )
    return response.content[0].text.strip()


def authenticate():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDS_FILE):
                print("ERROR: credentials.json not found.")
                print("See the setup instructions at the top of this script.")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def get_header(headers, name):
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return "(none)"


def get_snippet(service, msg_id):
    msg = service.users().messages().get(
        userId="me", id=msg_id, format="metadata",
        metadataHeaders=["Subject", "From", "Date"]
    ).execute()
    headers = msg["payload"]["headers"]
    return {
        "id": msg_id,
        "subject": get_header(headers, "Subject"),
        "from": get_header(headers, "From"),
        "date": get_header(headers, "Date"),
        "snippet": msg.get("snippet", ""),
    }


def get_body(service, msg_id):
    msg = service.users().messages().get(
        userId="me", id=msg_id, format="full"
    ).execute()

    headers = msg["payload"]["headers"]
    result = {
        "subject": get_header(headers, "Subject"),
        "from": get_header(headers, "From"),
        "to": get_header(headers, "To"),
        "date": get_header(headers, "Date"),
        "body": "",
    }

    def extract_text(parts):
        text = ""
        for part in parts:
            mime = part.get("mimeType", "")
            if mime == "text/plain" and "data" in part.get("body", {}):
                data = part["body"]["data"]
                text += base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
            elif "parts" in part:
                text += extract_text(part["parts"])
        return text

    payload = msg["payload"]
    if "parts" in payload:
        result["body"] = extract_text(payload["parts"])
    elif payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            result["body"] = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    else:
        result["body"] = "(No plain-text body found — may be HTML-only)"

    return result


def search(service, query, max_results):
    print(f'\nSearching for: "{query}" (max {max_results})\n')
    response = service.users().messages().list(
        userId="me", q=query, maxResults=max_results
    ).execute()

    messages = response.get("messages", [])
    if not messages:
        print("No messages found.")
        return []

    print(f"Found {len(messages)} result(s):\n")
    results = []
    for i, msg in enumerate(messages, 1):
        info = get_snippet(service, msg["id"])
        results.append(info)
        print(f"[{i}] {info['subject']}")
        print(f"    From:    {info['from']}")
        print(f"    Date:    {info['date']}")
        print(f"    Preview: {info['snippet'][:120]}")
        print()

    return results


def interactive_open(service, results):
    while True:
        choice = input("Enter a number to read the full email (or q to quit): ").strip()
        if choice.lower() == "q":
            break
        if not choice.isdigit() or not (1 <= int(choice) <= len(results)):
            print(f"Please enter a number between 1 and {len(results)}.")
            continue

        idx = int(choice) - 1
        email = get_body(service, results[idx]["id"])
        print("\n" + "=" * 60)
        print(f"Subject : {email['subject']}")
        print(f"From    : {email['from']}")
        print(f"To      : {email['to']}")
        print(f"Date    : {email['date']}")
        print("=" * 60)
        print(email["body"][:3000])
        if len(email["body"]) > 3000:
            print("\n... (truncated — email is longer) ...")
        print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Search your Gmail using natural language.")
    parser.add_argument("query", nargs="?", help="Natural language search (e.g. 'emails from my boss last week')")
    parser.add_argument("--max", type=int, default=10, help="Max results to return (default: 10)")
    parser.add_argument("--raw", action="store_true", help="Treat query as raw Gmail syntax, skip AI translation")
    args = parser.parse_args()

    if not args.query:
        args.query = input("What emails are you looking for? ").strip()
        if not args.query:
            print("No query provided.")
            sys.exit(1)

    if args.raw:
        gmail_query = args.query
    else:
        print(f'\nTranslating: "{args.query}"')
        gmail_query = natural_language_to_query(args.query)
        print(f'Gmail query: {gmail_query}')

    service = authenticate()
    results = search(service, gmail_query, args.max)

    if results:
        interactive_open(service, results)


if __name__ == "__main__":
    main()
