# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only NVIDIA telemetry, independent of GTK, X11 and application settings."""

import importlib
import threading
import time


class NvmlBackend:
    """Serialize snapshots and reacquire handles every time, including after errors.

    UUIDs are returned for application selection but must be redacted from shared
    diagnostics. Per-reading status describes read availability, never permission
    to control hardware. This backend exposes no write operations.
    """

    def __init__(self, nvml=None):
        self._nvml = nvml if nvml is not None else importlib.import_module("pynvml")
        self._lock = threading.Lock()

    def read_snapshot(self, gpu_uuid=None):
        if gpu_uuid is not None and (not isinstance(gpu_uuid, str) or not gpu_uuid.strip()):
            raise ValueError("GPU UUID must be a non-empty string")
        with self._lock:
            started = time.monotonic()
            result = collect_report(self._nvml, gpu_uuid=gpu_uuid, include_identity=True)
            result["started_monotonic_s"] = started
            result["finished_monotonic_s"] = time.monotonic()
            return result


_READS = frozenset({
    "nvmlSystemGetDriverVersion", "nvmlDeviceGetCount", "nvmlDeviceGetHandleByIndex",
    "nvmlDeviceGetName", "nvmlDeviceGetTemperature", "nvmlDeviceGetNumFans",
    "nvmlDeviceGetMinMaxFanSpeed", "nvmlDeviceGetFanSpeed_v2",
    "nvmlDeviceGetUUID", "nvmlDeviceGetHandleByUUID", "nvmlDeviceGetIndex",
    "nvmlDeviceGetMemoryInfo", "nvmlDeviceGetUtilizationRates", "nvmlDeviceGetPowerUsage",
})


def collect_report(nvml, *, gpu_uuid=None, include_identity=False):
    """Collect one snapshot using an injected binding, without opening a display.

    Unsupported optional queries are distinguished from failures. No setter is
    resolved or invoked; readable telemetry does not establish write support.
    Device indices identify entries in this snapshot only, not persistent GPUs.
    Identity queries are opt-in for diagnostic privacy. Selection by UUID never
    falls back to another GPU. Unsupported identity is a snapshot error.
    """
    report = {"schema_version": 2, "status": "ok", "gpus": [], "errors": []}
    errors = report["errors"]

    def read(name, *args, convert=None):
        if name not in _READS:
            raise ValueError(f"Not a diagnostic read: {name}")
        try:
            function = getattr(nvml, name, None)
            if function is None:
                return {"status": "unavailable", "reason": "binding_function_missing"}
            value = function(*args)
            if isinstance(value, bytes):
                value = value.decode("utf-8", errors="replace")
            if convert is not None:
                value = convert(value)
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
        indices = [None] if gpu_uuid is not None else range(count["value"])
        for index in indices:
            gpu = {"index": index}
            report["gpus"].append(gpu)
            handle_result = (read("nvmlDeviceGetHandleByUUID", gpu_uuid) if gpu_uuid is not None
                             else read("nvmlDeviceGetHandleByIndex", index))
            if handle_result["status"] != "ok":
                gpu["device_access"] = handle_result
                report["status"] = "error"
                continue
            handle = handle_result["value"]
            if include_identity or gpu_uuid is not None:
                identity = gpu["uuid"] = read("nvmlDeviceGetUUID", handle)
                if identity["status"] != "ok":
                    report["status"] = "error"
                    continue
                if gpu_uuid is not None and identity["value"] != gpu_uuid:
                    errors.append({"operation": "identity_check", "message": "GPU identity mismatch"})
                    continue
            if gpu_uuid is not None:
                current_index = read("nvmlDeviceGetIndex", handle)
                gpu["index"] = current_index.get("value")
            gpu["memory_bytes"] = read(
                "nvmlDeviceGetMemoryInfo", handle,
                convert=lambda memory: {"total": memory.total, "used": memory.used, "free": memory.free})
            gpu["utilization_percent"] = read(
                "nvmlDeviceGetUtilizationRates", handle,
                convert=lambda util: {"gpu": util.gpu, "memory": util.memory})
            gpu["power_w"] = read("nvmlDeviceGetPowerUsage", handle, convert=lambda mw: mw / 1000)
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

