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
