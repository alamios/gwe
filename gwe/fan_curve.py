# SPDX-License-Identifier: GPL-3.0-or-later
"""Validated fan curves without GTK, database access or hardware operations."""

from dataclasses import dataclass
import math


def finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


@dataclass(frozen=True)
class FanCurve:
    """Explicit ordered points; no sorting, clamping or migration of saved profiles."""

    points: tuple
    hysteresis: float = 2
    vbios_silent: bool = False

    def __post_init__(self):
        points = tuple(tuple(point) for point in self.points)
        if not points:
            raise ValueError("A curve requires at least one point")
        previous = None
        for point in points:
            if len(point) != 2:
                raise ValueError("Each curve point requires temperature and duty")
            temperature, duty = point
            if not finite_number(temperature) or not 0 <= temperature <= 150:
                raise ValueError("Invalid curve temperature")
            if not finite_number(duty) or not 0 <= duty <= 100:
                raise ValueError("Invalid curve duty")
            if previous and (temperature <= previous[0] or duty < previous[1]):
                raise ValueError("Temperatures must increase and duties must not decrease")
            previous = point
        if not finite_number(self.hysteresis) or not 0 <= self.hysteresis <= 20:
            raise ValueError("Invalid hysteresis")
        if type(self.vbios_silent) is not bool:
            raise ValueError("Silent mode must be boolean")
        object.__setattr__(self, "points", points)

    def validate_limits(self, minimum, maximum):
        if not all(finite_number(v) for v in (minimum, maximum)) or not 0 <= minimum <= maximum <= 100:
            raise ValueError("Invalid manual fan limits")
        if any(not minimum <= duty <= maximum for _, duty in self.points):
            raise ValueError("Curve exceeds reported manual limits; explicit review required")

    def target(self, temperature):
        if not finite_number(temperature) or not 0 <= temperature <= 150:
            raise ValueError("Invalid GPU temperature")
        if self.vbios_silent and temperature < self.points[0][0]:
            return None  # Firmware automatic control, never a manual zero-percent write.
        if temperature <= self.points[0][0]:
            return round(self.points[0][1])
        for (t0, d0), (t1, d1) in zip(self.points, self.points[1:]):
            if temperature < t1:
                return round(d0 + (d1 - d0) * (temperature - t0) / (t1 - t0))
        return round(self.points[-1][1])

    def demand(self, temperature, applied_duty, applied_temperature):
        duty = self.target(temperature)
        # Firmware-silent mode has precedence, matching the historical presenter.
        if duty is None or applied_duty is None:
            return duty
        if duty == applied_duty:
            return applied_duty
        if applied_temperature is not None and self.hysteresis:
            if -self.hysteresis <= temperature - applied_temperature <= 0:
                return applied_duty
        return duty
