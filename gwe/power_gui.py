# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit power UI actions; the GUI never calls an NVML setter."""
from concurrent.futures import ThreadPoolExecutor
import math
import time

from gwe.fan_service import FanClient
from gwe.runtime_mode import native_desktop


POWER_ERRORS = {
    'trial_guard_active': 'The trial accepts only 240 W or 250 W. Select one and press Apply.',
    'stale_power': 'The live limit changed. Wait for telemetry before pressing Apply again.',
    'outside_limits': 'The requested power is outside the live GPU limits.',
    'power_busy': 'The service is busy; wait before pressing Apply again.',
    'busy': 'Fan control is starting, restoring or faulted; wait for a stable session.',
    'recovery_pending': 'Recovery is pending. Check the service before another operation.',
    'recovery_failed': 'Recovery is not verified. Check the service.',
    'worker_unavailable': 'The service could not start its power worker.',
    'worker_lost': 'The power worker ended without a verified result.',
    'worker_stuck': 'The power worker stalled. Check service recovery.',
    'driver_error': 'The driver rejected the power operation; check the service.',
    'verification_failed': 'The driver readback did not match the requested limit.',
    'identity_mismatch': 'The service GPU does not match telemetry.',
    'invalid_response': 'The service returned an invalid or mismatched power result.',
    'request_refused': 'The service rejected the power request.',
    'service_connection_unavailable': 'The power service is unavailable. Quit and check service recovery before reopening.',
    'socket_timeout': 'The power service did not respond in time. Check the live limit and service.',
    'socket_permission_denied': 'Permission to connect to the power service was denied.',
    'client_error': 'Power result unavailable. Check the live limit and service.',
}


class PowerResponseError(ValueError):
    def __init__(self, code):
        self.code = code if isinstance(code, str) and code in POWER_ERRORS else 'request_refused'
        super().__init__(self.code)


def to_mw(watts):
    if isinstance(watts, bool) or not isinstance(watts, (int, float)) or not math.isfinite(watts):
        raise ValueError('Invalid power')
    mw = round(watts * 1000)
    if not 1 <= mw <= 0xffffffff or abs(watts * 1000 - mw) > .00001:
        raise ValueError('Invalid power precision')
    return mw


class PowerController:
    def __init__(self, view, path, *, allowed=False, factory=FanClient, clock=time.monotonic,
                 fan_busy=lambda: False, fan_active=lambda: False, event_sink=lambda *args, **kwargs: None,
                 telemetry_ttl=2.5):
        self.view, self.path, self.allowed = view, path, allowed
        self.factory, self.clock, self.fan_busy, self.event_sink = factory, clock, fan_busy, event_sink
        self.fan_active = fan_active
        self.telemetry_ttl = telemetry_ttl
        self.power_with_fan = False
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.pending = None
        self.pending_operation = 'power_status'
        self.last_error = None
        self.closed = False
        self.available = False
        self.remote_busy = False
        self.snapshot = None
        self.sample_time = float('-inf')
        self.next_poll = 0
        self.operation_id = None
        self.requested = self.expected = None
        self.service_uuid = None
        self.message = 'Power control requires an explicit Apply. Closing preserves a verified limit.'

    @property
    def busy(self):
        request_busy = self.pending is not None and (
            not native_desktop() or self.pending_operation != 'power_status')
        return request_busy or self.remote_busy or self.operation_id is not None

    def _request(self, op, **fields):
        client = self.factory(self.path)
        try:
            return client.request(op, **fields)
        finally:
            client.close()

    def telemetry(self, gpu):
        self.snapshot = gpu
        self.sample_time = self.clock()
        self.refresh()

    def valid(self):
        gpu = self.snapshot
        if gpu is None or self.clock() - self.sample_time > self.telemetry_ttl:
            return False
        try:
            low, limit, high = (to_mw(v) for v in (gpu.power.minimum, gpu.power.limit, gpu.power.maximum))
        except ValueError:
            return False
        return bool(gpu.info.uuid) and low <= limit <= high and low < high

    def refresh(self):
        enabled = (self.allowed and self.available and self.valid() and self.service_uuid == self.snapshot.info.uuid and not self.busy
                   and not self.fan_busy() and (not self.fan_active() or self.power_with_fan) and not self.closed)
        self.view.set_service_power_enabled(enabled, self.message)

    def apply(self):
        self.refresh()
        if not (self.allowed and self.available and self.valid() and not self.busy
                and self.service_uuid == self.snapshot.info.uuid
                and not self.fan_busy() and (not self.fan_active() or self.power_with_fan) and not self.closed):
            return
        try:
            requested = to_mw(self.view.get_power_limit()[1])
            gpu = self.snapshot
            if not to_mw(gpu.power.minimum) <= requested <= to_mw(gpu.power.maximum):
                raise ValueError('Outside limits')
            expected = to_mw(gpu.power.limit)
        except ValueError:
            self.message = 'Invalid power limit; no request sent.'
            self.refresh()
            return
        self.operation_id = -1
        self.requested, self.expected = requested, expected
        self.message = 'Applying power limit; awaiting service verification.'
        self.pending = self.executor.submit(self._request, 'power_apply', limit_mw=requested,
                                            expected_mw=expected, expected_uuid=gpu.info.uuid)
        self.pending_operation = 'power_apply'
        self.refresh()

    def pulse(self):
        if self.closed:
            return
        if self.pending is not None and self.pending.done():
            future, self.pending = self.pending, None
            operation = self.pending_operation
            try:
                result = future.result()
                if not isinstance(result, dict):
                    raise PowerResponseError('invalid_response')
                if result.get('ok') is not True:
                    raise PowerResponseError(result.get('error'))
                # Status identity is checked before enabling any write action.
                if not self.snapshot or result.get('gpu_uuid') != self.snapshot.info.uuid:
                    raise PowerResponseError('identity_mismatch')
                self.service_uuid = result['gpu_uuid']
                self.power_with_fan = result.get('power_with_fan') is True
                self.available = True
                state = result.get('state')
                if state not in ('idle', 'busy', 'applied', 'rolled_back', 'failed', 'fault'):
                    raise PowerResponseError('invalid_response')
                if type(result.get('operation_id')) is not int or result['operation_id'] < 0:
                    raise PowerResponseError('invalid_response')
                if state == 'fault':
                    raise PowerResponseError(result.get('error', 'recovery_failed'))
                self.remote_busy = state == 'busy'
                if self.operation_id == -1:
                    self.operation_id = result.get('operation_id')
                if self.operation_id is not None:
                    if result.get('operation_id') != self.operation_id:
                        raise PowerResponseError('invalid_response')
                    if state == 'applied':
                        previous, applied = result['previous_mw'], result['applied_mw']
                        if (type(previous) is not int or type(applied) is not int
                                or previous != self.expected or applied != self.requested):
                            raise PowerResponseError('invalid_response')
                        self.message = f'Power verified: {applied / 1000:g} W (previous {previous / 1000:g} W). Closing preserves this limit.'
                        self.operation_id = None
                        self.event_sink('power_verified', operation=operation)
                    elif state == 'rolled_back':
                        if (type(result.get('applied_mw')) is not int or result['applied_mw'] != self.expected
                                or result.get('previous_mw') != self.expected):
                            raise PowerResponseError('invalid_response')
                        self.message = 'Power operation failed; previous limit restored and verified.'
                        self.operation_id = None
                        self.event_sink('power_rolled_back', operation=operation)
                    elif state in ('failed', 'fault'):
                        raise PowerResponseError(result.get('error'))
                if (self.last_error in ('service_connection_unavailable', 'socket_timeout')
                        and self.operation_id is None and state == 'idle'):
                    self.message = 'Power service connected. Select a limit and press Apply; startup changes nothing.'
                self.last_error = None
            except Exception as error:
                if isinstance(error, PowerResponseError):
                    code = error.code
                elif isinstance(error, TimeoutError):
                    code = 'socket_timeout'
                elif isinstance(error, PermissionError):
                    code = 'socket_permission_denied'
                elif isinstance(error, (ConnectionError, FileNotFoundError)):
                    code = 'service_connection_unavailable'
                else:
                    code = 'client_error'
                self.available = False
                self.remote_busy = False
                self.operation_id = None
                self.last_error = code
                self.message = f'Power: {POWER_ERRORS[code]} [{code}]; no automatic retry.'
                self.event_sink('power_failed', operation=operation, error=code)
            self.next_poll = self.clock() + (.2 if self.remote_busy else 2)
        if (self.allowed and self.pending is None and self.valid() and not self.fan_busy()
                and self.clock() >= self.next_poll):
            self.next_poll = self.clock() + 2
            self.pending = self.executor.submit(self._request, 'power_status')
            self.pending_operation = 'power_status'
        self.refresh()

    def close(self):
        if self.closed:
            return
        self.closed = True
        # One-shot service transaction continues independently; no reset at close.
        self.executor.shutdown(wait=True, cancel_futures=True)
        self.refresh()
