# SPDX-License-Identifier: GPL-3.0-or-later
"""One-shot UUID-bound power transactions; no fan, clock or profile operations."""
import json
import os
from pathlib import Path
import stat


class PowerError(RuntimeError):
    """Allowlisted diagnostic code, never a raw driver message."""


def milliwatts(value):
    if type(value) is not int or not 1 <= value <= 0xffffffff:
        raise PowerError('invalid_power')
    return value


class PowerRecord:
    """Private journal before a setter; committed values survive normal shutdown.

    Production directory is root-owned, trusted and preserved by systemd. Files
    are bounded, no-follow, single-link and owned by this effective UID.
    """
    def __init__(self, directory):
        self.directory = Path(directory)
        self.pending = self.directory / 'power-pending.json'
        self.last = self.directory / 'power-last.json'

    def _sync(self):
        fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def write(self, path, row, *, exclusive=False):
        target = path if exclusive else path.with_suffix('.tmp')
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as output:
            json.dump(row, output, allow_nan=False)
            output.flush()
            os.fsync(output.fileno())
        if not exclusive:
            os.replace(target, path)
        self._sync()

    def read(self, path):
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd) as source:
            info = os.fstat(source.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 4096):
                raise PowerError('invalid_record')
            row = json.load(source)
        if (not isinstance(row, dict) or set(row) != {'version', 'gpu_uuid', 'previous_mw', 'requested_mw', 'outcome'}
                or type(row['version']) is not int or row['version'] != 1
                or not isinstance(row['gpu_uuid'], str) or not row['gpu_uuid'].startswith('GPU-')
                or row['outcome'] not in ('pending', 'applied', 'rolled_back')):
            raise PowerError('invalid_record')
        milliwatts(row['previous_mw'])
        milliwatts(row['requested_mw'])
        return row

    def begin(self, uuid, previous, requested):
        row = dict(version=1, gpu_uuid=uuid, previous_mw=previous,
                   requested_mw=requested, outcome='pending')
        self.write(self.pending, row, exclusive=True)
        return row

    def finish(self, row, outcome):
        # A crash before clearing pending means uncommitted: recover previous.
        # Discard only our fixed temporary audit file after interrupted writes.
        self.last.with_suffix('.tmp').unlink(missing_ok=True)
        self.write(self.last, {**row, 'outcome': outcome})
        self.pending.unlink()
        self._sync()


def _handle(nvml, uuid):
    handle = nvml.nvmlDeviceGetHandleByUUID(uuid)
    actual = nvml.nvmlDeviceGetUUID(handle)
    if isinstance(actual, bytes):
        actual = actual.decode('ascii')
    if actual != uuid:
        raise PowerError('identity_mismatch')
    return handle


def _limits(nvml, handle):
    low, high = nvml.nvmlDeviceGetPowerManagementLimitConstraints(handle)
    milliwatts(low)
    milliwatts(high)
    if low > high:
        raise PowerError('invalid_limits')
    return low, high


def recover(nvml, record, uuid):
    """Recover only an interrupted transaction, never a committed power choice."""
    if not record.pending.exists():
        return {'state': 'idle'}
    row = record.read(record.pending)
    if row['gpu_uuid'] != uuid or row['outcome'] != 'pending':
        raise PowerError('invalid_record')
    nvml.nvmlInit()
    try:
        handle = _handle(nvml, uuid)
        low, high = _limits(nvml, handle)
        previous = row['previous_mw']
        if not low <= previous <= high:
            raise PowerError('recovery_failed')
        current = nvml.nvmlDeviceGetPowerManagementLimit(handle)
        if current not in (previous, row['requested_mw']):
            raise PowerError('external_power_change')
        if current != previous:
            nvml.nvmlDeviceSetPowerManagementLimit(handle, previous)
        if nvml.nvmlDeviceGetPowerManagementLimit(handle) != previous:
            raise PowerError('recovery_failed')
        record.finish(row, 'rolled_back')
        return {'state': 'rolled_back', 'previous_mw': previous, 'applied_mw': previous}
    finally:
        nvml.nvmlShutdown()


def apply(nvml, record, uuid, requested, expected):
    milliwatts(requested)
    milliwatts(expected)
    if record.pending.exists():
        raise PowerError('recovery_pending')
    nvml.nvmlInit()
    try:
        handle = _handle(nvml, uuid)
        low, high = _limits(nvml, handle)
        previous = milliwatts(nvml.nvmlDeviceGetPowerManagementLimit(handle))
        if previous != expected:
            raise PowerError('stale_power')
        if not low <= requested <= high or not low <= previous <= high:
            raise PowerError('outside_limits')
        if requested == previous:
            return {'state': 'applied', 'previous_mw': previous, 'applied_mw': previous}
        row = record.begin(uuid, previous, requested)
        # Recheck after journal I/O. No other power controller should be active.
        if nvml.nvmlDeviceGetPowerManagementLimit(handle) != previous:
            raise PowerError('stale_power')
        nvml.nvmlDeviceSetPowerManagementLimit(handle, requested)
        if nvml.nvmlDeviceGetPowerManagementLimit(handle) != requested:
            raise PowerError('verification_failed')
        record.finish(row, 'applied')
        return {'state': 'applied', 'previous_mw': previous, 'applied_mw': requested}
    finally:
        nvml.nvmlShutdown()
