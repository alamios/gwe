# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit power UI actions; the GUI never calls an NVML setter."""
from concurrent.futures import ThreadPoolExecutor
import math
import time

from gwe.fan_service import FanClient


def to_mw(watts):
    if isinstance(watts, bool) or not isinstance(watts, (int, float)) or not math.isfinite(watts):
        raise ValueError('Invalid power')
    mw = round(watts * 1000)
    if not 1 <= mw <= 0xffffffff or abs(watts * 1000 - mw) > .00001:
        raise ValueError('Invalid power precision')
    return mw


class PowerController:
    def __init__(self, view, path, *, allowed=False, factory=FanClient, clock=time.monotonic,
                 fan_busy=lambda: False, event_sink=lambda *args, **kwargs: None):
        self.view, self.path, self.allowed = view, path, allowed
        self.factory, self.clock, self.fan_busy, self.event_sink = factory, clock, fan_busy, event_sink
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.pending = None
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
        return self.pending is not None or self.remote_busy or self.operation_id is not None

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
        if gpu is None or self.clock() - self.sample_time > 2.5:
            return False
        try:
            low, limit, high = (to_mw(v) for v in (gpu.power.minimum, gpu.power.limit, gpu.power.maximum))
        except ValueError:
            return False
        return bool(gpu.info.uuid) and low <= limit <= high and low < high

    def refresh(self):
        enabled = (self.allowed and self.available and self.valid() and self.service_uuid == self.snapshot.info.uuid and not self.busy
                   and not self.fan_busy() and not self.closed)
        self.view.set_service_power_enabled(enabled, self.message)

    def apply(self):
        self.refresh()
        if not (self.allowed and self.available and self.valid() and not self.busy
                and self.service_uuid == self.snapshot.info.uuid
                and not self.fan_busy() and not self.closed):
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
        self.refresh()

    def pulse(self):
        if self.closed:
            return
        if self.pending is not None and self.pending.done():
            future, self.pending = self.pending, None
            try:
                result = future.result()
                if not isinstance(result, dict) or result.get('ok') is not True:
                    raise ValueError('Service unavailable or rejected request')
                # Status identity is checked before enabling any write action.
                if not self.snapshot or result.get('gpu_uuid') != self.snapshot.info.uuid:
                    raise ValueError('Service identity mismatch')
                self.service_uuid = result['gpu_uuid']
                self.available = True
                state = result.get('state')
                if state not in ('idle', 'busy', 'applied', 'rolled_back', 'failed', 'fault'):
                    raise ValueError('Invalid power state')
                if type(result.get('operation_id')) is not int or result['operation_id'] < 0:
                    raise ValueError('Invalid operation identifier')
                if state == 'fault':
                    raise ValueError('Power recovery fault')
                self.remote_busy = state == 'busy'
                if self.operation_id == -1:
                    self.operation_id = result.get('operation_id')
                if self.operation_id is not None:
                    if result.get('operation_id') != self.operation_id:
                        raise ValueError('Operation changed')
                    if state == 'applied':
                        previous, applied = result['previous_mw'], result['applied_mw']
                        if (type(previous) is not int or type(applied) is not int
                                or previous != self.expected or applied != self.requested):
                            raise ValueError('Power result mismatch')
                        self.message = f'Power verified: {applied / 1000:g} W (previous {previous / 1000:g} W). Closing preserves this limit.'
                        self.operation_id = None
                        self.event_sink('power_verified')
                    elif state == 'rolled_back':
                        if (type(result.get('applied_mw')) is not int or result['applied_mw'] != self.expected
                                or result.get('previous_mw') != self.expected):
                            raise ValueError('Rollback result mismatch')
                        self.message = 'Power operation failed; previous limit restored and verified.'
                        self.operation_id = None
                        self.event_sink('power_rolled_back')
                    elif state in ('failed', 'fault'):
                        raise ValueError('Power result failed')
                if not self.available:
                    self.message = 'Power control unavailable: service GPU does not match telemetry.'
            except Exception:
                self.available = False
                self.remote_busy = False
                self.operation_id = None
                self.message = 'Power result unavailable or rejected. Check live limit and service; no automatic retry.'
                self.event_sink('power_failed')
            self.next_poll = self.clock() + (.2 if self.remote_busy else 2)
        if (self.allowed and self.pending is None and self.valid() and not self.fan_busy()
                and self.clock() >= self.next_poll):
            self.next_poll = self.clock() + 2
            self.pending = self.executor.submit(self._request, 'power_status')
        self.refresh()

    def close(self):
        if self.closed:
            return
        self.closed = True
        # One-shot service transaction continues independently; no reset at close.
        self.executor.shutdown(wait=True, cancel_futures=True)
        self.refresh()
