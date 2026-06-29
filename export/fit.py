"""Garmin ``.FIT`` structured-workout encoder.

One FIT workout file per running session, with per-step pace-band speed targets so the watch shows
"too fast / too slow" alerts. Rep blocks are pre-flattened by :mod:`export.structured`, so this is a
straight serialize of the step list. The optional ``fit-tool`` dependency is imported lazily, so the
rest of the package works without it installed.

FIT encodes a step's pace target as ``custom_target_value_{low,high}`` in mm/s (scale 1000) with
``target_type = SPEED``; slower pace → lower speed.
"""

from __future__ import annotations

import re

from export.structured import ExportRepeat, ExportStep, ExportWorkout, plan_to_workouts

_MPS_SCALE = 1000  # FIT speed raw unit is mm/s


def _require_fit_tool():
    try:
        from fit_tool.fit_file_builder import FitFileBuilder  # noqa: F401
    except ImportError as exc:  # pragma: no cover - exercised only without the optional dep
        raise RuntimeError(
            "FIT export needs the optional 'fit-tool' package. Install it with: pip install fit-tool"
        ) from exc


def _intensity(step_intensity: str):
    from fit_tool.profile.profile_type import Intensity

    return {
        "warmup": Intensity.WARMUP,
        "cooldown": Intensity.COOLDOWN,
        "recovery": Intensity.RECOVERY,
        "interval": Intensity.INTERVAL,
        "rest": Intensity.REST,
    }.get(step_intensity, Intensity.ACTIVE)


def _step_message(step: ExportStep, index: int):
    from fit_tool.profile.messages.workout_step_message import WorkoutStepMessage
    from fit_tool.profile.profile_type import WorkoutStepDuration, WorkoutStepTarget

    m = WorkoutStepMessage()
    m.message_index = index
    m.workout_step_name = step.label[:30]
    m.intensity = _intensity(step.intensity)

    if step.duration_type == "distance" and step.distance_m:
        m.duration_type = WorkoutStepDuration.DISTANCE
        m.duration_distance = float(step.distance_m)
    elif step.duration_type == "time" and step.time_s:
        m.duration_type = WorkoutStepDuration.TIME
        m.duration_time = float(step.time_s)
    else:
        m.duration_type = WorkoutStepDuration.OPEN

    lo, hi = step.speed_low_mps, step.speed_high_mps
    if lo and hi:
        m.target_type = WorkoutStepTarget.SPEED
        m.custom_target_value_low = round(lo * _MPS_SCALE)
        m.custom_target_value_high = round(hi * _MPS_SCALE)
    else:
        m.target_type = WorkoutStepTarget.OPEN
    return m


def _repeat_message(from_index: int, count: int, index: int):
    """A FIT control step: loop back to ``from_index`` until the block has run ``count`` times."""
    from fit_tool.profile.messages.workout_step_message import WorkoutStepMessage
    from fit_tool.profile.profile_type import WorkoutStepDuration

    m = WorkoutStepMessage()
    m.message_index = index
    m.duration_type = WorkoutStepDuration.REPEAT_UNTIL_STEPS_CMPLT
    m.duration_step = from_index
    m.target_repeat_steps = count
    return m


def workout_to_fit(ew: ExportWorkout) -> bytes:
    """Encode one running :class:`ExportWorkout` as FIT bytes, with native repeat loops for rep
    blocks (e.g. 5 × [1000 m @ I, 2:00 jog])."""
    _require_fit_tool()
    from fit_tool.fit_file_builder import FitFileBuilder
    from fit_tool.profile.messages.file_id_message import FileIdMessage
    from fit_tool.profile.messages.workout_message import WorkoutMessage
    from fit_tool.profile.profile_type import FileType, Manufacturer, Sport

    builder = FitFileBuilder(auto_define=True)

    fid = FileIdMessage()
    fid.type = FileType.WORKOUT
    fid.manufacturer = Manufacturer.DEVELOPMENT.value
    fid.product = 0
    fid.serial_number = 1
    builder.add(fid)

    step_messages = []
    for item in ew.steps:
        if isinstance(item, ExportRepeat):
            block_start = len(step_messages)
            for inner in item.steps:
                step_messages.append(_step_message(inner, len(step_messages)))
            step_messages.append(_repeat_message(block_start, item.count, len(step_messages)))
        elif item.intensity != "rest":
            step_messages.append(_step_message(item, len(step_messages)))

    wkt = WorkoutMessage()
    wkt.workout_name = ew.description[:30]
    wkt.sport = Sport.RUNNING
    wkt.num_valid_steps = len(step_messages)
    builder.add(wkt)
    for m in step_messages:
        builder.add(m)

    return builder.build().to_bytes()


def fit_filename(ew: ExportWorkout) -> str:
    kind = re.sub(r"[^a-z0-9]+", "-", ew.kind.lower()).strip("-")
    stem = f"w{ew.week_index:02d}-{ew.day.lower()}-{ew.date or 'tbd'}-{kind}"
    return f"{stem}.fit"


def plan_to_fit(plan) -> list[tuple[str, bytes]]:
    """``(filename, fit_bytes)`` for every running session (cross-training is skipped — no pace)."""
    out: list[tuple[str, bytes]] = []
    for ew in plan_to_workouts(plan, running_only=True):
        if not ew.steps:
            continue
        out.append((fit_filename(ew), workout_to_fit(ew)))
    return out
