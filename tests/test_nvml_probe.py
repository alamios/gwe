# SPDX-License-Identifier: GPL-3.0-or-later
"""No test initializes real NVML or writes to GPU hardware."""

import json
from types import SimpleNamespace

import pynvml
import pytest

from gwe import nvml_probe


@pytest.fixture
def binding():
    calls = []
    functions = {
        "nvmlInit": lambda: None,
        "nvmlShutdown": lambda: None,
        "nvmlSystemGetDriverVersion": lambda: b"580.test",
        "nvmlDeviceGetCount": lambda: 1,
        "nvmlDeviceGetHandleByIndex": lambda index: object(),
        "nvmlDeviceGetName": lambda handle: b"Test GPU",
        "nvmlDeviceGetTemperature": lambda handle, sensor: 45,
        "nvmlDeviceGetNumFans": lambda handle: 2,
        "nvmlDeviceGetMinMaxFanSpeed": lambda handle: [30, 100],
        "nvmlDeviceGetFanSpeed_v2": lambda handle, fan: 30 + fan,
    }
    fake = SimpleNamespace(
        NVMLError=pynvml.NVMLError,
        NVML_ERROR_NOT_SUPPORTED=pynvml.NVML_ERROR_NOT_SUPPORTED,
        NVML_ERROR_FUNCTION_NOT_FOUND=pynvml.NVML_ERROR_FUNCTION_NOT_FOUND,
        NVML_TEMPERATURE_GPU=pynvml.NVML_TEMPERATURE_GPU,
        calls=calls,
    )
    for name, function in functions.items():
        def record(*args, name=name, function=function):
            calls.append(name)
            return function(*args)
        setattr(fake, name, record)
    return fake


def fail(code):
    def raise_error(*args):
        raise pynvml.NVMLError(code)
    return raise_error


def test_snapshot_is_serializable_and_uses_only_reads(binding):
    report = nvml_probe.collect_report(binding)
    assert report["status"] == "ok"
    assert report["driver"]["value"] == "580.test"
    gpu = report["gpus"][0]
    assert gpu["temperature_c"]["value"] == 45
    assert gpu["manual_fan_range_percent"]["value"] == [30, 100]
    assert [fan["speed_percent"]["value"] for fan in gpu["fans"]] == [30, 31]
    assert binding.calls[0] == "nvmlInit"
    assert binding.calls[-1] == "nvmlShutdown"
    assert set(binding.calls) <= nvml_probe._READS | {"nvmlInit", "nvmlShutdown"}
    assert "uuid" not in json.dumps(report).lower()


@pytest.mark.parametrize("code,status", [
    (pynvml.NVML_ERROR_NOT_SUPPORTED, "unsupported"),
    (pynvml.NVML_ERROR_FUNCTION_NOT_FOUND, "unavailable"),
    (pynvml.NVML_ERROR_NO_PERMISSION, "error"),
    (pynvml.NVML_ERROR_GPU_IS_LOST, "error"),
])
def test_missing_temperature_is_not_zero_and_fans_are_still_reported(binding, code, status):
    binding.nvmlDeviceGetTemperature = fail(code)
    report = nvml_probe.collect_report(binding)
    temp = report["gpus"][0]["temperature_c"]
    assert temp["status"] == status
    assert "value" not in temp
    assert len(report["gpus"][0]["fans"]) == 2
    assert report["status"] == ("error" if status == "error" else "ok")
    assert binding.calls[-1] == "nvmlShutdown"


def test_missing_binding_function(binding):
    del binding.nvmlDeviceGetNumFans
    report = nvml_probe.collect_report(binding)
    assert report["gpus"][0]["fan_count"]["status"] == "unavailable"
    assert report["gpus"][0]["fans"] == []


def test_partial_fan_read_failure(binding):
    def fan_speed(handle, fan):
        if fan == 1:
            raise pynvml.NVMLError(pynvml.NVML_ERROR_UNKNOWN)
        return 30
    binding.nvmlDeviceGetFanSpeed_v2 = fan_speed
    report = nvml_probe.collect_report(binding)
    assert report["status"] == "error"
    assert report["gpus"][0]["fans"][0]["speed_percent"]["value"] == 30
    assert report["gpus"][0]["fans"][1]["speed_percent"]["status"] == "error"


def test_init_failure_does_not_query_or_shutdown(binding):
    binding.nvmlInit = fail(pynvml.NVML_ERROR_LIBRARY_NOT_FOUND)
    report = nvml_probe.collect_report(binding)
    assert report["status"] == "error"
    assert binding.calls == []


@pytest.mark.parametrize("operation", ["nvmlDeviceGetCount", "nvmlDeviceGetHandleByIndex"])
def test_enumeration_failure_shuts_down(binding, operation):
    setattr(binding, operation, fail(pynvml.NVML_ERROR_GPU_IS_LOST))
    report = nvml_probe.collect_report(binding)
    assert report["status"] == "error"
    assert binding.calls[-1] == "nvmlShutdown"


def test_no_devices(binding):
    binding.nvmlDeviceGetCount = lambda: 0
    assert nvml_probe.collect_report(binding)["status"] == "no_devices"
    assert binding.calls[-1] == "nvmlShutdown"


def test_shutdown_failure_is_reported(binding):
    binding.nvmlShutdown = fail(pynvml.NVML_ERROR_UNKNOWN)
    report = nvml_probe.collect_report(binding)
    assert report["status"] == "error"
    assert report["errors"][-1]["operation"] == "nvmlShutdown"


def test_unexpected_error_still_shuts_down(binding):
    binding.nvmlDeviceGetName = lambda handle: 1 / 0
    with pytest.raises(ZeroDivisionError):
        nvml_probe.collect_report(binding)
    assert binding.calls[-1] == "nvmlShutdown"


@pytest.mark.parametrize("count,exit_code", [(0, 1), (1, 0)])
def test_cli_json_and_exit_code(binding, monkeypatch, capsys, count, exit_code):
    binding.nvmlDeviceGetCount = lambda: count
    monkeypatch.setattr(nvml_probe.importlib, "import_module", lambda name: binding)
    assert nvml_probe.main([]) == exit_code
    report = json.loads(capsys.readouterr().out)
    assert report["device_count"]["value"] == count
    assert report["binding_version"]


def test_cli_missing_binding(monkeypatch, capsys):
    def missing(name):
        raise ModuleNotFoundError(name=name)
    monkeypatch.setattr(nvml_probe.importlib, "import_module", missing)
    assert nvml_probe.main([]) == 1
    assert "nvidia-ml-py" in json.loads(capsys.readouterr().out)["message"]
