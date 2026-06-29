"""Plan interop exports.

Turn a deterministic :class:`engine.plan.models.TrainingPlan` into portable artifacts that other
training platforms consume:

- :mod:`export.structured` — a platform-neutral structured-workout IR + normalizer. Both exporters
  below consume it, so the pace-band / repeat / duration logic lives in one place.
- :mod:`export.ics` — an iCalendar feed (schedule + workout description), subscribable in Google /
  Apple / Garmin Connect calendars. Pure stdlib.
- :mod:`export.fit` — Garmin ``.FIT`` structured workout files (device-executable, pace-target
  alerts). Lazily imports the optional ``fit-tool`` dependency.

The plan engine stays pure and import-free of this layer.
"""

from __future__ import annotations

from export.structured import ExportRepeat, ExportStep, ExportWorkout, plan_to_workouts

__all__ = ["ExportRepeat", "ExportStep", "ExportWorkout", "plan_to_workouts"]
