# SPDX-License-Identifier: GPL-3.0-or-later
"""Fixed conservative acceptance trial guard, separate from normal power choices."""
from gwe.nvml_power import PowerError, PowerRecord, _handle, _limits


class TrialRecord(PowerRecord):
    def __init__(self, directory):
        super().__init__(directory)
        self.pending = self.directory / 'power-trial.json'
        self.last = self.directory / 'power-trial-last.json'


def prepare(nvml, directory, uuid):
    """Read-only baseline plus private guard; no hardware setter is called."""
    record = TrialRecord(directory)
    if record.pending.exists() or PowerRecord(directory).pending.exists():
        raise PowerError('recovery_pending')
    nvml.nvmlInit()
    try:
        handle = _handle(nvml, uuid)
        name = nvml.nvmlDeviceGetName(handle)
        if isinstance(name, bytes):
            name = name.decode('ascii')
        if '3090 Ti' not in name or nvml.nvmlDeviceGetNumFans(handle) != 2:
            raise PowerError('trial_baseline_mismatch')
        if any(nvml.nvmlDeviceGetFanControlPolicy_v2(handle, fan) != 0 for fan in range(2)):
            raise PowerError('trial_baseline_mismatch')
        low, high = _limits(nvml, handle)
        if (nvml.nvmlDeviceGetPowerManagementLimit(handle) != 250000
                or not low <= 240000 < 250000 <= high
                or nvml.nvmlDeviceGetTemperature(handle, nvml.NVML_TEMPERATURE_GPU) >= 65):
            raise PowerError('trial_baseline_mismatch')
        record.begin(uuid, 250000, 240000)
    finally:
        nvml.nvmlShutdown()
