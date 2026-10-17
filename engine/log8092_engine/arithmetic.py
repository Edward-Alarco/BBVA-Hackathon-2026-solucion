"""Aritmetica normativa de enteros; ningun KPI depende de ``float``."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


def ceil_div(numerator: int, denominator: int) -> int:
    if numerator < 0 or denominator <= 0:
        raise ValueError("ceil_div requiere numerador no negativo y divisor positivo")
    return (numerator + denominator - 1) // denominator


def round_half_up_ratio(numerator: int, denominator: int) -> int:
    """GEN-007: floor((2a+b)/(2b)) para a>=0 y b>0."""
    if numerator < 0 or denominator <= 0:
        raise ValueError("round_half_up_ratio requiere valores no negativos")
    return (2 * numerator + denominator) // (2 * denominator)


def decimal_ratio(
    numerator: int, denominator: int, places: int
) -> float | None:
    if denominator == 0:
        return None
    quantum = Decimal(1).scaleb(-places)
    value = (Decimal(numerator) / Decimal(denominator)).quantize(
        quantum, rounding=ROUND_HALF_UP
    )
    return float(value)


def clamp(value: int, low: int = 0, high: int = 10_000) -> int:
    return min(high, max(low, value))
