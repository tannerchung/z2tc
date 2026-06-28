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

# Caution palette — for "this plan deviates from the textbook; flag your coach" notes and for
# weeks whose volume exceeds the athlete's demonstrated peak (new, watch-it territory).
CAUTION_FG = (0.6, 0.33, 0.0)             # amber text
CAUTION_HEADER_BG = (0.988, 0.882, 0.71)  # amber band (cautions header)
CAUTION_BODY_BG = (0.996, 0.949, 0.863)   # light amber (cautions body)
OVER_CAPACITY_BG = (0.988, 0.882, 0.71)   # amber Total cell when above demonstrated peak

# Tune-up result indicator — tint the race cell once a result has landed (on-track green / behind red;
# the amber "watch" reuses the caution palette).
ON_TRACK_BG = (0.851, 0.918, 0.827)       # soft green: tune-up result keeps the goal in reach
ON_TRACK_FG = (0.118, 0.451, 0.235)       # green text
BEHIND_BG = (0.957, 0.8, 0.776)           # soft red: tune-up result is behind — re-anchor
BEHIND_FG = (0.659, 0.196, 0.157)         # red text

# Short-week marker — a week the athlete logged under ~92% of prescribed (from Strava). Deliberately
# a cool slate-blue so it never reads as the amber "over capacity" cue: short ≠ too much.
SHORT_WEEK_BG = (0.851, 0.890, 0.949)     # soft slate-blue: this week came in short
SHORT_WEEK_FG = (0.184, 0.310, 0.510)     # slate-blue text

PHASE_TAGLINE: dict[str, str] = {
    "Base": "Build the aerobic engine",
    "Threshold": "Threshold is the engine",
    "Race Prep": "Sharpen with speed",
    "Taper": "Shed fatigue, stay sharp",
}

# Per-method tab color, so a glance at the tab strip tells you which coach plan an athlete is on.
# Green/orange are sampled verbatim from the existing hand-colored tabs (Daniels: Kelly/Cindy;
# Pfitzinger: Rohan/Emily/Michelle). Higdon/Hanson get distinct hues for when they're assigned.
# (Tanner's tab is a bespoke blue — a hand-authored prototype, deliberately outside this mapping.)
METHOD_TAB_RGB: dict[str, tuple[float, float, float]] = {
    "daniels": (0.235, 0.549, 0.416),      # green
    "pfitzinger": (0.816, 0.537, 0.173),   # orange
    "higdon": (0.459, 0.404, 0.706),       # purple
    "hanson": (0.706, 0.314, 0.314),       # muted red
}


def method_tab_color(method: str | None) -> tuple[float, float, float] | None:
    return METHOD_TAB_RGB.get((method or "").strip().lower())


@dataclass(frozen=True)
class PlanSheetTheme:
    font_family: str = "Roboto"          # grid/body: clean, dense-table-friendly, Arial-like metrics
    title_font_family: str = "Montserrat"  # geometric display face for the athlete title only
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
    caution_fg: tuple[float, float, float] = CAUTION_FG
    caution_header_bg: tuple[float, float, float] = CAUTION_HEADER_BG
    caution_body_bg: tuple[float, float, float] = CAUTION_BODY_BG
    over_capacity_bg: tuple[float, float, float] = OVER_CAPACITY_BG
    on_track_bg: tuple[float, float, float] = ON_TRACK_BG
    on_track_fg: tuple[float, float, float] = ON_TRACK_FG
    behind_bg: tuple[float, float, float] = BEHIND_BG
    behind_fg: tuple[float, float, float] = BEHIND_FG
    short_week_bg: tuple[float, float, float] = SHORT_WEEK_BG
    short_week_fg: tuple[float, float, float] = SHORT_WEEK_FG

    @property
    def header_rgb(self) -> tuple[float, float, float]:
        """Back-compat for the legacy flat-grid header formatter."""
        return self.navy


def theme_from_style_spec(spec: StyleSpec) -> PlanSheetTheme:
    """Keep the sampled navy/phase palette and our modern typography (Roboto grid + Montserrat
    title) as the source of truth — the harvested Arial bundle is intentionally overridden."""
    return PlanSheetTheme(
        title_font_size=spec.title_font_size or 15,
    )
