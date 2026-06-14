"""Deterministic training engine: VDOT, training paces, and plan generation.

Pure functions over structured data — no IO, no network. The numbers are reproducible
and unit-testable so plan output never depends on a model's discretion.
"""
