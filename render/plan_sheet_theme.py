"""Deterministic Google Sheets theme for athlete plan tabs.

Palette and shape are extracted verbatim from the hand-styled club ``Cindy`` tab
(see ``docs/design/plan-sheet-layout.md``). RGB are 0-1 fractions as Sheets returns them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from llm.boundary import StyleSpec

# --- Brand palette (sampled from the club workbook) ------------------------------
NAVY = (0.122, 0.227, 0.373)         # brand: title, headers, long-run + pace labels
GRAY_TEXT = (0.502, 0.502, 0.502)    # secondary text: subtitle, "Why", recovery rows
DARK_TEXT = (0.149, 0.149, 0.149)    # body text
WHITE = (1.0, 1.0, 1.0)

# Phase band fills (one per Daniels phase) + race day
PHASE_RGB: dict[str, tuple[float, float, float]] = {
    "Base": (0.863, 0.902, 0.949),        # light blue
    "Threshold": (0.839, 0.918, 0.875),   # light green
    "Race Prep": (0.984, 0.906, 0.804),   # light tan
    "Taper": (0.906, 0.882, 0.945),       # light purple
}
RACE_DAY_BAND_RGB = NAVY
RACE_DAY_ROW_RGB = (0.988, 0.894, 0.839)  # peach
RACE_DAY_FG = (0.545, 0.18, 0.0)          # dark orange

RECOVERY_RGB = (0.961, 0.961, 0.961)      # down-week row shade
PACE_SECTION_RGB = (0.933, 0.945, 0.961)  # paces block header
PACE_LABEL_RGB = (0.961, 0.969, 0.98)     # pace label cells

PHASE_TAGLINE: dict[str, str] = {
    "Base": "Build the aerobic engine",
    "Threshold": "Threshold is the engine",
    "Race Prep": "Sharpen with speed",
    "Taper": "Shed fatigue, stay sharp",
}


@dataclass(frozen=True)
class PlanSheetTheme:
    font_family: str = "Arial"
    title_font_size: int = 15
    subtitle_font_size: int = 9
    body_font_size: int = 10
    header_font_size: int = 9
    pace_value_font_size: int = 11
    navy: tuple[float, float, float] = NAVY
    gray_text: tuple[float, float, float] = GRAY_TEXT
    dark_text: tuple[float, float, float] = DARK_TEXT
    phase_rgb: dict[str, tuple[float, float, float]] = field(default_factory=lambda: dict(PHASE_RGB))
    recovery_rgb: tuple[float, float, float] = RECOVERY_RGB
    pace_section_rgb: tuple[float, float, float] = PACE_SECTION_RGB
    pace_label_rgb: tuple[float, float, float] = PACE_LABEL_RGB
    race_day_band_rgb: tuple[float, float, float] = RACE_DAY_BAND_RGB
    race_day_row_rgb: tuple[float, float, float] = RACE_DAY_ROW_RGB
    race_day_fg: tuple[float, float, float] = RACE_DAY_FG

    @property
    def header_rgb(self) -> tuple[float, float, float]:
        """Back-compat for the legacy flat-grid header formatter."""
        return self.navy


def theme_from_style_spec(spec: StyleSpec) -> PlanSheetTheme:
    """Use harvested font; keep the sampled navy/phase palette as the source of truth."""
    return PlanSheetTheme(
        font_family=spec.title_font_family or "Arial",
        title_font_size=spec.title_font_size or 15,
    )
