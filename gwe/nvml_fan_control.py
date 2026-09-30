# SPDX-License-Identifier: GPL-3.0-or-later
"""Experimental serialized curve session; requires an external supervising owner.

No implicit NVML import/init, CLI, privilege escalation, profile loading or UI wiring.
The caller supplies an initialized binding and must supervise calls independently.
"""

import threading
import time

from gwe.fan_curve import FanCurve, finite_number


class FanControlError(RuntimeError):
    """Control stopped; the state distinguishes verified recovery from failure."""


class NvmlFanController:
    """One explicitly selected GPU for one session, with latched failures.

    Locking serializes this instance only. It does not exclude other applications.
    Tick deadlines are checked on return; a hung native call needs a process watchdog.
    """

    def __init__(self, nvml, gpu_uuid, curve, *, clock=time.monotonic,
                 max_read_seconds=2, max_interval_seconds=5, temperature_ceiling=85):
        if not isinstance(gpu_uuid, str) or not gpu_uuid.strip():
            raise ValueError("Explicit GPU identity required")
        if not isinstance(curve, FanCurve):
            raise ValueError("Validated FanCurve required")
        if not all(finite_number(v) and v > 0 for v in (max_read_seconds, max_interval_seconds)):
            raise ValueError("Positive finite deadlines required")
        if not finite_number(temperature_ceiling) or not 0 < temperature_ceiling <= 100:
            raise ValueError("Invalid temperature ceiling")
        self._nvml, self._uuid, self._curve, self._clock = nvml, gpu_uuid, curve, clock
        self._read_timeout, self._interval, self._ceiling = max_read_seconds, max_interval_seconds, temperature_ceiling
        self._lock = threading.RLock()
        self._fans = ()
        self._limits = None
        self._last_tick = None
        self._duty = None
        self._applied_temperature = None
        self.state = "new"
        self.recovery_errors = ()

    def _handle(self):
        handle = self._nvml.nvmlDeviceGetHandleByUUID(self._uuid)
        if self._nvml.nvmlDeviceGetUUID(handle) != self._uuid:
            raise FanControlError("GPU identity mismatch; no index fallback")
        return handle

    def _deadline(self, started):
        now = self._clock()
        if not finite_number(now) or not 0 <= now - started <= self._read_timeout:
            raise FanControlError("Telemetry or control deadline exceeded")

    def _capabilities(self, handle):
        count = self._nvml.nvmlDeviceGetNumFans(handle)
        if type(count) is not int or not 1 <= count <= 32:
            raise FanControlError("Invalid fan count")
        limits = tuple(self._nvml.nvmlDeviceGetMinMaxFanSpeed(handle))
        try:
            self._curve.validate_limits(*limits)
        except (TypeError, ValueError) as error:
            raise FanControlError("Curve incompatible with reported fan limits") from error
        return tuple(range(count)), limits

    def _policies(self, handle):
        return [self._nvml.nvmlDeviceGetFanControlPolicy_v2(handle, i) for i in self._fans]

    def _temperature(self, handle):
        value = self._nvml.nvmlDeviceGetTemperature(handle, self._nvml.NVML_TEMPERATURE_GPU)
        if not finite_number(value) or not 0 <= value < self._ceiling:
            raise FanControlError("Missing, invalid or excessive GPU temperature")
        return value

    def _restore(self):
        errors = []
        for fan in self._fans:
            try:
                self._nvml.nvmlDeviceSetDefaultFanSpeed_v2(self._handle(), fan)
            except Exception as error:
                errors.append(f"fan {fan} reset: {type(error).__name__}")
        for fan in self._fans:
            try:
                policy = self._nvml.nvmlDeviceGetFanControlPolicy_v2(self._handle(), fan)
                if policy != self._nvml.NVML_FAN_POLICY_TEMPERATURE_CONTINOUS_SW:
                    raise FanControlError("Policy is not automatic")
            except Exception as error:
                errors.append(f"fan {fan} verification: {type(error).__name__}")
        self.recovery_errors = tuple(errors)
        self._duty = self._applied_temperature = None
        if errors:
            self.state = "recovery_failed"
            raise FanControlError("; ".join(errors))

    def _fault(self):
        self.state = "fault"
        self._restore()

    def start(self, *, on_owned=None):
        """Validate before taking ownership; resets prove support before manual writes."""
        with self._lock:
            if self.state != "new":
                raise FanControlError("Create a new session after stop or failure")
            started = self._clock()
            try:
                handle = self._handle()
                fans, limits = self._capabilities(handle)
                self._temperature(handle)
                policies = [self._nvml.nvmlDeviceGetFanControlPolicy_v2(handle, i) for i in fans]
                if any(p != self._nvml.NVML_FAN_POLICY_TEMPERATURE_CONTINOUS_SW for p in policies):
                    raise FanControlError("GPU is already under manual control")
                self._deadline(started)
                # Ownership starts only after all read-only checks pass.
                if on_owned is not None:
                    on_owned(fans)
                self._fans, self._limits = fans, limits
                self._restore()
                self._deadline(started)
                self.state = "automatic"
                self._last_tick = self._clock()
            except BaseException:
                self._fault()
                raise

    def tick(self):
        """Read fresh telemetry, compute one curve step and verify every fan target."""
        with self._lock:
            if self.state not in ("automatic", "manual"):
                raise FanControlError("Session is not active")
            started = self._clock()
            try:
                if not finite_number(started) or not 0 <= started - self._last_tick <= self._interval:
                    raise FanControlError("Control tick is stale; explicit restart required")
                handle = self._handle()
                if self._capabilities(handle) != (self._fans, self._limits):
                    raise FanControlError("Fan capabilities changed")
                temperature = self._temperature(handle)
                expected = (self._nvml.NVML_FAN_POLICY_MANUAL if self.state == "manual"
                            else self._nvml.NVML_FAN_POLICY_TEMPERATURE_CONTINOUS_SW)
                if any(p != expected for p in self._policies(handle)):
                    raise FanControlError("Fan ownership/policy changed")
                if self.state == "manual":
                    if any(self._nvml.nvmlDeviceGetTargetFanSpeed(handle, i) != self._duty for i in self._fans):
                        raise FanControlError("Manual target changed outside this session")
                self._deadline(started)
                duty = self._curve.demand(temperature, self._duty, self._applied_temperature)
                if duty is None:
                    if self.state == "manual":
                        self._restore()
                    self.state = "automatic"
                elif duty != self._duty:
                    # Rounding must not take fractional limits outside the accepted range.
                    if not self._limits[0] <= duty <= self._limits[1]:
                        raise FanControlError("Rounded target exceeds manual limits")
                    for fan in self._fans:
                        self._deadline(started)
                        self._nvml.nvmlDeviceSetFanSpeed_v2(self._handle(), fan, duty)
                    for fan in self._fans:
                        handle = self._handle()
                        if (self._nvml.nvmlDeviceGetFanControlPolicy_v2(handle, fan) != self._nvml.NVML_FAN_POLICY_MANUAL
                                or self._nvml.nvmlDeviceGetTargetFanSpeed(handle, fan) != duty):
                            raise FanControlError("Manual write verification failed")
                    self._duty, self._applied_temperature = duty, temperature
                    self.state = "manual"
                self._deadline(started)
                # Anchor to collection start so slow reads cannot extend the next deadline.
                self._last_tick = started
                return {"temperature_c": temperature, "duty_percent": duty, "state": self.state}
            except BaseException:
                self._fault()
                raise

    def stop(self):
        """Retry recovery even after a previous failure; never rearm this instance."""
        with self._lock:
            if self.state == "closed":
                return
            self.state = "fault"
            self._restore()
            self.state = "closed"
