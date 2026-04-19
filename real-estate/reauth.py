#!/usr/bin/env python3
from google_auth_oauthlib.flow import InstalledAppFlow
from pathlib import Path

flow = InstalledAppFlow.from_client_secrets_file(
    'credentials.json',
    ['https://www.googleapis.com/auth/gmail.readonly',
     'https://www.googleapis.com/auth/gmail.send']
)
creds = flow.run_local_server(port=0)
Path('token.json').write_text(creds.to_json())
print("Auth successful — token.json updated.")
