# SPDX-License-Identifier: GPL-3.0-or-later
"""Design tokens for StormFuse's dark interface."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ThemeTokens:
    """Color and typography tokens for the application theme."""

    CANVAS: str
    SURFACE: str
    SURFACE_RAISED: str
    SURFACE_INSET: str
    BORDER: str
    ACCENT: str
    SUCCESS: str
    WARNING: str
    DANGER: str
    TEXT: str
    TEXT_MUTED: str
    TEXT_SECONDARY: str
    FONT_HEADING: tuple[int, int]
    FONT_BODY_STRONG: tuple[int, int]
    FONT_BODY: tuple[int, int]
    FONT_MONO: tuple[int, int]


DARK = ThemeTokens(
    CANVAS="#0A0D13",
    SURFACE="#12161F",
    SURFACE_RAISED="#1B212D",
    SURFACE_INSET="#0D1119",
    BORDER="#262D3B",
    ACCENT="#5B84C4",
    SUCCESS="#5C7CFA",
    WARNING="#F5A623",
    DANGER="#F87171",
    TEXT="#FFFFFF",
    TEXT_MUTED="#8E96AA",
    TEXT_SECONDARY="#C9D0E3",
    FONT_HEADING=(18, 700),
    FONT_BODY_STRONG=(10, 600),
    FONT_BODY=(10, 400),
    FONT_MONO=(9, 400),
)


def darken(hex_color: str, factor: float) -> str:
    """Scale ``hex_color`` toward black by ``factor`` (e.g. 0.85 = 15% darker)."""
    hex_color = hex_color.lstrip("#")
    red, green, blue = (int(hex_color[index : index + 2], 16) for index in (0, 2, 4))
    red, green, blue = (max(0, min(255, round(channel * factor))) for channel in (red, green, blue))
    return f"#{red:02X}{green:02X}{blue:02X}"


def with_alpha(hex_color: str, alpha: float) -> str:
    """Return ``hex_color`` as a QSS ``rgba(...)`` string with the given opacity."""
    hex_color = hex_color.lstrip("#")
    red, green, blue = (int(hex_color[index : index + 2], 16) for index in (0, 2, 4))
    return f"rgba({red}, {green}, {blue}, {alpha})"
