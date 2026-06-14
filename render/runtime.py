"""Google API credential loading for the Sheets renderer.

We do **not** run our own OAuth consent flow by default. Hermes already holds an
authorized-user token at ``~/.hermes/google_token.json`` whose scopes include
``spreadsheets`` and ``drive.readonly`` plus a refresh token, so we reuse it directly
(``google.oauth2.credentials.Credentials.from_authorized_user_file``). Both paths are
overridable via env vars so the repo isn't pinned to one machine's home directory:

    Z2TC_GOOGLE_TOKEN          path to the authorized-user token JSON
    Z2TC_GOOGLE_CLIENT_SECRET  path to the installed-app client secret JSON

If the token is expired we refresh it with the refresh token and write the refreshed
token back to the same file (so the next run starts valid).
"""

from __future__ import annotations

import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import Resource, build

# Scopes this app actually uses. The reused Hermes token already grants these (and more);
# this list only matters if a first-time consent flow is ever run.
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

_HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
DEFAULT_TOKEN_PATH = _HERMES_HOME / "google_token.json"
DEFAULT_CLIENT_SECRET_PATH = _HERMES_HOME / "google_client_secret.json"


def token_path() -> Path:
    return Path(os.environ.get("Z2TC_GOOGLE_TOKEN", DEFAULT_TOKEN_PATH))


def client_secret_path() -> Path:
    return Path(os.environ.get("Z2TC_GOOGLE_CLIENT_SECRET", DEFAULT_CLIENT_SECRET_PATH))


def load_credentials() -> Credentials:
    """Load the authorized-user token, refreshing (and persisting) it if expired."""
    path = token_path()
    if not path.exists():
        raise FileNotFoundError(
            f"No Google token at {path}. Set Z2TC_GOOGLE_TOKEN, or run a consent flow "
            "to create one. The Sheets renderer needs the 'spreadsheets' scope."
        )
    creds = Credentials.from_authorized_user_file(str(path))
    if not creds.valid:
        if not (creds.expired and creds.refresh_token):
            raise RuntimeError(
                f"Google credentials at {path} are invalid and cannot be refreshed "
                "(no refresh token). Re-authorize the token."
            )
        creds.refresh(Request())
        path.write_text(creds.to_json())
    return creds


def sheets_service() -> Resource:
    """A Google Sheets API v4 client (``service.spreadsheets()...``)."""
    return build("sheets", "v4", credentials=load_credentials(), cache_discovery=False)


def drive_service() -> Resource:
    """A Google Drive API v3 client. Read-only with the reused Hermes token."""
    return build("drive", "v3", credentials=load_credentials(), cache_discovery=False)


def whoami() -> dict:
    """Return the Google account this token belongs to (a cheap connectivity check)."""
    about = drive_service().about().get(fields="user").execute()
    return about.get("user", {})
