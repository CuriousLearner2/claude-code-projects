#!/usr/bin/env python3
"""Create a Google Doc with this week's calendar events."""

import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/documents"]
TOKEN_FILE = os.path.join(os.path.dirname(__file__), "token_docs.json")
CREDS_FILE = os.path.join(os.path.dirname(__file__), "credentials.json")

EVENTS = [
    # Multi-day
    {"day": "All Week", "time": "", "title": "Ann & Mira | Care for Billy (3/31 after 11am)"},
    {"day": "All Week", "time": "", "title": "Mira | Mosaic Project Outdoor School (Spring 2026)"},
    # Monday Apr 6
    {"day": "Monday, April 6", "time": "7:00 AM",  "title": "Mira's meds"},
    {"day": "Monday, April 6", "time": "8:30 AM",  "title": "Meds"},
    {"day": "Monday, April 6", "time": "1:00 PM",  "title": "Ann-Gautam M consult"},
    {"day": "Monday, April 6", "time": "1:00 PM",  "title": "Virtual Medicare counseling"},
    {"day": "Monday, April 6", "time": "2:00 PM",  "title": "Stanford Volunteering"},
    {"day": "Monday, April 6", "time": "9:00 PM",  "title": "Evening Meds"},
    # Tuesday Apr 7
    {"day": "Tuesday, April 7", "time": "7:00 AM",  "title": "Mira's meds"},
    {"day": "Tuesday, April 7", "time": "8:00 AM",  "title": "Equip | Emotional and Practical Tools for Caregivers: Education and Skills"},
    {"day": "Tuesday, April 7", "time": "8:30 AM",  "title": "Meds"},
    {"day": "Tuesday, April 7", "time": "2:00 PM",  "title": "Equip | Caregivers of College-Age Patients (ages 18–24): Support and Skills"},
    {"day": "Tuesday, April 7", "time": "3:30 PM",  "title": "Review CT with Samantha Smrcka Callan, PA - Must be at home"},
    {"day": "Tuesday, April 7", "time": "3:45 PM",  "title": "BSS KK"},
    {"day": "Tuesday, April 7", "time": "9:00 PM",  "title": "Evening Meds"},
    # Wednesday Apr 8
    {"day": "Wednesday, April 8", "time": "7:00 AM",  "title": "Mira's meds"},
    {"day": "Wednesday, April 8", "time": "8:30 AM",  "title": "Meds"},
    {"day": "Wednesday, April 8", "time": "9:30 AM",  "title": "School Dropoff"},
    {"day": "Wednesday, April 8", "time": "9:00 PM",  "title": "Evening Meds"},
    # Thursday Apr 9
    {"day": "Thursday, April 9", "time": "7:00 AM",  "title": "Mira's meds"},
    {"day": "Thursday, April 9", "time": "8:30 AM",  "title": "Stanford Dermatology | Moh's Surgery (4-8 hrs)"},
    {"day": "Thursday, April 9", "time": "8:30 AM",  "title": "Meds"},
    {"day": "Thursday, April 9", "time": "1:30 PM",  "title": "Equip | Caregivers of Young Adults (ages 18+): Support and Skills (JD Ouelette)"},
    {"day": "Thursday, April 9", "time": "5:45 PM",  "title": "BSS Shift Sunnyvale"},
    {"day": "Thursday, April 9", "time": "9:00 PM",  "title": "Evening Meds"},
    # Friday Apr 10
    {"day": "Friday, April 10", "time": "7:00 AM",  "title": "Mira's meds"},
    {"day": "Friday, April 10", "time": "7:30 AM",  "title": "D"},
    {"day": "Friday, April 10", "time": "8:30 AM",  "title": "Meds"},
    {"day": "Friday, April 10", "time": "4:00 PM",  "title": "P/u Mira from Mosaic - 5pm"},
    {"day": "Friday, April 10", "time": "9:00 PM",  "title": "Evening Meds"},
    # Saturday Apr 11
    {"day": "Saturday, April 11", "time": "7:00 AM",  "title": "Mira's meds"},
    {"day": "Saturday, April 11", "time": "8:30 AM",  "title": "Meds"},
    {"day": "Saturday, April 11", "time": "8:30 AM",  "title": "Destination USF | For Admitted Students & Parents"},
    {"day": "Saturday, April 11", "time": "8:45 AM",  "title": "BSS Sunnyvale"},
    {"day": "Saturday, April 11", "time": "8:45 AM",  "title": "Shift @ British SS"},
    {"day": "Saturday, April 11", "time": "9:00 PM",  "title": "Evening Meds"},
    # Sunday Apr 12
    {"day": "Sunday, April 12", "time": "7:00 AM",  "title": "Mira's meds"},
    {"day": "Sunday, April 12", "time": "8:30 AM",  "title": "Meds"},
    {"day": "Sunday, April 12", "time": "5:00 PM",  "title": "Take Mira to Mosaic"},
    {"day": "Sunday, April 12", "time": "7:00 PM",  "title": "Family meeting"},
    {"day": "Sunday, April 12", "time": "9:00 PM",  "title": "Evening Meds"},
]


def get_credentials():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return creds


def build_requests():
    """Build the Google Docs API batchUpdate requests to populate the document."""
    requests = []
    cursor = 1  # tracks insertion index (doc starts at index 1)

    def insert_text(text, idx):
        return {"insertText": {"location": {"index": idx}, "text": text}}

    def style_range(start, end, bold=False, font_size=None, foreground_color=None):
        fields = []
        fmt = {}
        if bold:
            fmt["bold"] = True
            fields.append("bold")
        if font_size:
            fmt["fontSize"] = {"magnitude": font_size, "unit": "PT"}
            fields.append("fontSize")
        if foreground_color:
            fmt["foregroundColor"] = {"color": {"rgbColor": foreground_color}}
            fields.append("foregroundColor")
        return {
            "updateTextStyle": {
                "range": {"startIndex": start, "endIndex": end},
                "textStyle": fmt,
                "fields": ",".join(fields),
            }
        }

    def style_paragraph(start, end, named_style):
        return {
            "updateParagraphStyle": {
                "range": {"startIndex": start, "endIndex": end},
                "paragraphStyle": {"namedStyleType": named_style},
                "fields": "namedStyleType",
            }
        }

    # Title
    title = "Week of April 6–12, 2026\n"
    requests.append(insert_text(title, cursor))
    requests.append(style_paragraph(cursor, cursor + len(title), "TITLE"))
    cursor += len(title)

    # Group events by day
    days = {}
    for e in EVENTS:
        days.setdefault(e["day"], []).append(e)

    for day, events in days.items():
        # Day heading
        heading = f"{day}\n"
        requests.append(insert_text(heading, cursor))
        requests.append(style_paragraph(cursor, cursor + len(heading), "HEADING_2"))
        cursor += len(heading)

        for e in events:
            if e["time"]:
                line = f"{e['time']}  {e['title']}\n"
                requests.append(insert_text(line, cursor))
                # Bold the time portion
                requests.append(style_range(cursor, cursor + len(e["time"]), bold=True))
                cursor += len(line)
            else:
                line = f"{e['title']}\n"
                requests.append(insert_text(line, cursor))
                cursor += len(line)

    return requests


def main():
    creds = get_credentials()
    service = build("docs", "v1", credentials=creds)

    # Create blank doc
    doc = service.documents().create(body={"title": "Week of April 6–12, 2026"}).execute()
    doc_id = doc["documentId"]
    print(f"Created doc: https://docs.google.com/document/d/{doc_id}/edit")

    # Populate with events
    reqs = build_requests()
    service.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": reqs}
    ).execute()

    print("Done! Doc is ready.")
    return f"https://docs.google.com/document/d/{doc_id}/edit"


if __name__ == "__main__":
    main()
