# SPDX-License-Identifier: GPL-3.0-or-later
from copy import deepcopy

from gwe.nvml_monitor import NvmlMonitor


def ok(value):
    return {"status": "ok", "value": value}


def snapshot(uuid="GPU-test", index=3):
    return {"driver": ok("580.test"), "gpus": [{
        "index": index, "uuid": ok(uuid), "name": ok("Test GPU"),
        "temperature_c": ok(45), "power_w": ok(80),
        "memory_bytes": ok({"total": 4 * 1024**2, "used": 1024**2}),
        "utilization_percent": ok({"gpu": 20, "memory": 30}),
        "fans": [{"speed_percent": ok(35)}, {"speed_percent": {"status": "error"}}],
    }]}


class Backend:
    def __init__(self):
        self.result = snapshot()
        self.selections = []

    def read_snapshot(self, uuid):
        self.selections.append(uuid)
        return deepcopy(self.result)


def test_adapter_units_missing_rpm_and_disabled_controls():
    status = NvmlMonitor(Backend()).get_status()
    gpu = status.gpu_status_list[0]
    assert status.read_only
    assert gpu.index == 0
    assert gpu.info.memory_total == 4
    assert gpu.info.memory_used == 1
    assert gpu.temp.gpu == 45
    assert gpu.power.draw == 80
    assert gpu.power.limit is None
    assert gpu.fan.fan_list == [(35, None), (None, None)]
    assert not gpu.fan.control_allowed
    assert not gpu.overclock.available


def test_pin_identity_and_clear_old_telemetry_on_device_loss():
    backend = Backend()
    monitor = NvmlMonitor(backend)
    monitor.get_status()
    backend.result = snapshot("GPU-other", 0)
    missing = monitor.get_status().gpu_status_list[0]
    assert missing.temp.gpu is None
    assert missing.info.name is None
    assert missing.fan.fan_list == []
    backend.result = snapshot(index=8)
    assert monitor.get_status().gpu_status_list[0].temp.gpu == 45
    assert backend.selections == [None, "GPU-test", "GPU-test"]


def test_no_devices_produces_empty_read_only_view_model():
    backend = Backend()
    backend.result = {"gpus": []}
    status = NvmlMonitor(backend).get_status()
    assert status.read_only
    assert status.gpu_status_list[0].temp.gpu is None


def test_sensor_error_is_not_zero_or_cached_temperature():
    backend = Backend()
    monitor = NvmlMonitor(backend)
    monitor.get_status()
    backend.result["gpus"][0]["temperature_c"] = {"status": "error"}
    gpu = monitor.get_status().gpu_status_list[0]
    assert gpu.temp.gpu is None
    assert gpu.power.draw == 80
