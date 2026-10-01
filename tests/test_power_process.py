# SPDX-License-Identifier: GPL-3.0-or-later
"""Power process adapter tests with an isolated, shared NVML double."""
import multiprocessing
import os
import time

import pytest

from gwe.power_process import PowerBackend


class FakeNvml:
    """Picklable NVML substitute; all state shared with spawned workers."""

    def __init__(self, context):
        self.current = context.Value('i', 200000)
        self.setter_mode = context.Value('i', 0)
        self.release = context.Event()

    def nvmlInit(self):
        pass

    def nvmlShutdown(self):
        pass

    def nvmlDeviceGetHandleByUUID(self, uuid):
        return uuid

    def nvmlDeviceGetUUID(self, handle):
        return handle

    def nvmlDeviceGetPowerManagementLimitConstraints(self, handle):
        return 100000, 300000

    def nvmlDeviceGetPowerManagementLimit(self, handle):
        return self.current.value

    def nvmlDeviceSetPowerManagementLimit(self, handle, value):
        # 1 exits after the pending journal exists; 2 blocks until killed.
        if value == 250000 and self.setter_mode.value == 1:
            self.current.value = value
            os._exit(17)
        if value == 250000 and self.setter_mode.value == 2:
            self.release.wait(30)
        # 3 makes recovery fail, preserving the pending journal.
        if value == 200000 and self.setter_mode.value == 3:
            raise PermissionError('simulated restore failure')
        self.current.value = value


class Factory:
    def __init__(self, nvml):
        self.nvml = nvml

    def __call__(self):
        return self.nvml


def make_backend(tmp_path, mode=0, timeout=1):
    context = multiprocessing.get_context('spawn')
    nvml = FakeNvml(context)
    nvml.setter_mode.value = mode
    backend = PowerBackend('GPU-test', tmp_path, factory=Factory(nvml),
                           context=context, timeout=timeout)
    return nvml, backend


def until(backend, predicate, timeout=6):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        backend.poll()
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError(f"Timed out in {backend.result}")


def test_apply_runs_in_process_and_commits_record(tmp_path):
    nvml, backend = make_backend(tmp_path)
    try:
        started = backend.start(250000, 200000)
        assert started['state'] == 'busy'
        until(backend, lambda: backend.result['state'] == 'applied')
        assert nvml.current.value == 250000
        assert not (tmp_path / 'power-pending.json').exists()
        assert (tmp_path / 'power-last.json').exists()
    finally:
        backend.close()


@pytest.mark.parametrize('mode,timeout', [(1, 1), (2, .15)])
def test_worker_crash_or_freeze_after_journal_rolls_back(tmp_path, mode, timeout):
    nvml, backend = make_backend(tmp_path, mode, timeout)
    try:
        backend.start(250000, 200000)
        # Exercise busy rejection while a frozen apply worker still owns the slot.
        if mode == 2:
            until(backend, lambda: (tmp_path / 'power-pending.json').exists())
            response = backend.start(220000, 200000)
            assert response == {'ok': False, 'error': 'power_busy'}
        until(backend, lambda: backend.result['state'] == 'rolled_back')
        assert nvml.current.value == 200000
        assert not (tmp_path / 'power-pending.json').exists()
        assert backend.result['previous_mw'] == 200000
    finally:
        backend.close()


def test_failed_rollback_latches_fault_and_keeps_journal(tmp_path):
    nvml, backend = make_backend(tmp_path, mode=1)
    # Crash apply; configure the separate recovery worker to reject restoration.
    try:
        # The shared mode controls the fake's setter: switch to recovery failure
        # once apply has exited and its pending journal is visible.
        backend.start(250000, 200000)
        end = time.monotonic() + 6
        while time.monotonic() < end:
            if ((tmp_path / 'power-pending.json').exists()
                    and not backend.process.is_alive()):
                break
            time.sleep(.01)
        else:
            raise AssertionError('Apply worker did not crash after writing its journal')
        nvml.setter_mode.value = 3
        until(backend, lambda: backend.result['state'] == 'fault')
        assert (tmp_path / 'power-pending.json').exists()
        assert backend.start(220000, 200000) == {'ok': False, 'error': 'power_busy'}
    finally:
        backend.close()


def test_close_kills_worker_and_preserves_journal_for_post_stop(tmp_path):
    nvml, backend = make_backend(tmp_path, mode=2, timeout=30)
    backend.start(250000, 200000)
    until(backend, lambda: (tmp_path / 'power-pending.json').exists())
    started = time.monotonic()
    backend.close()
    assert time.monotonic() - started < 3
    assert (tmp_path / 'power-pending.json').exists()


def test_poll_is_nonblocking_while_worker_is_frozen(tmp_path):
    _, backend = make_backend(tmp_path, mode=2, timeout=30)
    try:
        backend.start(250000, 200000)
        until(backend, lambda: (tmp_path / 'power-pending.json').exists())
        started = time.monotonic()
        for _ in range(20):
            backend.poll()
        assert time.monotonic() - started < .1
    finally:
        backend.close()


def test_trial_guard_restricts_other_power_requests_before_spawn(tmp_path):
    from gwe.power_trial import TrialRecord
    TrialRecord(tmp_path).begin('GPU-test', 250000, 240000)
    backend = PowerBackend('GPU-test', tmp_path)
    assert backend.status()['trial_active']
    assert backend.start(300000, 250000) == {'ok': False, 'error': 'trial_guard_active'}
    assert backend.start(240000, 300000) == {'ok': False, 'error': 'trial_guard_active'}
    assert not backend.busy
