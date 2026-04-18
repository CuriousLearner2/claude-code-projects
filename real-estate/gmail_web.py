#!/usr/bin/env python3
"""
Gmail Search — web UI
Run: python3 gmail_web.py
Then open http://localhost:5000 in your browser.

Requires ANTHROPIC_API_KEY environment variable.
Requires credentials.json from Google Cloud Console (same as gmail_search.py).
"""

import base64
import os
import sys

import anthropic
from flask import Flask, jsonify, render_template_string, request
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

Respond with ONLY the Gmail search query string — no explanation, no quotes around it, no markdown."""

app = Flask(__name__)
_gmail_service = None


def get_gmail_service():
    global _gmail_service
    if _gmail_service:
        return _gmail_service

    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDS_FILE):
                raise FileNotFoundError("credentials.json not found. See setup instructions.")
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    _gmail_service = build("gmail", "v1", credentials=creds)
    return _gmail_service


def translate_query(natural_language: str) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return natural_language
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=256,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": natural_language}],
    )
    return response.content[0].text.strip()


def get_header(headers, name):
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


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


HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Gmail Search</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #f6f8fa;
      color: #24292f;
      min-height: 100vh;
    }

    header {
      background: #fff;
      border-bottom: 1px solid #d0d7de;
      padding: 1rem 2rem;
      display: flex;
      align-items: center;
      gap: 1rem;
    }

    header h1 {
      font-size: 1.2rem;
      font-weight: 600;
      color: #24292f;
    }

    .search-bar {
      background: #fff;
      border-bottom: 1px solid #d0d7de;
      padding: 1.25rem 2rem;
    }

    .search-row {
      display: flex;
      gap: 0.75rem;
      max-width: 800px;
    }

    #query {
      flex: 1;
      padding: 0.6rem 1rem;
      font-size: 1rem;
      border: 1px solid #d0d7de;
      border-radius: 6px;
      outline: none;
      transition: border-color 0.15s, box-shadow 0.15s;
    }

    #query:focus {
      border-color: #0969da;
      box-shadow: 0 0 0 3px rgba(9,105,218,0.15);
    }

    #search-btn {
      padding: 0.6rem 1.25rem;
      background: #0969da;
      color: #fff;
      border: none;
      border-radius: 6px;
      font-size: 1rem;
      cursor: pointer;
      font-weight: 500;
      transition: background 0.15s;
      white-space: nowrap;
    }

    #search-btn:hover { background: #0860ca; }
    #search-btn:disabled { background: #6e7781; cursor: not-allowed; }

    .translated-query {
      margin-top: 0.6rem;
      font-size: 0.82rem;
      color: #57606a;
    }

    .translated-query code {
      background: #eaeef2;
      padding: 0.1rem 0.35rem;
      border-radius: 4px;
      font-family: monospace;
    }

    .layout {
      display: flex;
      height: calc(100vh - 120px);
    }

    .results-pane {
      width: 380px;
      min-width: 280px;
      border-right: 1px solid #d0d7de;
      background: #fff;
      overflow-y: auto;
    }

    .results-pane .empty {
      padding: 2rem;
      color: #57606a;
      text-align: center;
      margin-top: 3rem;
    }

    .result-item {
      padding: 1rem 1.25rem;
      border-bottom: 1px solid #f0f0f0;
      cursor: pointer;
      transition: background 0.1s;
    }

    .result-item:hover { background: #f6f8fa; }
    .result-item.active { background: #ddf4ff; border-left: 3px solid #0969da; }

    .result-item .subject {
      font-weight: 600;
      font-size: 0.9rem;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .result-item .from {
      font-size: 0.8rem;
      color: #57606a;
      margin-top: 0.2rem;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .result-item .date {
      font-size: 0.75rem;
      color: #8c959f;
      margin-top: 0.15rem;
    }

    .result-item .preview {
      font-size: 0.8rem;
      color: #57606a;
      margin-top: 0.35rem;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }

    .email-pane {
      flex: 1;
      overflow-y: auto;
      padding: 2rem;
      background: #fff;
    }

    .email-pane .placeholder {
      color: #8c959f;
      text-align: center;
      margin-top: 5rem;
      font-size: 1rem;
    }

    .email-header {
      border-bottom: 1px solid #d0d7de;
      padding-bottom: 1.25rem;
      margin-bottom: 1.5rem;
    }

    .email-header h2 {
      font-size: 1.25rem;
      font-weight: 600;
      margin-bottom: 0.75rem;
    }

    .meta-row {
      display: flex;
      gap: 0.4rem;
      font-size: 0.85rem;
      margin-top: 0.3rem;
      color: #57606a;
    }

    .meta-row strong { color: #24292f; }

    .email-body {
      font-size: 0.9rem;
      line-height: 1.7;
      white-space: pre-wrap;
      word-break: break-word;
      color: #24292f;
    }

    .spinner {
      display: inline-block;
      width: 16px; height: 16px;
      border: 2px solid #d0d7de;
      border-top-color: #0969da;
      border-radius: 50%;
      animation: spin 0.7s linear infinite;
      vertical-align: middle;
      margin-right: 6px;
    }

    @keyframes spin { to { transform: rotate(360deg); } }

    .error-msg {
      color: #cf222e;
      font-size: 0.85rem;
      margin-top: 0.5rem;
    }
  </style>
</head>
<body>

<header>
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#0969da" stroke-width="2">
    <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
  </svg>
  <h1>Gmail Search</h1>
</header>

<div class="search-bar">
  <div class="search-row">
    <input id="query" type="text" placeholder='Try "unread emails from my boss last week" or "invoices with attachments"' autofocus>
    <button id="search-btn" onclick="doSearch()">Search</button>
  </div>
  <div id="translated" class="translated-query"></div>
  <div id="error" class="error-msg"></div>
</div>

<div class="layout">
  <div class="results-pane" id="results-pane">
    <div class="empty">Search your Gmail using plain English</div>
  </div>
  <div class="email-pane" id="email-pane">
    <div class="placeholder">Select an email to read it</div>
  </div>
</div>

<script>
  document.getElementById('query').addEventListener('keydown', e => {
    if (e.key === 'Enter') doSearch();
  });

  async function doSearch() {
    const query = document.getElementById('query').value.trim();
    if (!query) return;

    const btn = document.getElementById('search-btn');
    const translatedEl = document.getElementById('translated');
    const errorEl = document.getElementById('error');
    const resultsPane = document.getElementById('results-pane');
    const emailPane = document.getElementById('email-pane');

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span>Searching…';
    translatedEl.textContent = '';
    errorEl.textContent = '';
    resultsPane.innerHTML = '<div class="empty"><span class="spinner"></span> Searching…</div>';
    emailPane.innerHTML = '<div class="placeholder">Select an email to read it</div>';

    try {
      const res = await fetch('/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query })
      });
      const data = await res.json();

      if (data.error) {
        errorEl.textContent = 'Error: ' + data.error;
        resultsPane.innerHTML = '<div class="empty">Something went wrong.</div>';
        return;
      }

      translatedEl.innerHTML = `Gmail query: <code>${escHtml(data.gmail_query)}</code>`;

      if (!data.results || data.results.length === 0) {
        resultsPane.innerHTML = '<div class="empty">No emails found.</div>';
        return;
      }

      resultsPane.innerHTML = data.results.map((r, i) => `
        <div class="result-item" id="item-${i}" onclick="loadEmail('${r.id}', ${i})">
          <div class="subject">${escHtml(r.subject || '(no subject)')}</div>
          <div class="from">${escHtml(r.from)}</div>
          <div class="date">${escHtml(r.date)}</div>
          <div class="preview">${escHtml(r.snippet)}</div>
        </div>
      `).join('');

    } catch (err) {
      errorEl.textContent = 'Network error: ' + err.message;
    } finally {
      btn.disabled = false;
      btn.textContent = 'Search';
    }
  }

  async function loadEmail(id, idx) {
    document.querySelectorAll('.result-item').forEach(el => el.classList.remove('active'));
    const item = document.getElementById('item-' + idx);
    if (item) item.classList.add('active');

    const emailPane = document.getElementById('email-pane');
    emailPane.innerHTML = '<div class="placeholder"><span class="spinner"></span> Loading…</div>';

    try {
      const res = await fetch('/email/' + id);
      const data = await res.json();

      if (data.error) {
        emailPane.innerHTML = `<div class="placeholder" style="color:#cf222e">Error: ${escHtml(data.error)}</div>`;
        return;
      }

      emailPane.innerHTML = `
        <div class="email-header">
          <h2>${escHtml(data.subject || '(no subject)')}</h2>
          <div class="meta-row"><strong>From:</strong> ${escHtml(data.from)}</div>
          <div class="meta-row"><strong>To:</strong> ${escHtml(data.to)}</div>
          <div class="meta-row"><strong>Date:</strong> ${escHtml(data.date)}</div>
        </div>
        <div class="email-body">${escHtml(data.body || '(no plain-text body)')}</div>
      `;
    } catch (err) {
      emailPane.innerHTML = `<div class="placeholder" style="color:#cf222e">Network error: ${escHtml(err.message)}</div>`;
    }
  }

  function escHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
</script>
</body>
</html>"""


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/search", methods=["POST"])
def search():
    data = request.get_json()
    natural_query = data.get("query", "").strip()
    if not natural_query:
        return jsonify({"error": "Empty query"}), 400

    try:
        gmail_query = translate_query(natural_query)
        service = get_gmail_service()
        response = service.users().messages().list(
            userId="me", q=gmail_query, maxResults=25
        ).execute()

        messages = response.get("messages", [])
        results = []
        for msg in messages:
            msg_data = service.users().messages().get(
                userId="me", id=msg["id"], format="metadata",
                metadataHeaders=["Subject", "From", "Date"]
            ).execute()
            headers = msg_data["payload"]["headers"]
            results.append({
                "id": msg["id"],
                "subject": get_header(headers, "Subject"),
                "from": get_header(headers, "From"),
                "date": get_header(headers, "Date"),
                "snippet": msg_data.get("snippet", ""),
            })

        return jsonify({"gmail_query": gmail_query, "results": results})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/email/<msg_id>")
def get_email(msg_id):
    try:
        service = get_gmail_service()
        msg = service.users().messages().get(
            userId="me", id=msg_id, format="full"
        ).execute()

        headers = msg["payload"]["headers"]
        payload = msg["payload"]

        if "parts" in payload:
            body = extract_text(payload["parts"])
        elif payload.get("mimeType") == "text/plain":
            raw = payload.get("body", {}).get("data", "")
            body = base64.urlsafe_b64decode(raw).decode("utf-8", errors="replace") if raw else ""
        else:
            body = "(No plain-text body — may be HTML-only)"

        return jsonify({
            "subject": get_header(headers, "Subject"),
            "from": get_header(headers, "From"),
            "to": get_header(headers, "To"),
            "date": get_header(headers, "Date"),
            "body": body,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    if not os.path.exists(CREDS_FILE):
        print("ERROR: credentials.json not found.")
        print("See the setup instructions at the top of this file.")
        sys.exit(1)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("WARNING: ANTHROPIC_API_KEY not set — queries won't be translated by AI.")

    print("Starting Gmail Search at http://localhost:5000")
    app.run(debug=False, port=5000)
