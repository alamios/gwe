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


def test_extended_telemetry_maps_and_clears_without_enabling_writes():
    backend = Backend()
    device = backend.result['gpus'][0]
    device.update(power_limit_w=ok(250), power_default_w=ok(450), power_enforced_w=ok(250),
                  power_constraints_w=ok({'minimum': 100, 'maximum': 480}),
                  clocks_mhz={'graphic_current': ok(0), 'memory_max': ok(10500)})
    device['fans'][0]['speed_rpm'] = ok(0)
    device['fans'][1]['speed_rpm'] = ok(1200)
    monitor = NvmlMonitor(backend)
    status = monitor.get_status()
    gpu = status.gpu_status_list[0]
    assert vars(gpu.power) == dict(draw=80, limit=250, default=450, minimum=100, enforced=250, maximum=480)
    assert gpu.clocks.graphic_current == 0
    assert gpu.clocks.memory_max == 10500
    assert gpu.clocks.sm_current is None
    assert gpu.fan.fan_list == [(35, 0), (None, 1200)]
    assert status.read_only and not gpu.fan.control_allowed and not gpu.overclock.available
    backend.result = snapshot()
    cleared = monitor.get_status().gpu_status_list[0]
    assert cleared.power.limit is None and cleared.clocks.memory_max is None
    assert cleared.fan.fan_list[0][1] is None
