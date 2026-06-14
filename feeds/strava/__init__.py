"""Strava feed — logged-in profile and weekly training-history scraping (Playwright).

Today this authenticates with a saved browser session; the call site (``strava_session``,
``scrape_athlete``, ``scrape_training_history``) is designed to stay stable when this is
later swapped for the Strava OAuth API.
"""
