"""Logged-in Strava browser session via saved storage state.

You log in manually once in a headed browser — handling email/password, 2FA, and any
captcha yourself. The moment login is confirmed we capture Playwright ``storage_state``
(cookies + localStorage) to ``auth/strava_state.json`` and reuse it for every later run.

We capture the state immediately on confirmation rather than relying on a persistent
profile's on-disk cookie flush, which races with browser shutdown and can drop the
freshly-set auth cookie. No credentials are ever stored in or handled by code.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from playwright.sync_api import BrowserContext, Page, sync_playwright

# feeds/strava/session.py -> repo root is three parents up.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATE_PATH = PROJECT_ROOT / "auth" / "strava_state.json"

BASE_URL = "https://www.strava.com"
LOGIN_URL = f"{BASE_URL}/login"
DASHBOARD_URL = f"{BASE_URL}/dashboard"

# A realistic UA reduces the odds of being served a degraded/blocked page.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def is_logged_in(page: Page) -> bool:
    """Heuristic: Strava bounces unauthenticated users to /login. If we can sit on
    an authenticated route without being redirected there, we're logged in."""
    return "/login" not in page.url and "/legal" not in page.url


def _new_context(
    pw, *, headless: bool, storage_state: Path | str | None, slow_mo_ms: int = 0
) -> BrowserContext:
    browser = pw.chromium.launch(headless=headless, slow_mo=slow_mo_ms)
    context = browser.new_context(
        storage_state=str(storage_state) if storage_state else None,
        user_agent=USER_AGENT,
        viewport={"width": 1280, "height": 900},
        locale="en-US",
    )
    # Mask the most obvious headless automation tell so reused sessions aren't
    # bounced as bots on profile pages.
    context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    )
    return context


@contextmanager
def strava_session(
    *,
    headless: bool = True,
    state_path: Path | str = DEFAULT_STATE_PATH,
    slow_mo_ms: int = 0,
) -> Iterator[Page]:
    """Yield a Playwright Page backed by the saved, logged-in Strava session.

    Raises RuntimeError if no valid session exists; run `python main.py login` first.
    """
    state_path = Path(state_path)
    if not state_path.exists():
        raise RuntimeError(
            f"No saved session at {state_path}. Run `python main.py login` first."
        )

    with sync_playwright() as pw:
        context = _new_context(
            pw, headless=headless, storage_state=state_path, slow_mo_ms=slow_mo_ms
        )
        page = context.new_page()
        try:
            page.goto(DASHBOARD_URL, wait_until="domcontentloaded", timeout=30_000)
            if not is_logged_in(page):
                raise RuntimeError(
                    "Saved Strava session is expired or invalid. Re-run "
                    "`python main.py login`."
                )
            yield page
        finally:
            context.close()


def session_status(
    state_path: Path | str = DEFAULT_STATE_PATH,
) -> tuple[bool, str | None]:
    """Check whether the saved session is logged in, without scraping.

    Returns (logged_in, athlete_name). Runs headless and never raises.
    """
    state_path = Path(state_path)
    if not state_path.exists():
        return False, None

    with sync_playwright() as pw:
        context = _new_context(pw, headless=True, storage_state=state_path)
        page = context.new_page()
        try:
            page.goto(DASHBOARD_URL, wait_until="domcontentloaded", timeout=30_000)
            logged_in = is_logged_in(page)
            who = _current_athlete_name(page) if logged_in else None
            return logged_in, who
        except Exception:
            return False, None
        finally:
            context.close()


def _current_athlete_name(page: Page) -> str | None:
    try:
        return page.evaluate(
            """() => {
                const el = document.querySelector(
                    '.user-menu .athlete-name, [data-testid="owner-name"], '
                    + '.user-nav .athlete-name'
                );
                return el ? el.innerText.trim() : null;
            }"""
        )
    except Exception:
        return None


def ensure_login(state_path: Path | str = DEFAULT_STATE_PATH) -> bool:
    """Open a headed browser for a one-time manual login and save the session state.

    Returns True once login is confirmed and storage state is written. Safe to re-run.
    """
    state_path = Path(state_path)
    state_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        # Start clean: a fresh context so a stale logged-out cookie can't interfere.
        context = _new_context(pw, headless=False, storage_state=None)
        page = context.new_page()
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
        print(
            "\nA browser window is open. Log in to Strava (email/password, 2FA, "
            "captcha as needed).\nWaiting for login to complete..."
        )

        try:
            # Strava lands authenticated users on the dashboard/feed after login.
            page.wait_for_url(
                lambda url: "/login" not in url and "/dashboard" in url,
                timeout=300_000,
            )
        except Exception:
            page.goto(DASHBOARD_URL, wait_until="domcontentloaded", timeout=30_000)

        if not is_logged_in(page):
            print("Login not detected. Re-run `python main.py login` to try again.")
            context.close()
            return False

        # Capture the authenticated state NOW, before closing, to avoid the
        # browser-shutdown cookie-flush race.
        context.storage_state(path=str(state_path))
        context.close()
        print("Login detected — session saved to", state_path)
        return True
