# SPDX-License-Identifier: GPL-3.0-or-later
"""Adapt read-only NVML telemetry to the existing UI models without profile access."""

from gwe.model.clocks import Clocks
from gwe.model.fan import Fan
from gwe.model.gpu_status import GpuStatus
from gwe.model.info import Info
from gwe.model.overclock import Overclock
from gwe.model.power import Power
from gwe.model.status import Status
from gwe.model.temp import Temp


def reading(record, key):
    field = record.get(key, {})
    return field.get("value") if field.get("status") == "ok" else None


class NvmlMonitor:
    """Pin the first discovered GPU for this session; never switch on device loss.

    UI list position remains zero even if the native device index changes. No
    control path may use this view model as a GPU write target.
    """

    def __init__(self, backend):
        self._backend = backend
        self._uuid = None

    def is_available(self):
        return "device_count" in self._backend.read_snapshot()

    def get_status(self):
        snapshot = self._backend.read_snapshot(self._uuid)
        device = {}
        for candidate in snapshot.get("gpus", []):
            uuid = reading(candidate, "uuid")
            if uuid and (self._uuid is None or uuid == self._uuid) and "temperature_c" in candidate:
                self._uuid = uuid
                device = candidate
                break
        memory = reading(device, "memory_bytes") or {}
        utilization = reading(device, "utilization_percent") or {}
        fan_list = [(reading(fan, "speed_percent"), None) for fan in device.get("fans", [])]
        # Missing values remain None, not zero or previous readings. Control
        # capability is deliberately false, even when manual limits are readable.
        info = Info(
            name=reading(device, "name"), uuid=self._uuid,
            driver=reading(snapshot, "driver"),
            memory_total=memory["total"] // (1024 * 1024) if "total" in memory else None,
            memory_used=memory["used"] // (1024 * 1024) if "used" in memory else None,
            memory_usage=utilization.get("memory"), gpu_usage=utilization.get("gpu"),
        )
        return Status([GpuStatus(
            index=0, info=info, power=Power(draw=reading(device, "power_w")),
            temp=Temp(gpu=reading(device, "temperature_c")),
            fan=Fan(fan_list=fan_list, control_allowed=False),
            clocks=Clocks(), overclock=Overclock(available=False),
        )], read_only=True)
