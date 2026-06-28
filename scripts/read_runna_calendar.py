#!/usr/bin/env python3
"""Read workout names from a Google Calendar (e.g. the Runna training calendar).

Used to harvest real-world workout naming for the z2tc workout catalog. Read-only.

Prereq — authorize once with the calendar scope (see ``scripts/google_oauth_z2tc.py``)::

    export Z2TC_GOOGLE_CLIENT_SECRET=$PWD/client_secret_<...>.json
    python scripts/google_oauth_z2tc.py            # opens a browser for consent
    export Z2TC_GOOGLE_TOKEN=$PWD/auth/z2tc_google_token.json

Then::

    python scripts/read_runna_calendar.py                 # list calendars, dump Runna
    python scripts/read_runna_calendar.py --calendar Runna --days-back 30 --days-ahead 90
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

ROOT = Path(__file__).resolve().parents[1]


def _load_creds() -> Credentials:
    token = Path(os.environ.get("Z2TC_GOOGLE_TOKEN", ROOT / "auth" / "z2tc_google_token.json"))
    if not token.exists():
        sys.exit(
            f"No token at {token}. Run scripts/google_oauth_z2tc.py first (it now requests "
            "the calendar.readonly scope), then export Z2TC_GOOGLE_TOKEN to its path."
        )
    creds = Credentials.from_authorized_user_file(str(token))
    scopes = set(creds.scopes or [])
    if "https://www.googleapis.com/auth/calendar.readonly" not in scopes:
        sys.exit(
            "Token is missing the calendar.readonly scope. Re-run scripts/google_oauth_z2tc.py "
            "to re-consent with the calendar scope added."
        )
    return creds


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--calendar", default=None, help="Calendar name substring (default: list all and exit).")
    ap.add_argument("--days-back", type=int, default=30)
    ap.add_argument("--days-ahead", type=int, default=90)
    args = ap.parse_args()

    svc = build("calendar", "v3", credentials=_load_creds(), cache_discovery=False)

    cals = svc.calendarList().list().execute().get("items", [])
    if not args.calendar:
        print("Calendars available:")
        for c in cals:
            print(f"  - {c.get('summary')}  (id: {c.get('id')})")
        print("\nRe-run with --calendar <name substring> to dump events.")
        return 0

    match = next((c for c in cals if args.calendar.lower() in (c.get("summary") or "").lower()), None)
    if not match:
        sys.exit(f"No calendar matching {args.calendar!r}. Available: {[c.get('summary') for c in cals]}")

    now = datetime.now(timezone.utc)
    time_min = (now - timedelta(days=args.days_back)).isoformat()
    time_max = (now + timedelta(days=args.days_ahead)).isoformat()

    events: list[dict] = []
    page_token = None
    while True:
        resp = svc.events().list(
            calendarId=match["id"], timeMin=time_min, timeMax=time_max,
            singleEvents=True, orderBy="startTime", maxResults=2500, pageToken=page_token,
        ).execute()
        events.extend(resp.get("items", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    print(f"# {match.get('summary')} — {len(events)} events ({args.days_back}d back, {args.days_ahead}d ahead)\n")
    titles: Counter[str] = Counter()
    for ev in events:
        start = ev.get("start", {}).get("date") or ev.get("start", {}).get("dateTime", "")[:10]
        summary = (ev.get("summary") or "").strip()
        titles[summary] += 1
        print(f"{start}  {summary}")

    print("\n# Distinct workout titles (by frequency):")
    for title, n in titles.most_common():
        print(f"  {n:>3}  {title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
