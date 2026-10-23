"""Per-athlete Garmin Connect sessions backed by saved OAuth token stores.

Enrollment (`garmin_login`) prompts for the athlete's Garmin email/password (and MFA
code if their account requires it), performs the mobile-SSO login once, and writes
only the resulting OAuth access+refresh tokens to ``auth/garmin/<athlete-id>/``.
Credentials are read via getpass, passed straight to the library, and never persisted.

Steady state (`garmin_client`) resumes from the token store with no credentials; the
library refreshes the access token automatically before each request.
"""

from __future__ import annotations

import getpass
from pathlib import Path

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

# feeds/garmin/session.py -> repo root is three parents up.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
GARMIN_AUTH_DIR = PROJECT_ROOT / "auth" / "garmin"


def tokenstore_path(athlete_id: str) -> Path:
    """Directory holding the saved OAuth tokens for one athlete."""
    return GARMIN_AUTH_DIR / athlete_id


def is_connected(athlete_id: str) -> bool:
    """True if a token store exists for this athlete (does not validate it)."""
    path = tokenstore_path(athlete_id)
    return path.exists() and any(path.iterdir())


def list_connected() -> list[str]:
    """Athlete ids that have a saved Garmin token store."""
    if not GARMIN_AUTH_DIR.exists():
        return []
    return sorted(p.name for p in GARMIN_AUTH_DIR.iterdir() if p.is_dir())


def garmin_client(athlete_id: str) -> Garmin:
    """Resume a logged-in client from the athlete's saved tokens (no credentials).

    Raises RuntimeError if the athlete has never enrolled or the saved tokens are
    no longer usable — in both cases the fix is `python main.py garmin-login <id>`.
    """
    store = tokenstore_path(athlete_id)
    if not is_connected(athlete_id):
        raise RuntimeError(
            f"No Garmin tokens for athlete {athlete_id!r}. "
            f"Run `python main.py garmin-login {athlete_id}` first."
        )
    client = Garmin()
    try:
        client.login(str(store))
    except (FileNotFoundError, GarminConnectAuthenticationError) as exc:
        raise RuntimeError(
            f"Saved Garmin tokens for {athlete_id!r} are invalid or expired. "
            f"Re-run `python main.py garmin-login {athlete_id}`."
        ) from exc
    return client


def garmin_login(
    athlete_id: str,
    *,
    email: str | None = None,
    password: str | None = None,
) -> Garmin:
    """One-time interactive enrollment: credential login, then persist tokens only.

    Prompts on the terminal for anything not supplied (password via getpass; MFA
    code if Garmin asks for one). Safe to re-run; overwrites the token store.
    """
    store = tokenstore_path(athlete_id)
    store.mkdir(parents=True, exist_ok=True)

    if not email:
        email = input(f"Garmin Connect email for {athlete_id}: ").strip()
    if not password:
        password = getpass.getpass("Garmin Connect password (not stored): ")

    client = Garmin(
        email=email,
        password=password,
        prompt_mfa=lambda: input("MFA one-time code: ").strip(),
    )
    try:
        # Passing the tokenstore path makes the library persist tokens on success
        # (and resume from them on re-runs, skipping the credential login).
        client.login(str(store))
    except GarminConnectAuthenticationError as exc:
        raise RuntimeError(f"Garmin login failed (bad credentials?): {exc}") from exc
    except (GarminConnectConnectionError, GarminConnectTooManyRequestsError) as exc:
        raise RuntimeError(f"Garmin login failed: {exc}") from exc
    return client


def session_status(athlete_id: str) -> tuple[bool, str | None]:
    """(connected, display_name) for one athlete's saved session. Never raises."""
    try:
        client = garmin_client(athlete_id)
        return True, client.get_full_name()
    except Exception:
        return False, None
