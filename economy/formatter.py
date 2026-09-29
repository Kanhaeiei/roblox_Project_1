"""Large-number formatting for display, strictly separated from stored integers.

Stored currency and power values are always exact integers up to safeIntegerCeiling.
This module formats them for UI presentation without mutating stored values.
"""

from __future__ import annotations

import math
from typing import Union

Number = Union[int, float]

SUFFIXES = [
    (10**15, "Q"),  # Quadrillion
    (10**12, "T"),  # Trillion
    (10**9, "B"),   # Billion
    (10**6, "M"),   # Million
    (10**3, "K"),   # Thousand
]


def format_compact(value: Number, decimals: int = 2) -> str:
    """Format a number into a compact string with suffix (e.g. 1500 -> '1.50K').

    Integers below 1000 are formatted as standard integers with commas.
    Negative numbers are supported.
    """
    if not math.isfinite(value):
        raise ValueError(f"Cannot format non-finite number: {value}")

    sign = "-" if value < 0 else ""
    abs_val = abs(value)

    if abs_val < 1000:
        if isinstance(value, int) or abs_val.is_integer():
            return f"{sign}{int(abs_val)}"
        return f"{sign}{abs_val:.{decimals}f}".rstrip("0").rstrip(".")

    for threshold, suffix in SUFFIXES:
        if abs_val >= threshold:
            scaled = abs_val / threshold
            formatted = f"{scaled:.{decimals}f}"
            return f"{sign}{formatted}{suffix}"

    return f"{sign}{int(abs_val)}"


def format_delimiter(value: int) -> str:
    """Format an integer with commas (e.g. 1234567 -> '1,234,567')."""
    return f"{value:,}"
