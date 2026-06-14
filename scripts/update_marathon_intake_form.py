#!/usr/bin/env python3
"""Update the club marathon intake Google Form for any 2026 goal marathon.

- Removes questions that look Chicago-travel-specific (hotel / flights / fly-in).
- Appends a universal **2026 marathon** section (primary race, date, goals, travel
  coordination for *any* destination, optional second race).

Uses the Google Forms API. Requires:

1. **Google Forms API enabled** on the GCP project tied to your OAuth client
   (see error URL if you get ``SERVICE_DISABLED``).
2. A token with ``https://www.googleapis.com/auth/forms.body`` — run once::

       python scripts/google_oauth_z2tc.py

   then ``export Z2TC_GOOGLE_TOKEN=.../auth/z2tc_google_token.json``.

Usage::

    python scripts/update_marathon_intake_form.py --dry-run   # list items; no writes
    python scripts/update_marathon_intake_form.py --apply    # batchUpdate the form

Environment::

    Z2TC_INTAKE_FORM_ID   default: legacy club form id
    Z2TC_GOOGLE_TOKEN     path to token JSON (see above)
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_FORM_ID = "12Vft9B-yZwsL-x-11Y01fUaOZuYW-1I-yod-bdkxx5s"

# Titles/descriptions matching these (case-insensitive) are removed as Chicago-only travel.
_DELETE_PATTERNS = re.compile(
    r"(hotel|motel|airbnb|lodging|"
    r"fly\s*in|fly\s*out|flying|flight|"
    r"when\s+are\s+you\s+(flying|arriving|landing)|"
    r"what\s+hotel|which\s+hotel|"
    r"arrival\s+date|departure\s+date|"
    r"plane\s+ticket)",
    re.I,
)


def _load_creds():
    """Token must include ``forms.body`` (use ``google_oauth_z2tc.py``)."""
    os.environ.setdefault("Z2TC_GOOGLE_TOKEN", str(ROOT / "auth" / "z2tc_google_token.json"))
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from render.runtime import token_path

    p = token_path()
    if not p.exists():
        raise FileNotFoundError(
            f"No token at {p}. Run: python scripts/google_oauth_z2tc.py\n"
            "Then: export Z2TC_GOOGLE_TOKEN=.../auth/z2tc_google_token.json"
        )
    creds = Credentials.from_authorized_user_file(str(p))
    if "https://www.googleapis.com/auth/forms.body" not in (creds.scopes or []):
        raise RuntimeError(
            "Token is missing the forms.body scope. Run python scripts/google_oauth_z2tc.py "
            "with the z2tc OAuth client and set Z2TC_GOOGLE_TOKEN to the new file."
        )
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            p.write_text(creds.to_json())
        else:
            raise RuntimeError("Token invalid; run google_oauth_z2tc.py again.")
    return creds


def _forms():
    from googleapiclient.discovery import build

    return build("forms", "v1", credentials=_load_creds(), cache_discovery=False)


def _item_text(it: dict) -> str:
    parts = [it.get("title") or "", it.get("description") or ""]
    qi = it.get("questionItem") or {}
    q = qi.get("question") or {}
    parts.append(q.get("questionId") or "")
    return "\n".join(parts)


def _should_delete(it: dict) -> bool:
    if not it:
        return False
    if it.get("pageBreakItem") or it.get("textItem") or it.get("imageItem"):
        # keep layout/media unless clearly travel (unlikely)
        t = _item_text(it)
        return bool(_DELETE_PATTERNS.search(t))
    if it.get("questionItem"):
        return bool(_DELETE_PATTERNS.search(_item_text(it)))
    return False


def _marathon_choice_options():
    return [
        {"value": "Bank of America Chicago Marathon"},
        {"value": "TCS New York City Marathon"},
        {"value": "Berlin Marathon"},
        {"value": "London Marathon"},
        {"value": "Boston Marathon"},
        {"value": "California International Marathon (CIM)"},
        {"value": "Houston Marathon"},
        {"value": "Marine Corps Marathon"},
        {"value": "Twin Cities Marathon"},
        {"value": "Grandma's Marathon"},
        {"value": "Other (write exact race in the next question)"},
    ]


def _append_universal_items(start_index: int) -> list[dict]:
    """batchUpdate requests: createItem at increasing indices (all after start_index)."""
    idx = start_index
    reqs: list[dict] = []

    def add(item: dict) -> None:
        nonlocal idx, reqs
        reqs.append({"createItem": {"item": item, "location": {"index": idx}}})
        idx += 1

    add(
        {
            "title": "2026 Marathon — everyone",
            "description": (
                "This club trains on different 2026 goal marathons (Chicago, NYC, Berlin, "
                "etc.). Answer for **your** primary race. We use the travel block only if "
                "you want help coordinating near the race — put N/A if you live there or "
                "prefer not to share."
            ),
            "textItem": {},
        }
    )
    add(
        {
            "title": "Full name",
            "questionItem": {
                "question": {
                    "required": True,
                    "textQuestion": {"paragraph": False},
                }
            },
        }
    )
    add(
        {
            "title": "Strava profile URL or numeric athlete ID",
            "questionItem": {
                "question": {
                    "required": True,
                    "textQuestion": {"paragraph": False},
                }
            },
        }
    )
    add(
        {
            "title": "Which marathon is your **primary** A race in 2026?",
            "questionItem": {
                "question": {
                    "required": True,
                    "choiceQuestion": {
                        "type": "DROP_DOWN",
                        "options": _marathon_choice_options(),
                        "shuffle": False,
                    },
                }
            },
        }
    )
    add(
        {
            "title": "If you chose “Other”, what is the exact race name and city?",
            "description": "If you did not choose Other, answer N/A.",
            "questionItem": {
                "question": {
                    "required": False,
                    "textQuestion": {"paragraph": True},
                }
            },
        }
    )
    add(
        {
            "title": "Primary marathon date",
            "description": "Use the official race date (calendar picker).",
            "questionItem": {
                "question": {
                    "required": True,
                    "dateQuestion": {"includeTime": False, "includeYear": True},
                }
            },
        }
    )
    add(
        {
            "title": "Goal finish time for that primary marathon",
            "description": "e.g. 3:25:00 — or a short note like “sub-4” / “finish healthy”.",
            "questionItem": {
                "question": {
                    "required": True,
                    "textQuestion": {"paragraph": False},
                }
            },
        }
    )
    add(
        {
            "title": "Second 2026 marathon (optional)",
            "description": "Name + date if you are also racing another marathon (e.g. NYC after Chicago). Otherwise N/A.",
            "questionItem": {
                "question": {
                    "required": False,
                    "textQuestion": {"paragraph": True},
                }
            },
        }
    )
    add(
        {
            "title": "How many days per week can you run?",
            "questionItem": {
                "question": {
                    "required": True,
                    "choiceQuestion": {
                        "type": "RADIO",
                        "options": [{"value": str(n)} for n in range(3, 8)],
                    },
                }
            },
        }
    )
    add(
        {
            "title": "Club long run",
            "description": "Group long runs are **Saturday** for everyone in this intake.",
            "textItem": {},
        }
    )
    add(
        {
            "title": "Race-weekend coordination (any marathon)",
            "description": (
                "Optional: if your **primary** race involves travel and you want the group "
                "to coordinate (shared rides, spectating, shakeout runs), share rough arrival, "
                "departure, and where you are staying (hotel / with friends / etc.). "
                "If you live at the race location or do not want to share, answer **N/A**."
            ),
            "questionItem": {
                "question": {
                    "required": False,
                    "textQuestion": {"paragraph": True},
                }
            },
        }
    )
    add(
        {
            "title": "Injury history or current niggles",
            "questionItem": {
                "question": {
                    "required": False,
                    "textQuestion": {"paragraph": True},
                }
            },
        }
    )
    add(
        {
            "title": "Anything else for the coach",
            "questionItem": {
                "question": {
                    "required": False,
                    "textQuestion": {"paragraph": True},
                }
            },
        }
    )
    return reqs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--form-id", default=os.environ.get("Z2TC_INTAKE_FORM_ID", DEFAULT_FORM_ID))
    parser.add_argument("--dry-run", action="store_true", help="List items and exit.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply deletes + append universal section (destructive; re-link Sheet if needed).",
    )
    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        parser.error("Specify --dry-run or --apply")

    svc = _forms()
    form = svc.forms().get(formId=args.form_id).execute()
    title = (form.get("info") or {}).get("title", "")
    items = form.get("items") or []
    print(f"Form: {title!r}  id={args.form_id}  items={len(items)}")

    to_delete: list[int] = []
    for i, it in enumerate(items):
        t = _item_text(it)[:120].replace("\n", " ")
        mark = "DELETE" if _should_delete(it) else "keep"
        print(f"  [{i:3d}] {mark:6s} {t!r}")
        if _should_delete(it):
            to_delete.append(i)

    if args.dry_run:
        print(f"\n--dry-run: would delete {len(to_delete)} item(s) at indices {to_delete}")
        print(f"Would append universal block ({len(_append_universal_items(0))} new items) at end.")
        return 0

    requests: list[dict] = []
    for i in sorted(to_delete, reverse=True):
        requests.append({"deleteItem": {"location": {"index": i}}})

    if requests:
        svc.forms().batchUpdate(formId=args.form_id, body={"requests": requests}).execute()
        print(f"Deleted {len(to_delete)} item(s).")

    form = svc.forms().get(formId=args.form_id).execute()
    n = len(form.get("items") or [])
    append_reqs = _append_universal_items(n)
    if append_reqs:
        svc.forms().batchUpdate(formId=args.form_id, body={"requests": append_reqs}).execute()
        print(f"Appended {len(append_reqs)} universal item(s) at index {n}.")

    info_up = {
        "requests": [
            {
                "updateFormInfo": {
                    "info": {
                        "title": title or "Zone 2 Track Club — 2026 Marathon Intake",
                        "description": (
                            "Universal intake for **any** 2026 goal marathon. Travel / hotel "
                            "questions are replaced by one optional coordination box that works "
                            "for Chicago, NYC, Berlin, or hometown races (use N/A when not relevant)."
                        ),
                    },
                    "updateMask": "title,description",
                }
            }
        ]
    }
    svc.forms().batchUpdate(formId=args.form_id, body=info_up).execute()
    print("Updated form title/description.")
    print("\nNext: open the form in the browser, reorder sections if you want new block at top,")
    print("and confirm the linked Google Sheet still matches your column mapping.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
