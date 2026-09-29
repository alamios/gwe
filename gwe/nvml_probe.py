# SPDX-License-Identifier: GPL-3.0-or-later
"""Standalone read-only NVML diagnostics; never imports the GWE application."""

import argparse
import importlib
import json
import platform
from importlib.metadata import version


_READS = frozenset({
    "nvmlSystemGetDriverVersion", "nvmlDeviceGetCount", "nvmlDeviceGetHandleByIndex",
    "nvmlDeviceGetName", "nvmlDeviceGetTemperature", "nvmlDeviceGetNumFans",
    "nvmlDeviceGetMinMaxFanSpeed", "nvmlDeviceGetFanSpeed_v2",
})


def collect_report(nvml):
    """Collect one snapshot using an injected binding, without opening a display.

    Unsupported optional queries are distinguished from failures. No setter is
    resolved or invoked; readable telemetry does not establish write support.
    Device indices identify entries in this snapshot only, not persistent GPUs.
    """
    report = {"schema_version": 1, "status": "ok", "gpus": [], "errors": []}
    errors = report["errors"]

    def read(name, *args):
        if name not in _READS:
            raise ValueError(f"Not a diagnostic read: {name}")
        try:
            function = getattr(nvml, name, None)
            if function is None:
                return {"status": "unavailable", "reason": "binding_function_missing"}
            value = function(*args)
            if isinstance(value, bytes):
                value = value.decode("utf-8", errors="replace")
            return {"status": "ok", "value": value}
        except nvml.NVMLError as error:
            if error.value == nvml.NVML_ERROR_NOT_SUPPORTED:
                status = "unsupported"
            elif error.value == nvml.NVML_ERROR_FUNCTION_NOT_FOUND:
                status = "unavailable"
            else:
                status = "error"
            result = {"status": status, "error_code": error.value, "message": str(error)}
            if status == "error":
                errors.append({"operation": name, **result})
            return result

    try:
        nvml.nvmlInit()
    except nvml.NVMLError as error:
        report["status"] = "error"
        errors.append({"operation": "nvmlInit", "error_code": error.value, "message": str(error)})
        return report

    try:
        report["driver"] = read("nvmlSystemGetDriverVersion")
        count = report["device_count"] = read("nvmlDeviceGetCount")
        if count["status"] != "ok":
            report["status"] = "error"
            return report
        if count["value"] == 0:
            report["status"] = "no_devices"
        for index in range(count["value"]):
            gpu = {"index": index}
            report["gpus"].append(gpu)
            handle_result = read("nvmlDeviceGetHandleByIndex", index)
            if handle_result["status"] != "ok":
                gpu["device_access"] = handle_result
                report["status"] = "error"
                continue
            handle = handle_result["value"]
            gpu["name"] = read("nvmlDeviceGetName", handle)
            gpu["temperature_c"] = read("nvmlDeviceGetTemperature", handle, nvml.NVML_TEMPERATURE_GPU)
            fans = gpu["fan_count"] = read("nvmlDeviceGetNumFans", handle)
            gpu["manual_fan_range_percent"] = read("nvmlDeviceGetMinMaxFanSpeed", handle)
            gpu["fans"] = []
            if fans["status"] == "ok":
                for fan in range(fans["value"]):
                    gpu["fans"].append({
                        "index": fan, "speed_percent": read("nvmlDeviceGetFanSpeed_v2", handle, fan),
                    })
    finally:
        try:
            nvml.nvmlShutdown()
        except nvml.NVMLError as error:
            errors.append({"operation": "nvmlShutdown", "error_code": error.value, "message": str(error)})
        if errors:
            report["status"] = "error"
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read NVIDIA telemetry as JSON without changing GPU settings.")
    parser.parse_args(argv)
    try:
        nvml = importlib.import_module("pynvml")
    except ModuleNotFoundError as error:
        if error.name != "pynvml":
            raise
        print(json.dumps({"status": "error", "message": "Install nvidia-ml-py in this Python environment."}))
        return 1
    report = collect_report(nvml)
    report["python_version"] = platform.python_version()
    report["binding_version"] = version("nvidia-ml-py")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
