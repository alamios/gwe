# SPDX-License-Identifier: GPL-3.0-or-later
"""Backend tests use simulated devices exclusively."""

from types import SimpleNamespace

import pynvml
import pytest

from gwe.nvml_backend import NvmlBackend
from test_nvml_probe import binding, fail  # Reuse the strict read-only test fixture.


@pytest.fixture
def identified(binding):
    binding.nvmlDeviceGetUUID = lambda handle: b"GPU-test"
    binding.nvmlDeviceGetHandleByUUID = lambda uuid: object()
    binding.nvmlDeviceGetIndex = lambda handle: 3
    binding.nvmlDeviceGetMemoryInfo = lambda handle: SimpleNamespace(total=100, used=40, free=60)
    binding.nvmlDeviceGetUtilizationRates = lambda handle: SimpleNamespace(gpu=15, memory=20)
    binding.nvmlDeviceGetPowerUsage = lambda handle: 123456
    return binding


def test_identity_units_and_timestamps(identified):
    result = NvmlBackend(identified).read_snapshot()
    gpu = result["gpus"][0]
    assert gpu["uuid"]["value"] == "GPU-test"
    assert gpu["memory_bytes"]["value"] == {"total": 100, "used": 40, "free": 60}
    assert gpu["utilization_percent"]["value"] == {"gpu": 15, "memory": 20}
    assert gpu["power_w"]["value"] == 123.456
    assert result["started_monotonic_s"] <= result["finished_monotonic_s"]


def test_selection_survives_changed_index(identified):
    selected = []
    def by_uuid(uuid):
        selected.append(uuid)
        return object()
    identified.nvmlDeviceGetHandleByUUID = by_uuid
    backend = NvmlBackend(identified)
    assert backend.read_snapshot("GPU-test")["gpus"][0]["index"] == 3
    identified.nvmlDeviceGetIndex = lambda handle: 7
    assert backend.read_snapshot("GPU-test")["gpus"][0]["index"] == 7
    assert selected == ["GPU-test", "GPU-test"]
    assert "nvmlDeviceGetHandleByIndex" not in identified.calls


def test_missing_selected_gpu_never_falls_back(identified):
    identified.nvmlDeviceGetHandleByUUID = fail(pynvml.NVML_ERROR_NOT_FOUND)
    result = NvmlBackend(identified).read_snapshot("GPU-missing")
    assert result["status"] == "error"
    assert "name" not in result["gpus"][0]
    assert "nvmlDeviceGetHandleByIndex" not in identified.calls


def test_identity_mismatch_stops_telemetry(identified):
    result = NvmlBackend(identified).read_snapshot("GPU-other")
    assert result["status"] == "error"
    assert "temperature_c" not in result["gpus"][0]


def test_unsupported_identity_does_not_use_index_as_identity(identified):
    identified.nvmlDeviceGetUUID = fail(pynvml.NVML_ERROR_NOT_SUPPORTED)
    result = NvmlBackend(identified).read_snapshot()
    assert result["status"] == "error"
    assert result["gpus"][0]["uuid"]["status"] == "unsupported"


def test_transient_failure_does_not_reuse_old_reading(identified):
    backend = NvmlBackend(identified)
    first = backend.read_snapshot()
    identified.nvmlDeviceGetTemperature = fail(pynvml.NVML_ERROR_GPU_IS_LOST)
    second = backend.read_snapshot()
    assert first["gpus"][0]["temperature_c"]["value"] == 45
    assert second["status"] == "error"
    assert "value" not in second["gpus"][0]["temperature_c"]
    identified.nvmlDeviceGetTemperature = lambda handle, sensor: 50
    third = backend.read_snapshot()
    assert third["status"] == "ok"
    assert third["gpus"][0]["temperature_c"]["value"] == 50
    assert identified.calls.count("nvmlInit") == 3
    assert identified.calls.count("nvmlShutdown") == 3
    assert identified.calls.count("nvmlDeviceGetHandleByIndex") == 3


@pytest.mark.parametrize("uuid", ["", " ", 0, b"GPU-test"])
def test_invalid_selection_never_initializes(identified, uuid):
    with pytest.raises(ValueError):
        NvmlBackend(identified).read_snapshot(uuid)
    assert identified.calls == []


def test_power_units_and_independent_clock_queries(identified):
    identified.nvmlDeviceGetPowerManagementLimit = lambda h: 250000
    identified.nvmlDeviceGetPowerManagementDefaultLimit = lambda h: 450000
    identified.nvmlDeviceGetEnforcedPowerLimit = lambda h: 249500
    identified.nvmlDeviceGetPowerManagementLimitConstraints = lambda h: [100000, 480000]
    for index, domain in enumerate(('GRAPHICS', 'SM', 'MEM', 'VIDEO')):
        setattr(identified, f'NVML_CLOCK_{domain}', index)
    def clock(handle, domain):
        if domain == 1:
            raise pynvml.NVMLError(pynvml.NVML_ERROR_NOT_SUPPORTED)
        return domain * 100
    identified.nvmlDeviceGetClockInfo = clock
    identified.nvmlDeviceGetMaxClockInfo = lambda h, domain: 2000 + domain
    result = NvmlBackend(identified).read_snapshot()
    gpu = result['gpus'][0]
    assert result['status'] == 'ok'
    assert [gpu[f'power_{field}_w']['value'] for field in ('limit', 'default', 'enforced')] == [250, 450, 249.5]
    assert gpu['power_constraints_w']['value'] == {'minimum': 100, 'maximum': 480}
    assert gpu['clocks_mhz']['graphic_current']['value'] == 0
    assert gpu['clocks_mhz']['sm_current']['status'] == 'unsupported'
    assert gpu['clocks_mhz']['sm_max']['value'] == 2001
    assert gpu['clocks_mhz']['memory_current']['value'] == 200
    assert gpu['clocks_mhz']['video_current']['value'] == 300


def test_missing_extended_binding_is_optional(identified):
    gpu = NvmlBackend(identified).read_snapshot()['gpus'][0]
    assert gpu['power_limit_w']['status'] == 'unavailable'
    assert gpu['clocks_mhz']['graphic_current']['reason'] == 'binding_constant_missing'
    assert all(fan['speed_rpm']['status'] == 'unavailable' for fan in gpu['fans'])


@pytest.mark.parametrize('error', [None, pynvml.NVML_ERROR_NOT_SUPPORTED,
                                  pynvml.NVML_ERROR_FUNCTION_NOT_FOUND,
                                  pynvml.NVML_ERROR_NO_PERMISSION])
def test_indexed_rpm_and_partial_errors(identified, error):
    from ctypes import cast, POINTER
    identified.c_nvmlFanSpeedInfo_t = pynvml.c_nvmlFanSpeedInfo_t
    identified.nvmlFanSpeedInfo_v1 = pynvml.nvmlFanSpeedInfo_v1
    identified._nvmlCheckReturn = pynvml._nvmlCheckReturn
    queried = []
    def native(handle, pointer):
        info = cast(pointer, POINTER(pynvml.c_nvmlFanSpeedInfo_t)).contents
        assert info.version == pynvml.nvmlFanSpeedInfo_v1
        queried.append(info.fan)
        info.speed = info.fan * 1000
        return error if error is not None and info.fan == 1 else 0
    def resolve(name):
        assert name == 'nvmlDeviceGetFanSpeedRPM'
        return native
    identified._nvmlGetFunctionPointer = resolve
    result = NvmlBackend(identified).read_snapshot()
    fans = result['gpus'][0]['fans']
    assert queried == [0, 1]
    assert fans[0]['speed_rpm']['value'] == 0
    if error is None:
        assert fans[1]['speed_rpm']['value'] == 1000
    else:
        assert 'value' not in fans[1]['speed_rpm']
        expected = {pynvml.NVML_ERROR_NOT_SUPPORTED: 'unsupported',
                    pynvml.NVML_ERROR_FUNCTION_NOT_FOUND: 'unavailable',
                    pynvml.NVML_ERROR_NO_PERMISSION: 'error'}[error]
        assert fans[1]['speed_rpm']['status'] == expected
    assert fans[1]['speed_percent']['value'] == 31
    assert result['status'] == ('error' if error == pynvml.NVML_ERROR_NO_PERMISSION else 'ok')
    assert identified.calls[-1] == 'nvmlShutdown'
