"""Relojes SLA continuo y habil definidos por intervalos semiabiertos."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Mapping


SECONDS_PER_DAY = 86_400


def _parse_clock(value: str) -> tuple[int, int]:
    if value == "24:00":
        return (24, 0)
    hour, minute = (int(part) for part in value.split(":"))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Hora invalida: {value}")
    return hour, minute


@dataclass(frozen=True, slots=True)
class SlaRule:
    product: str
    duration_seconds: int
    clock: str
    weekdays: frozenset[int]
    open_hour: int
    open_minute: int
    close_hour: int
    close_minute: int

    @classmethod
    def from_mapping(cls, product: str, raw: Mapping[str, object]) -> "SlaRule":
        open_hour, open_minute = _parse_clock(str(raw["open"]))
        close_hour, close_minute = _parse_clock(str(raw["close"]))
        return cls(
            product=product,
            duration_seconds=int(raw["duration_minutes"]) * 60,
            clock=str(raw["clock"]),
            weekdays=frozenset(int(day) for day in raw["days"]),
            open_hour=open_hour,
            open_minute=open_minute,
            close_hour=close_hour,
            close_minute=close_minute,
        )


class BusinessCalendar:
    def __init__(self, holidays: frozenset[date], sla: Mapping[str, SlaRule]) -> None:
        self.holidays = holidays
        self.sla = dict(sla)

    def _window(self, day: date, rule: SlaRule, tzinfo: object) -> tuple[datetime, datetime] | None:
        if day.isoweekday() not in rule.weekdays or day in self.holidays:
            return None
        opening = datetime.combine(
            day, time(rule.open_hour, rule.open_minute), tzinfo=tzinfo
        )
        if rule.close_hour == 24:
            closing = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tzinfo)
        else:
            closing = datetime.combine(
                day, time(rule.close_hour, rule.close_minute), tzinfo=tzinfo
            )
        if closing <= opening:
            raise ValueError(f"Ventana SLA invalida para {rule.product}")
        return opening, closing

    def deadline(self, available_at: datetime, product: str) -> datetime:
        rule = self.sla[product]
        if rule.clock == "CONTINUOUS":
            return available_at + timedelta(seconds=rule.duration_seconds)

        remaining = rule.duration_seconds
        cursor = available_at
        while True:
            window = self._window(cursor.date(), rule, cursor.tzinfo)
            if window is not None:
                opening, closing = window
                start = max(cursor, opening)
                if start < closing:
                    usable = int((closing - start).total_seconds())
                    if remaining <= usable:
                        return start + timedelta(seconds=remaining)
                    remaining -= usable
            cursor = datetime.combine(
                cursor.date() + timedelta(days=1), time.min, tzinfo=cursor.tzinfo
            )

    def elapsed_seconds(self, start: datetime, end: datetime, product: str) -> int:
        if end <= start:
            return 0
        rule = self.sla[product]
        if rule.clock == "CONTINUOUS":
            return int((end - start).total_seconds())

        total = 0
        day = start.date()
        last_day = end.date()
        while day <= last_day:
            window = self._window(day, rule, start.tzinfo)
            if window is not None:
                opening, closing = window
                left = max(start, opening)
                right = min(end, closing)
                if right > left:
                    total += int((right - left).total_seconds())
            day += timedelta(days=1)
        return total

    def ratio_parts(self, start: datetime, end: datetime, product: str) -> tuple[int, int]:
        rule = self.sla[product]
        return self.elapsed_seconds(start, end, product), rule.duration_seconds
