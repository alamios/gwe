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

    def close(self):
        self._backend.close()

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
        fan_list = [(reading(fan, "speed_percent"), reading(fan, "speed_rpm"))
                    for fan in device.get("fans", [])]
        constraints = reading(device, "power_constraints_w") or {}
        clocks = device.get("clocks_mhz", {})
        thresholds = device.get("temperature_thresholds_c", {})
        # Missing values remain None, not zero or previous readings. Control
        # capability is deliberately false, even when manual limits are readable.
        info = Info(
            name=reading(device, "name"), uuid=self._uuid,
            vbios=reading(device, "vbios"), cuda_cores=reading(device, "cuda_cores"),
            memory_interface=reading(device, "memory_bus_width_bits"),
            pcie_current_generation=reading(device, "pcie_current_generation"),
            pcie_max_generation=reading(device, "pcie_max_generation"),
            pcie_current_link=reading(device, "pcie_current_link"),
            pcie_max_link=reading(device, "pcie_max_link"),
            encoder_usage=(reading(device, "encoder_utilization") or {}).get("percent"),
            decoder_usage=(reading(device, "decoder_utilization") or {}).get("percent"),
            driver=reading(snapshot, "driver"),
            memory_total=memory["total"] // (1024 * 1024) if "total" in memory else None,
            memory_used=memory["used"] // (1024 * 1024) if "used" in memory else None,
            memory_usage=utilization.get("memory"), gpu_usage=utilization.get("gpu"),
        )
        return Status([GpuStatus(
            index=0, info=info, power=Power(
                draw=reading(device, "power_w"), limit=reading(device, "power_limit_w"),
                default=reading(device, "power_default_w"), enforced=reading(device, "power_enforced_w"),
                minimum=constraints.get("minimum"), maximum=constraints.get("maximum")),
            temp=Temp(gpu=reading(device, "temperature_c"), maximum=reading(thresholds, "maximum"),
                      slowdown=reading(thresholds, "slowdown"), shutdown=reading(thresholds, "shutdown")),
            fan=Fan(fan_list=fan_list, control_allowed=False),
            clocks=Clocks(**{f"{domain}_{kind}": reading(clocks, f"{domain}_{kind}")
                             for domain in ("graphic", "sm", "memory", "video")
                             for kind in ("current", "max")}), overclock=Overclock(available=False),
        )], read_only=True)
