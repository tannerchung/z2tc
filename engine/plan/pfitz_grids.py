"""Verbatim Pfitzinger Advanced Marathoning ch.8 (≤55 mpw) — 18-wk daily grid.

Transcribed day-by-day from Advanced Marathoning pp.292–295 (4e).
"""

from __future__ import annotations

from .models import GridCell, WorkoutKind

# 18 entries, marathon week last (includes taper descent).
CH8_18WK_TOTALS_MI: tuple[float, ...] = (
    33.0,
    33.0,
    33.0,
    32.0,
    40.0,
    40.0,
    40.0,
    37.6,
    47.0,
    47.0,
    47.0,
    43.2,
    55.0,
    55.0,
    55.0,
    43.2,
    33.5,
    24.3,
)


def ch8_down_week_flags(totals: tuple[float, ...] = CH8_18WK_TOTALS_MI) -> tuple[bool, ...]:
    """Mark recovery/down weeks when the published weekly total drops materially."""
    out: list[bool] = []
    prev: float | None = None
    for i, t in enumerate(totals):
        if prev is not None and t < prev - 0.75:
            out.append(True)
        else:
            out.append(False)
        prev = t
    return tuple(out)


# Verbatim 18-week schedule for up-to-55 miles per week
CH8_18WK_GRID: list[list[GridCell]] = [
    # Week 1 (17 weeks to goal)
    [
        GridCell(WorkoutKind.REST, text="Rest or cross-training"),
        GridCell(WorkoutKind.THRESHOLD, miles=8.0, text="Lactate threshold 8 mi w/ 4 mi @ 15K to half marathon race pace", segment_hints=[{"reps": 1, "pace_label": "T", "distance_m": 6437.376}]),
        GridCell(WorkoutKind.REST, text="Rest or cross-training"),
        GridCell(WorkoutKind.GENERAL_AEROBIC, miles=9.0, text="General aerobic 9 mi"),
        GridCell(WorkoutKind.REST, text="Rest or cross-training"),
        GridCell(WorkoutKind.RECOVERY, miles=4.0, text="Recovery 4 mi"),
        GridCell(WorkoutKind.MEDIUM_LONG, miles=12.0, text="Medium-long run 12 mi"),
    ],
    # Week 2 (16 weeks to goal)
    [
        GridCell(WorkoutKind.REST, text="Rest or cross-training"),
        GridCell(WorkoutKind.GENERAL_AEROBIC, miles=8.0, text="General aerobic + speed 8 mi w/ 10 x 100 m strides", segment_hints=[{"reps": 10, "pace_label": "R", "distance_m": 100.0, "recovery": "jog"}]),
        GridCell(WorkoutKind.REST, text="Rest or cross-training"),
        GridCell(WorkoutKind.GENERAL_AEROBIC, miles=10.0, text="General aerobic 10 mi"),
        GridCell(WorkoutKind.REST, text="Rest or cross-training"),
        GridCell(WorkoutKind.RECOVERY, miles=5.0, text="Recovery 5 mi"),
        GridCell(WorkoutKind.MARATHON_PACE, miles=13.0, text="Marathon-pace run 13 mi w/ 8 mi @ marathon race pace", segment_hints=[{"reps": 1, "pace_label": "M", "distance_m": 12874.752}]),
    ],
    # Week 3 (15 weeks to goal)
    [
        GridCell(WorkoutKind.REST, text="Rest or cross-training"),
        GridCell(WorkoutKind.GENERAL_AEROBIC, miles=10.0, text="General aerobic 10 mi"),
        GridCell(WorkoutKind.RECOVERY, miles=4.0, text="Recovery 4 mi"),
        GridCell(WorkoutKind.THRESHOLD, miles=8.0, text="Lactate threshold 8 mi w/ 4 mi @ 15K to half marathon race pace", segment_hints=[{"reps": 1, "pace_label": "T", "distance_m": 6437.376}]),
        GridCell(WorkoutKind.REST, text="Rest or cross-training"),
        GridCell(WorkoutKind.RECOVERY, miles=4.0, text="Recovery 4 mi"),
        GridCell(WorkoutKind.MEDIUM_LONG, miles=14.0, text="Medium-long run 14 mi"),
    ],
    # Week 4 (14 weeks to goal)
    [
        GridCell(WorkoutKind.REST, text="Rest or cross-training"),
        GridCell(WorkoutKind.GENERAL_AEROBIC, miles=8.0, text="General aerobic + speed 8 mi w/ 10 x 100 m strides", segment_hints=[{"reps": 10, "pace_label": "R", "distance_m": 100.0, "recovery": "jog"}]),
        GridCell(WorkoutKind.RECOVERY, miles=5.0, text="Recovery 5 mi"),
        GridCell(WorkoutKind.GENERAL_AEROBIC, miles=10.0, text="General aerobic 10 mi"),
        GridCell(WorkoutKind.REST, text="Rest or cross-training"),
        GridCell(WorkoutKind.RECOVERY, miles=4.0, text="Recovery 4 mi"),
        GridCell(WorkoutKind.MEDIUM_LONG, miles=15.0, text="Medium-long run 15 mi"),
    ],
    # Week 5 (13 weeks to goal)
    [
        GridCell(WorkoutKind.REST, text="Rest or cross-training"),
        GridCell(WorkoutKind.THRESHOLD, miles=9.0, text="Lactate threshold 9 mi w/ 5 mi @ 15K to half marathon race pace", segment_hints=[{"reps": 1, "pace_label": "T", "distance_m": 8046.72}]),
        GridCell(WorkoutKind.RECOVERY, miles=5.0, text="Recovery 5 mi"),
        GridCell(WorkoutKind.GENERAL_AEROBIC, miles=10.0, text="General aerobic 10 mi"),
        GridCell(WorkoutKind.REST, text="Rest or cross-training"),
        GridCell(WorkoutKind.RECOVERY, miles=5.0, text="Recovery 5 mi"),
        GridCell(WorkoutKind.MARATHON_PACE, miles=16.0, text="Marathon-pace run 16 mi w/ 10 mi @ marathon race pace", segment_hints=[{"reps": 1, "pace_label": "M", "distance_m": 16093.44}]),
    ],
    # Week 6 (12 weeks to goal - Recovery)
    [
        GridCell(WorkoutKind.REST, text="Rest or cross-training"),
        GridCell(WorkoutKind.GENERAL_AEROBIC, miles=8.0, text="General aerobic + speed 8 mi w/ 10 x 100 m strides", segment_hints=[{"reps": 10, "pace_label": "R", "distance_m": 100.0, "recovery": "jog"}]),
        GridCell(WorkoutKind.RECOVERY, miles=5.0, text="Recovery 5 mi"),
        GridCell(WorkoutKind.GENERAL_AEROBIC, miles=8.0, text="General aerobic 8 mi"),
        GridCell(WorkoutKind.REST, text="Rest or cross-training"),
        GridCell(WorkoutKind.RECOVERY, miles=4.0, text="Recovery 4 mi"),
        GridCell(WorkoutKind.MEDIUM_LONG, miles=12.0, text="Medium-long run 12 mi"),
    ],
    # Week 7 (11 weeks to goal)
    [
        GridCell(WorkoutKind.REST, text="Rest or cross-training"),
        GridCell(WorkoutKind.THRESHOLD, miles=10.0, text="Lactate threshold 10 mi w/ 5 mi @ 15K to half marathon race pace", segment_hints=[{"reps": 1, "pace_label": "T", "distance_m": 8046.72}]),
        GridCell(WorkoutKind.RECOVERY, miles=4.0, text="Recovery 4 mi"),
        GridCell(WorkoutKind.MEDIUM_LONG, miles=11.0, text="Medium-long run 11 mi"),
        GridCell(WorkoutKind.REST, text="Rest or cross-training"),
        GridCell(WorkoutKind.GENERAL_AEROBIC, miles=7.0, text="General aerobic + speed 7 mi w/ 8 x 100 m strides p.m.", segment_hints=[{"reps": 8, "pace_label": "R", "distance_m": 100.0, "recovery": "jog"}]),
        GridCell(WorkoutKind.LONG, miles=18.0, text="Long run 18 mi"),
    ],
    # Week 8 (10 weeks to goal)
    [
        GridCell(WorkoutKind.REST, text="Rest or cross-training"),
        GridCell(WorkoutKind.RECOVERY, miles=7.0, text="Recovery + speed 7 mi w/ 6 x 100 m strides", segment_hints=[{"reps": 6, "pace_label": "R", "distance_m": 100.0, "recovery": "jog"}]),
        GridCell(WorkoutKind.MEDIUM_LONG, miles=12.0, text="Medium-long run 12 mi"),
        GridCell(WorkoutKind.REST, text="Rest or cross-training"),
        GridCell(WorkoutKind.THRESHOLD, miles=10.0, text="Lactate threshold 10 mi w/ 6 mi @ 15K to half marathon race pace", segment_hints=[{"reps": 1, "pace_label": "T", "distance_m": 9656.064}]),
        GridCell(WorkoutKind.RECOVERY, miles=5.0, text="Recovery 5 mi"),
        GridCell(WorkoutKind.LONG, miles=20.0, text="Long run 20 mi"),
    ],
    # Week 9 (9 weeks to goal)
    [
        GridCell(WorkoutKind.REST, text="Rest or cross-training"),
        GridCell(WorkoutKind.RECOVERY, miles=6.0, text="Recovery 6 mi"),
        GridCell(WorkoutKind.MEDIUM_LONG, miles=14.0, text="Medium-long run 14 mi"),
        GridCell(WorkoutKind.RECOVERY, miles=6.0, text="Recovery 6 mi"),
        GridCell(WorkoutKind.REST, text="Rest or cross-training"),
        GridCell(WorkoutKind.RECOVERY, miles=6.0, text="Recovery + speed 6 mi w/ 6 x 100 m strides", segment_hints=[{"reps": 6, "pace_label": "R", "distance_m": 100.0, "recovery": "jog"}]),
        GridCell(WorkoutKind.MARATHON_PACE, miles=16.0, text="Marathon-pace run 16 mi w/ 12 mi @ marathon race pace", segment_hints=[{"reps": 1, "pace_label": "M", "distance_m": 19312.128}]),
    ],
    # Week 10 (8 weeks to goal - Recovery)
    [
        GridCell(WorkoutKind.REST, text="Rest or cross-training"),
        GridCell(WorkoutKind.GENERAL_AEROBIC, miles=8.0, text="General aerobic 8 mi"),
        GridCell(WorkoutKind.INTERVAL, miles=8.0, text="VO₂max 8 mi w/ 5 x 800 m @ 5K race pace; jog 50 to 90% interval time between", segment_hints=[{"reps": 5, "pace_label": "I", "distance_m": 800.0, "recovery": "50-90% jog"}]),
        GridCell(WorkoutKind.RECOVERY, miles=5.0, text="Recovery 5 mi"),
        GridCell(WorkoutKind.REST, text="Rest or cross-training"),
        GridCell(WorkoutKind.GENERAL_AEROBIC, miles=8.0, text="General aerobic + speed 8 mi w/ 8 x 100 m strides", segment_hints=[{"reps": 8, "pace_label": "R", "distance_m": 100.0, "recovery": "jog"}]),
        GridCell(WorkoutKind.MEDIUM_LONG, miles=14.0, text="Medium-long run 14 mi"),
    ],
    # Week 11 (7 weeks to goal)
    [
        GridCell(WorkoutKind.REST, text="Rest or cross-training"),
        GridCell(WorkoutKind.RECOVERY, miles=7.0, text="Recovery + speed 7 mi w/ 6 x 100 m strides", segment_hints=[{"reps": 6, "pace_label": "R", "distance_m": 100.0, "recovery": "jog"}]),
        GridCell(WorkoutKind.THRESHOLD, miles=11.0, text="Lactate threshold 11 mi w/ 7 mi @ 15K to half marathon race pace", segment_hints=[{"reps": 1, "pace_label": "T", "distance_m": 11265.408}]),
        GridCell(WorkoutKind.REST, text="Rest or cross-training"),
        GridCell(WorkoutKind.MEDIUM_LONG, miles=12.0, text="Medium-long run 12 mi"),
        GridCell(WorkoutKind.RECOVERY, miles=5.0, text="Recovery 5 mi"),
        GridCell(WorkoutKind.LONG, miles=20.0, text="Long run 20 mi"),
    ],
    # Week 12 (6 weeks to goal)
    [
        GridCell(WorkoutKind.REST, text="Rest or cross-training"),
        GridCell(WorkoutKind.INTERVAL, miles=8.0, text="VO₂max 8 mi w/ 5 x 600 m @ 5K race pace; jog 50 to 90% interval time between", segment_hints=[{"reps": 5, "pace_label": "I", "distance_m": 600.0, "recovery": "50-90% jog"}]),
        GridCell(WorkoutKind.MEDIUM_LONG, miles=12.0, text="Medium-long run 12 mi"),
        GridCell(WorkoutKind.REST, text="Rest or cross-training"),
        GridCell(WorkoutKind.RECOVERY, miles=5.0, text="Recovery + speed 5 mi w/ 6 x 100 m strides", segment_hints=[{"reps": 6, "pace_label": "R", "distance_m": 100.0, "recovery": "jog"}]),
        GridCell(WorkoutKind.RACE, miles=11.0, text="8K-15K tune-up race (total 9-13 mi)", segment_hints=[{"reps": 1, "pace_label": "R", "distance_m": 10000.0}]),
        GridCell(WorkoutKind.LONG, miles=17.0, text="Long run 17 mi"),
    ],
    # Week 13 (5 weeks to goal)
    [
        GridCell(WorkoutKind.REST, text="Rest or cross-training"),
        GridCell(WorkoutKind.GENERAL_AEROBIC, miles=8.0, text="General aerobic 8 mi"),
        GridCell(WorkoutKind.INTERVAL, miles=9.0, text="VO₂max 9 mi w/ 5 x 1,000 m @ 5K race pace; jog 50 to 90% interval time between", segment_hints=[{"reps": 5, "pace_label": "I", "distance_m": 1000.0, "recovery": "50-90% jog"}]),
        GridCell(WorkoutKind.REST, text="Rest or cross-training"),
        GridCell(WorkoutKind.MEDIUM_LONG, miles=12.0, text="Medium-long run 12 mi"),
        GridCell(WorkoutKind.RECOVERY, miles=5.0, text="Recovery 5 mi"),
        GridCell(WorkoutKind.MARATHON_PACE, miles=18.0, text="Marathon-pace run 18 mi w/ 14 mi @ marathon race pace", segment_hints=[{"reps": 1, "pace_label": "M", "distance_m": 22530.816}]),
    ],
    # Week 14 (4 weeks to goal)
    [
        GridCell(WorkoutKind.REST, text="Rest or cross-training"),
        GridCell(WorkoutKind.INTERVAL, miles=8.0, text="VO₂max 8 mi w/ 5 x 600 m @ 5K race pace; jog 50 to 90% interval time between", segment_hints=[{"reps": 5, "pace_label": "I", "distance_m": 600.0, "recovery": "50-90% jog"}]),
        GridCell(WorkoutKind.MEDIUM_LONG, miles=11.0, text="Medium-long run 11 mi"),
        GridCell(WorkoutKind.REST, text="Rest or cross-training"),
        GridCell(WorkoutKind.RECOVERY, miles=4.0, text="Recovery + speed 4 mi w/ 6 x 100 m strides", segment_hints=[{"reps": 6, "pace_label": "R", "distance_m": 100.0, "recovery": "jog"}]),
        GridCell(WorkoutKind.RACE, miles=11.0, text="8K-15K tune-up race (total 9-13 mi)", segment_hints=[{"reps": 1, "pace_label": "R", "distance_m": 10000.0}]),
        GridCell(WorkoutKind.LONG, miles=17.0, text="Long run 17 mi"),
    ],
    # Week 15 (3 weeks to goal)
    [
        GridCell(WorkoutKind.REST, text="Rest or cross-training"),
        GridCell(WorkoutKind.RECOVERY, miles=7.0, text="Recovery + speed 7 mi w/ 6 x 100 m strides", segment_hints=[{"reps": 6, "pace_label": "R", "distance_m": 100.0, "recovery": "jog"}]),
        GridCell(WorkoutKind.INTERVAL, miles=10.0, text="VO₂max 10 mi w/ 4 x 1,200 m @ 5K race pace; jog 50 to 90% interval time between", segment_hints=[{"reps": 4, "pace_label": "I", "distance_m": 1200.0, "recovery": "50-90% jog"}]),
        GridCell(WorkoutKind.REST, text="Rest or cross-training"),
        GridCell(WorkoutKind.MEDIUM_LONG, miles=11.0, text="Medium-long run 11 mi"),
        GridCell(WorkoutKind.RECOVERY, miles=4.0, text="Recovery 4 mi"),
        GridCell(WorkoutKind.LONG, miles=20.0, text="Long run 20 mi"),
    ],
    # Week 16 (2 weeks to goal)
    [
        GridCell(WorkoutKind.REST, text="Rest or cross-training"),
        GridCell(WorkoutKind.INTERVAL, miles=8.0, text="VO₂max 8 mi w/ 5 x 600 m @ 5K race pace; jog 50 to 90% interval time between", segment_hints=[{"reps": 5, "pace_label": "I", "distance_m": 600.0, "recovery": "50-90% jog"}]),
        GridCell(WorkoutKind.RECOVERY, miles=6.0, text="Recovery 6 mi"),
        GridCell(WorkoutKind.REST, text="Rest or cross-training"),
        GridCell(WorkoutKind.RECOVERY, miles=4.0, text="Recovery + speed 4 mi w/ 6 x 100 m strides", segment_hints=[{"reps": 6, "pace_label": "R", "distance_m": 100.0, "recovery": "jog"}]),
        GridCell(WorkoutKind.RACE, miles=10.0, text="8K-10K tune-up race (total 9-11 mi)", segment_hints=[{"reps": 1, "pace_label": "R", "distance_m": 10000.0}]),
        GridCell(WorkoutKind.LONG, miles=16.0, text="Long run 16 mi"),
    ],
    # Week 17 (1 week to goal)
    [
        GridCell(WorkoutKind.REST, text="Rest or cross-training"),
        GridCell(WorkoutKind.GENERAL_AEROBIC, miles=7.0, text="General aerobic + speed 7 mi w/ 8 x 100 m strides", segment_hints=[{"reps": 8, "pace_label": "R", "distance_m": 100.0, "recovery": "jog"}]),
        GridCell(WorkoutKind.INTERVAL, miles=8.0, text="VO₂max 8 mi w/ 3 x 1,600 m @ 5K race pace; jog 50 to 90% interval time between", segment_hints=[{"reps": 3, "pace_label": "I", "distance_m": 1600.0, "recovery": "50-90% jog"}]),
        GridCell(WorkoutKind.REST, text="Rest or cross-training"),
        GridCell(WorkoutKind.RECOVERY, miles=5.0, text="Recovery + speed 5 mi w/ 6 x 100 m strides", segment_hints=[{"reps": 6, "pace_label": "R", "distance_m": 100.0, "recovery": "jog"}]),
        GridCell(WorkoutKind.REST, text="Rest or cross-training"),
        GridCell(WorkoutKind.MEDIUM_LONG, miles=12.0, text="Medium-long run 12 mi"),
    ],
    # Week 18 (Race week)
    [
        GridCell(WorkoutKind.REST, text="Rest"),
        GridCell(WorkoutKind.RECOVERY, miles=6.0, text="Recovery 6 mi"),
        GridCell(WorkoutKind.MARATHON_PACE, miles=7.0, text="Dress rehearsal 7 mi w/ 2 mi @ marathon race pace", segment_hints=[{"reps": 1, "pace_label": "M", "distance_m": 3218.688}]),
        GridCell(WorkoutKind.REST, text="Rest"),
        GridCell(WorkoutKind.RECOVERY, miles=5.0, text="Recovery + speed 5 mi w/ 6 x 100 m strides", segment_hints=[{"reps": 6, "pace_label": "R", "distance_m": 100.0, "recovery": "jog"}]),
        GridCell(WorkoutKind.RECOVERY, miles=4.0, text="Recovery 4 mi"),
        GridCell(WorkoutKind.RACE, miles=26.2, text="Goal marathon"),
    ],
]
