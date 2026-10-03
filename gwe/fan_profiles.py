# SPDX-License-Identifier: GPL-3.0-or-later
"""Read existing fan profiles without importing the application database or migrating it."""
from dataclasses import dataclass
from contextlib import closing
from pathlib import Path
import sqlite3

from gwe.fan_curve import FanCurve


@dataclass(frozen=True)
class SavedFanProfile:
    identifier: int
    name: str
    curve: FanCurve | None
    problem: str | None
    automatic: bool = False


def read_profiles(path, *, allow_automatic=False):
    """Read one coherent snapshot; retain insertion order and reject ambiguous curves."""
    source = Path(path).resolve(strict=True)
    profiles = []
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=2)) as database:
        database.execute('PRAGMA query_only=ON')
        database.execute('BEGIN')
        if database.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
            raise ValueError('Profile database integrity check failed')
        setting = database.execute(
            "SELECT value FROM setting WHERE key='settings_hysteresis'").fetchone()
        hysteresis = 2
        if setting is not None:
            value = setting[0]
            if isinstance(value, bytes):
                value = value.decode('ascii')
            if type(value) is not int and not (isinstance(value, str) and value.isdecimal()):
                raise ValueError('Invalid saved hysteresis')
            hysteresis = int(value)
        if not 0 <= hysteresis <= 20:
            raise ValueError('Invalid saved hysteresis')
        rows = database.execute(
            'SELECT id, name, type, vbios_silent_mode FROM fan_profile ORDER BY id LIMIT 129').fetchall()
        if len(rows) > 128:
            raise ValueError('Too many profiles for the review client')
        for identifier, name, kind, silent in rows:
            curve, problem = None, None
            if not isinstance(name, str) or len(name) > 256:
                raise ValueError('Invalid profile name')
            if kind == 'auto':
                if not allow_automatic:
                    problem = 'Automatic profile: use Restore automatic for this client\'s active trial.'
            else:
                try:
                    if kind != 'fan_curve' or silent not in (0, 1):
                        raise ValueError('Unsupported saved profile type or silent mode')
                    points = database.execute(
                        'SELECT temperature, duty FROM speed_step WHERE profile_id=? ORDER BY id LIMIT 33',
                        (identifier,)).fetchall()
                    if len(points) > 32:
                        raise ValueError('Service supports at most 32 points')
                    curve = FanCurve(points, hysteresis, bool(silent))
                except ValueError as error:
                    problem = str(error)
            profiles.append(SavedFanProfile(identifier, name, curve, problem, kind == 'auto' and allow_automatic))
    return tuple(profiles)


def manual_limits():
    """Read capabilities of the single current-host GPU; no setters or identity output."""
    import pynvml as nvml
    nvml.nvmlInit()
    try:
        if nvml.nvmlDeviceGetCount() != 1:
            raise ValueError('Review client requires exactly one GPU')
        handle = nvml.nvmlDeviceGetHandleByIndex(0)
        if nvml.nvmlDeviceGetName(handle) != 'NVIDIA GeForce RTX 3090 Ti':
            raise ValueError('Review client requires the validated GPU model')
        if nvml.nvmlDeviceGetNumFans(handle) != 2:
            raise ValueError('Review client requires two fans')
        limits = tuple(nvml.nvmlDeviceGetMinMaxFanSpeed(handle))
        FanCurve(((0, limits[0]),)).validate_limits(*limits)
        return limits
    finally:
        nvml.nvmlShutdown()
