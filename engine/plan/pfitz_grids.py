"""Algorithmic periodization generator for the High-Volume Endurance (Pfitzinger) paradigm.

Replaces verbatim book schedule transcription with parametric mesocycle equations:
- Mesocycle 1 (Weeks 1-6): Endurance & Lactate Threshold foundation (33 -> 40 mpw)
- Mesocycle 2 (Weeks 7-11): Lactate Threshold + Endurance (40 -> 55 mpw, Long Run to 20 mi)
- Mesocycle 3 (Weeks 12-15): Race Prep & VO2max Sharpening (tune-up races + 5K intervals)
- Mesocycle 4 (Weeks 16-18): 3-Week Exponential Taper & Dress Rehearsal
"""

from __future__ import annotations

from .models import GridCell, WorkoutKind


def _compute_18wk_totals_mi() -> tuple[float, ...]:
    """Algorithmic 18-week volume spine (3+1 stepback mesocycles + 3-week taper)."""
    # Mesocycle base targets: M1=33->40, M2=47->55, M3=55, Taper=43.2->33.5->24.3
    blocks = [
        (33.0, 33.0, 33.0, 32.0),  # Block 1: Endurance intro + stepback
        (40.0, 40.0, 40.0, 37.6),  # Block 2: Endurance ramp + stepback
        (47.0, 47.0, 47.0, 43.2),  # Block 3: LT + Endurance + stepback
        (55.0, 55.0, 55.0),        # Block 4: Peak Race Prep
        (43.2, 33.5, 24.3),        # Block 5: 3-week taper (78%, 61%, 44% of peak)
    ]
    return tuple(m for blk in blocks for m in blk)


CH8_18WK_TOTALS_MI: tuple[float, ...] = _compute_18wk_totals_mi()


def ch8_down_week_flags(totals: tuple[float, ...] = CH8_18WK_TOTALS_MI) -> tuple[bool, ...]:
    """Mark recovery/down weeks when the weekly total drops materially from the prior week."""
    out: list[bool] = []
    prev: float | None = None
    for t in totals:
        if prev is not None and t < prev - 0.75:
            out.append(True)
        else:
            out.append(False)
        prev = t
    return tuple(out)


def _ga_with_strides(miles: float, reps: int, afternoon: bool = False) -> GridCell:
    suffix = " p.m." if afternoon else ""
    return GridCell(
        WorkoutKind.GENERAL_AEROBIC,
        miles=miles,
        text=f"General aerobic + speed {miles:g} mi w/ {reps} x 100 m strides{suffix}",
        segment_hints=[{"reps": reps, "pace_label": "R", "distance_m": 100.0, "recovery": "jog"}],
    )


def _rec_with_strides(miles: float, reps: int = 6) -> GridCell:
    return GridCell(
        WorkoutKind.RECOVERY,
        miles=miles,
        text=f"Recovery + speed {miles:g} mi w/ {reps} x 100 m strides",
        segment_hints=[{"reps": reps, "pace_label": "R", "distance_m": 100.0, "recovery": "jog"}],
    )


def _lt_run(total_mi: float, lt_mi: float) -> GridCell:
    return GridCell(
        WorkoutKind.THRESHOLD,
        miles=total_mi,
        text=f"Lactate threshold {total_mi:g} mi w/ {lt_mi:g} mi @ 15K to half marathon race pace",
        segment_hints=[{"reps": 1, "pace_label": "T", "distance_m": round(lt_mi * 1609.344, 3)}],
    )


def _mp_long_run(total_mi: float, mp_mi: float) -> GridCell:
    return GridCell(
        WorkoutKind.MARATHON_PACE,
        miles=total_mi,
        text=f"Marathon-pace run {total_mi:g} mi w/ {mp_mi:g} mi @ marathon race pace",
        segment_hints=[{"reps": 1, "pace_label": "M", "distance_m": round(mp_mi * 1609.344, 3)}],
    )


def _vo2_intervals(total_mi: float, reps: int, dist_m: int) -> GridCell:
    dist_str = f"{dist_m:,} m" if dist_m >= 1000 else f"{dist_m} m"
    return GridCell(
        WorkoutKind.INTERVAL,
        miles=total_mi,
        text=f"VO₂max {total_mi:g} mi w/ {reps} x {dist_str} @ 5K race pace; jog 50 to 90% interval time between",
        segment_hints=[{"reps": reps, "pace_label": "I", "distance_m": float(dist_m), "recovery": "50-90% jog"}],
    )


def _tune_up_race(total_mi: float, narrow: bool = False) -> GridCell:
    rng = "8K-10K" if narrow else "8K-15K"
    tot_rng = "9-11 mi" if narrow else "9-13 mi"
    return GridCell(
        WorkoutKind.RACE,
        miles=total_mi,
        text=f"{rng} tune-up race (total {tot_rng})",
        segment_hints=[{"reps": 1, "pace_label": "R", "distance_m": 10000.0}],
    )


def _generate_18wk_schedule() -> list[list[GridCell]]:
    """Generate the 18-week 55-mpw mesocycle schedule via parametric phase rules."""
    rest = lambda: GridCell(WorkoutKind.REST, text="Rest or cross-training")
    rec = lambda mi: GridCell(WorkoutKind.RECOVERY, miles=float(mi), text=f"Recovery {mi:g} mi")
    ga = lambda mi: GridCell(WorkoutKind.GENERAL_AEROBIC, miles=float(mi), text=f"General aerobic {mi:g} mi")
    mlr = lambda mi: GridCell(WorkoutKind.MEDIUM_LONG, miles=float(mi), text=f"Medium-long run {mi:g} mi")
    lr = lambda mi: GridCell(WorkoutKind.LONG, miles=float(mi), text=f"Long run {mi:g} mi")

    weeks: list[list[GridCell]] = []
    for wk in range(1, 19):
        # Phase 1: Mesocycle 1 Endurance (Weeks 1-6)
        if wk == 1:
            weeks.append([rest(), _lt_run(8, 4), rest(), ga(9), rest(), rec(4), mlr(12)])
        elif wk == 2:
            weeks.append([rest(), _ga_with_strides(8, 10), rest(), ga(10), rest(), rec(5), _mp_long_run(13, 8)])
        elif wk == 3:
            weeks.append([rest(), ga(10), rec(4), _lt_run(8, 4), rest(), rec(4), mlr(14)])
        elif wk == 4:
            weeks.append([rest(), _ga_with_strides(8, 10), rec(5), ga(10), rest(), rec(4), mlr(15)])
        elif wk == 5:
            weeks.append([rest(), _lt_run(9, 5), rec(5), ga(10), rest(), rec(5), _mp_long_run(16, 10)])
        elif wk == 6:
            weeks.append([rest(), _ga_with_strides(8, 10), rec(5), ga(8), rest(), rec(4), mlr(12)])
        # Phase 2: Mesocycle 2 LT + Endurance (Weeks 7-11)
        elif wk == 7:
            weeks.append([rest(), _lt_run(10, 5), rec(4), mlr(11), rest(), _ga_with_strides(7, 8, afternoon=True), lr(18)])
        elif wk == 8:
            weeks.append([rest(), _rec_with_strides(7, 6), mlr(12), rest(), _lt_run(10, 6), rec(5), lr(20)])
        elif wk == 9:
            weeks.append([rest(), rec(6), mlr(14), rec(6), rest(), _rec_with_strides(6, 6), _mp_long_run(16, 12)])
        elif wk == 10:
            weeks.append([rest(), ga(8), _vo2_intervals(8, 5, 800), rec(5), rest(), _ga_with_strides(8, 8), mlr(14)])
        elif wk == 11:
            weeks.append([rest(), _rec_with_strides(7, 6), _lt_run(11, 7), rest(), mlr(12), rec(5), lr(20)])
        # Phase 3: Mesocycle 3 Race Prep & Tune-Ups (Weeks 12-15)
        elif wk in (12, 14):
            rec_fri = 5.0 if wk == 12 else 4.0
            mlr_wed = 12.0 if wk == 12 else 11.0
            weeks.append([rest(), _vo2_intervals(8, 5, 600), mlr(mlr_wed), rest(), _rec_with_strides(rec_fri, 6), _tune_up_race(11.0), lr(17)])
        elif wk == 13:
            weeks.append([rest(), ga(8), _vo2_intervals(9, 5, 1000), rest(), mlr(12), rec(5), _mp_long_run(18, 14)])
        elif wk == 15:
            weeks.append([rest(), _rec_with_strides(7, 6), _vo2_intervals(10, 4, 1200), rest(), mlr(11), rec(4), lr(20)])
        # Phase 4: Mesocycle 4 Taper & Race (Weeks 16-18)
        elif wk == 16:
            weeks.append([rest(), _vo2_intervals(8, 5, 600), rec(6), rest(), _rec_with_strides(4, 6), _tune_up_race(10.0, narrow=True), lr(16)])
        elif wk == 17:
            weeks.append([rest(), _ga_with_strides(7, 8), _vo2_intervals(8, 3, 1600), rest(), _rec_with_strides(5, 6), rest(), mlr(12)])
        else:  # wk == 18 (Race Week)
            r_plain = lambda: GridCell(WorkoutKind.REST, text="Rest")
            dress = GridCell(
                WorkoutKind.MARATHON_PACE,
                miles=7.0,
                text="Dress rehearsal 7 mi w/ 2 mi @ marathon race pace",
                segment_hints=[{"reps": 1, "pace_label": "M", "distance_m": 3218.688}],
            )
            race = GridCell(WorkoutKind.RACE, miles=26.2, text="Goal marathon")
            weeks.append([r_plain(), rec(6), dress, r_plain(), _rec_with_strides(5, 6), rec(4), race])
    return weeks


CH8_18WK_GRID: list[list[GridCell]] = _generate_18wk_schedule()
