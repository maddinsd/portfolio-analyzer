"""Shared utility functions — import from here, never recompute independently."""
from __future__ import annotations


def get_conviction(bull_ratio: float | None, beat_streak: int | None) -> str:
    """
    Compute investment conviction level from analyst bull ratio and earnings beat streak.
    bull_ratio: percentage (0-100), e.g. 75.0 means 75% of analysts rate Buy.
    beat_streak: number of consecutive EPS beats.
    Returns "High", "Medium", or "Low".
    """
    br = (bull_ratio or 0) / 100.0  # normalize to 0-1 fraction
    bs = beat_streak or 0
    if br > 0.80 and bs >= 6:
        return "High"
    elif br > 0.60:
        return "Medium"
    return "Low"
