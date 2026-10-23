"""Garmin Connect feed (unofficial API via the `garminconnect` library).

Per-athlete auth: unlike Strava's single club-coach browser session, Garmin data is
private to each account, so every athlete enrolls once (`python main.py garmin-login
<athlete-id>`) and we persist only OAuth tokens — never credentials — under
``auth/garmin/<athlete-id>/``. Tokens auto-refresh; a credentialed re-login is only
needed if the refresh token expires or is revoked.
"""
