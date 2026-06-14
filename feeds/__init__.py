"""Data feeds: adapters that normalize external sources into the canonical store.

Each feed's job ends when validated structured data lands in the store; the engine
and renderers never depend on how a feed obtained its data (scrape vs API).
"""
