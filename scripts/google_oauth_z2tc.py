#!/usr/bin/env python3
"""One-time OAuth for z2tc Google APIs (Forms + Sheets + Drive read).

Writes ``auth/z2tc_google_token.json`` (gitignored). Use this token for
``scripts/update_marathon_intake_form.py``::

    export Z2TC_GOOGLE_TOKEN=$PWD/auth/z2tc_google_token.json

Prerequisites on Google Cloud (project that owns ``client_secret_*.json``):

- Enable **Google Forms API** and **Google Sheets API** (and Drive if needed).
- OAuth consent screen in **Testing** with your Google account as a test user, or
  publish the app for broader access.

"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

ROOT = Path(__file__).resolve().parents[1]
AUTH_DIR = ROOT / "auth"
SCOPES = [
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]


def _find_client_secret() -> Path:
    env = os.environ.get("Z2TC_GOOGLE_CLIENT_SECRET")
    if env:
        return Path(env)
    matches = sorted(ROOT.glob("client_secret_*.json"))
    if not matches:
        raise FileNotFoundError(
            "No client_secret_*.json in repo root. Add the OAuth client JSON or set "
            "Z2TC_GOOGLE_CLIENT_SECRET."
        )
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--console",
        action="store_true",
        help="Print an auth URL and read the code from stdin (use in SSH / headless).",
    )
    args = parser.parse_args()

    AUTH_DIR.mkdir(parents=True, exist_ok=True)
    out = Path(os.environ.get("Z2TC_GOOGLE_TOKEN", AUTH_DIR / "z2tc_google_token.json"))
    client = _find_client_secret()

    flow = InstalledAppFlow.from_client_secrets_file(str(client), SCOPES)
    if args.console:
        creds: Credentials = flow.run_console()
    else:
        creds = flow.run_local_server(port=0, open_browser=True)
    out.write_text(creds.to_json())
    print(f"Wrote token to {out}")
    print("Export for other scripts:")
    print(f"  export Z2TC_GOOGLE_TOKEN={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
