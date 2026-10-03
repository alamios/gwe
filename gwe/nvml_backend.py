# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only NVIDIA telemetry, independent of GTK, X11 and application settings."""

import importlib
from ctypes import byref
import threading
import time


class NvmlBackend:
    """Serialize snapshots and reacquire handles every time, including after errors.

    UUIDs are returned for application selection but must be redacted from shared
    diagnostics. Per-reading status describes read availability, never permission
    to control hardware. This backend exposes no write operations.
    """

    def __init__(self, nvml=None, *, keep_alive=False):
        self._nvml = nvml if nvml is not None else importlib.import_module("pynvml")
        self._lock = threading.Lock()
        self._keep_alive = keep_alive
        self._initialized = False
        self._closed = False

    def close(self):
        """Release this reader's library reference; never change GPU settings."""
        with self._lock:
            if self._initialized:
                self._nvml.nvmlShutdown()
                self._initialized = False
            self._closed = True

    def read_snapshot(self, gpu_uuid=None):
        if gpu_uuid is not None and (not isinstance(gpu_uuid, str) or not gpu_uuid.strip()):
            raise ValueError("GPU UUID must be a non-empty string")
        with self._lock:
            if self._closed:
                raise RuntimeError('NVML reader is closed')
            started = time.monotonic()
            result = None
            if self._keep_alive and not self._initialized:
                try:
                    self._nvml.nvmlInit()
                    self._initialized = True
                except self._nvml.NVMLError as error:
                    result = {'schema_version': 2, 'status': 'error', 'gpus': [], 'errors': [
                        {'operation': 'nvmlInit', 'error_code': error.value, 'message': str(error)}]}
            if result is None:
                result = collect_report(self._nvml, gpu_uuid=gpu_uuid, include_identity=True,
                                        manage_lifecycle=not self._keep_alive)
            if self._initialized and result['status'] in ('error', 'no_devices'):
                # Reinitialize after a read failure; never reuse a lost-device handle/cache.
                try:
                    self._nvml.nvmlShutdown()
                    self._initialized = False
                except self._nvml.NVMLError as error:
                    result['status'] = 'error'
                    result['errors'].append({'operation': 'nvmlShutdown', 'error_code': error.value,
                                             'message': str(error)})
            result["started_monotonic_s"] = started
            result["finished_monotonic_s"] = time.monotonic()
            return result


_READS = frozenset({
    "nvmlSystemGetDriverVersion", "nvmlDeviceGetCount", "nvmlDeviceGetHandleByIndex",
    "nvmlDeviceGetName", "nvmlDeviceGetTemperature", "nvmlDeviceGetNumFans",
    "nvmlDeviceGetMinMaxFanSpeed", "nvmlDeviceGetFanSpeed_v2",
    "nvmlDeviceGetUUID", "nvmlDeviceGetHandleByUUID", "nvmlDeviceGetIndex",
    "nvmlDeviceGetMemoryInfo", "nvmlDeviceGetUtilizationRates", "nvmlDeviceGetPowerUsage",
    "nvmlDeviceGetPowerManagementLimit", "nvmlDeviceGetPowerManagementDefaultLimit",
    "nvmlDeviceGetEnforcedPowerLimit", "nvmlDeviceGetPowerManagementLimitConstraints",
    "nvmlDeviceGetClockInfo", "nvmlDeviceGetMaxClockInfo", "nvmlDeviceGetFanSpeedRPM",
    "nvmlDeviceGetVbiosVersion", "nvmlDeviceGetNumGpuCores", "nvmlDeviceGetMemoryBusWidth",
    "nvmlDeviceGetCurrPcieLinkGeneration", "nvmlDeviceGetMaxPcieLinkGeneration",
    "nvmlDeviceGetCurrPcieLinkWidth", "nvmlDeviceGetMaxPcieLinkWidth",
    "nvmlDeviceGetEncoderUtilization", "nvmlDeviceGetDecoderUtilization",
    "nvmlDeviceGetTemperatureThreshold",
})


def _indexed_fan_rpm(nvml):
    """Use the binding's native structure: its public RPM wrapper fixes fan=0.

    Resolve only this read-only symbol, and never substitute fan zero for another
    fan. Missing binding helpers leave RPM unavailable without affecting percent.
    """
    helpers = ("c_nvmlFanSpeedInfo_t", "nvmlFanSpeedInfo_v1",
               "_nvmlGetFunctionPointer", "_nvmlCheckReturn")
    if any(getattr(nvml, name, None) is None for name in helpers):
        return None

    def read_rpm(handle, fan):
        info = nvml.c_nvmlFanSpeedInfo_t()
        info.version = nvml.nvmlFanSpeedInfo_v1
        info.fan = fan
        function = nvml._nvmlGetFunctionPointer("nvmlDeviceGetFanSpeedRPM")
        nvml._nvmlCheckReturn(function(handle, byref(info)))
        return info.speed

    return read_rpm


def collect_report(nvml, *, gpu_uuid=None, include_identity=False, manage_lifecycle=True):
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
            function = (_indexed_fan_rpm(nvml) if name == "nvmlDeviceGetFanSpeedRPM"
                        else getattr(nvml, name, None))
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

    if manage_lifecycle:
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
            for field, function in (
                    ("vbios", "nvmlDeviceGetVbiosVersion"),
                    ("cuda_cores", "nvmlDeviceGetNumGpuCores"),
                    ("memory_bus_width_bits", "nvmlDeviceGetMemoryBusWidth"),
                    ("pcie_current_generation", "nvmlDeviceGetCurrPcieLinkGeneration"),
                    ("pcie_max_generation", "nvmlDeviceGetMaxPcieLinkGeneration"),
                    ("pcie_current_link", "nvmlDeviceGetCurrPcieLinkWidth"),
                    ("pcie_max_link", "nvmlDeviceGetMaxPcieLinkWidth")):
                gpu[field] = read(function, handle)
            for engine, function in (("encoder", "nvmlDeviceGetEncoderUtilization"),
                                     ("decoder", "nvmlDeviceGetDecoderUtilization")):
                gpu[f"{engine}_utilization"] = read(
                    function, handle, convert=lambda sample: {
                        "percent": sample[0], "sampling_period_us": sample[1]})
            thresholds = gpu["temperature_thresholds_c"] = {}
            for field, constant in (("maximum", "NVML_TEMPERATURE_THRESHOLD_GPU_MAX"),
                                     ("slowdown", "NVML_TEMPERATURE_THRESHOLD_SLOWDOWN"),
                                     ("shutdown", "NVML_TEMPERATURE_THRESHOLD_SHUTDOWN")):
                threshold = getattr(nvml, constant, None)
                thresholds[field] = (
                    read("nvmlDeviceGetTemperatureThreshold", handle, threshold) if threshold is not None
                    else {"status": "unavailable", "reason": "binding_constant_missing"})
            gpu["memory_bytes"] = read(
                "nvmlDeviceGetMemoryInfo", handle,
                convert=lambda memory: {"total": memory.total, "used": memory.used, "free": memory.free})
            gpu["utilization_percent"] = read(
                "nvmlDeviceGetUtilizationRates", handle,
                convert=lambda util: {"gpu": util.gpu, "memory": util.memory})
            gpu["power_w"] = read("nvmlDeviceGetPowerUsage", handle, convert=lambda mw: mw / 1000)
            for field, function in (
                    ("limit", "nvmlDeviceGetPowerManagementLimit"),
                    ("default", "nvmlDeviceGetPowerManagementDefaultLimit"),
                    ("enforced", "nvmlDeviceGetEnforcedPowerLimit")):
                gpu[f"power_{field}_w"] = read(function, handle, convert=lambda mw: mw / 1000)
            gpu["power_constraints_w"] = read(
                "nvmlDeviceGetPowerManagementLimitConstraints", handle,
                convert=lambda limits: {"minimum": limits[0] / 1000, "maximum": limits[1] / 1000})
            clocks = gpu["clocks_mhz"] = {}
            for domain, constant in (("graphic", "NVML_CLOCK_GRAPHICS"), ("sm", "NVML_CLOCK_SM"),
                                     ("memory", "NVML_CLOCK_MEM"), ("video", "NVML_CLOCK_VIDEO")):
                clock_type = getattr(nvml, constant, None)
                for kind, function in (("current", "nvmlDeviceGetClockInfo"),
                                       ("max", "nvmlDeviceGetMaxClockInfo")):
                    clocks[f"{domain}_{kind}"] = (
                        read(function, handle, clock_type) if clock_type is not None else
                        {"status": "unavailable", "reason": "binding_constant_missing"})
            gpu["name"] = read("nvmlDeviceGetName", handle)
            gpu["temperature_c"] = read("nvmlDeviceGetTemperature", handle, nvml.NVML_TEMPERATURE_GPU)
            fans = gpu["fan_count"] = read("nvmlDeviceGetNumFans", handle)
            gpu["manual_fan_range_percent"] = read("nvmlDeviceGetMinMaxFanSpeed", handle)
            gpu["fans"] = []
            if fans["status"] == "ok":
                for fan in range(fans["value"]):
                    gpu["fans"].append({
                        "index": fan, "speed_percent": read("nvmlDeviceGetFanSpeed_v2", handle, fan),
                        "speed_rpm": read("nvmlDeviceGetFanSpeedRPM", handle, fan),
                    })
    finally:
        if manage_lifecycle:
            try:
                nvml.nvmlShutdown()
            except nvml.NVMLError as error:
                errors.append({"operation": "nvmlShutdown", "error_code": error.value, "message": str(error)})
        if errors:
            report["status"] = "error"
    return report
