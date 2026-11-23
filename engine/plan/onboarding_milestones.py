"""Just-in-time progressive onboarding prompts so runners are never bombarded on Day 1.

Priority order (at most ONE informal prompt per week):
1. Weeks 1..2 (if long run < 13 mi): None - focus 100% on hitting prescribed paces & routine.
2. First week where Saturday long run >= 12.0 mi (or >= 90 min) and ``enable_fueling_guidance`` is False:
   Ask informal gel/chew preference -> unlocks ``enable_fueling_guidance``.
3. Warm forecast (temp >= 65F) OR entering Peak build (wtg <= 8) when ``enable_hydration_weather`` is False:
   Ask informal salty-sweater check -> unlocks ``enable_hydration_weather``.
4. Dress-rehearsal week (wtg == 4) or Race Week (wtg == 1):
   Offer informal 48h carb-load target (~8g/kg) without daily macro app logging.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import AthleteInputs, TrainingPlan


@dataclass(frozen=True)
class OnboardingMilestonePrompt:
    module_key: str
    trigger_reason: str
    informal_question: str


def next_onboarding_prompt(
    plan: TrainingPlan,
    inputs: AthleteInputs,
    *,
    week_index: int,
) -> OnboardingMilestonePrompt | None:
    """Return at most one informal onboarding prompt appropriate for ``week_index``, or None."""
    by_idx = {w.index: w for w in plan.weeks}
    wk = by_idx.get(week_index)
    if wk is None:
        return None

    wtg = max(0, plan.block_weeks - week_index)
    lr_miles = wk.long_run.miles if wk.long_run else 0.0

    # Gate 1: Never prompt in Week 1 unless their very first long run is already >= 13 mi
    if week_index == 1 and lr_miles < 13.0:
        return None

    # Milestone 1: Long run reaches >= 12.0 mi -> Informal Fueling Check
    if not inputs.enable_fueling_guidance and lr_miles >= 12.0:
        return OnboardingMilestonePrompt(
            module_key="enable_fueling_guidance",
            trigger_reason=f"Week {week_index} long run reaches {lr_miles:g} mi",
            informal_question=(
                f"Your Saturday run steps up to {lr_miles:g} mi this week! Want me to include informal "
                "gel/water timing tips on your long runs? If so, what gel, chew, or drink do you usually like?"
            ),
        )

    # Milestone 2: Warm weather or Peak build (wtg <= 8) -> Informal Sweat/Salt Check
    warm = (inputs.ambient_temp_f is not None and inputs.ambient_temp_f >= 65.0)
    if inputs.enable_fueling_guidance and not inputs.enable_hydration_weather and (warm or wtg <= 8):
        return OnboardingMilestonePrompt(
            module_key="enable_hydration_weather",
            trigger_reason="Entering peak long-run block / warm conditions",
            informal_question=(
                "Quick hydration check as the long runs get bigger: do you usually notice white salt "
                "stains on your hat/shorts or get calf twitches on warm runs, or pretty normal sweat?"
            ),
        )

    # Milestone 3: Dress Rehearsal (wtg == 4) or Race Week (wtg == 1) -> Informal Carb-Load Offer
    if wtg in (4, 1):
        label = "dress-rehearsal long run" if wtg == 4 else "marathon Sunday"
        return OnboardingMilestonePrompt(
            module_key="informal_carb_load",
            trigger_reason=f"wtg={wtg} ({label})",
            informal_question=(
                f"Big {label} this weekend - want a super simple 2-day carb-load target (bagels/rice/drink mix, "
                "no calorie-counting app required) so your legs have a full tank?"
            ),
        )

    return None
