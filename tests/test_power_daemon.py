# SPDX-License-Identifier: GPL-3.0-or-later
"""Recovery dispatch must attempt all independent journals even after failure."""
from pathlib import Path

from gwe import fan_daemon
from gwe.power_process import PowerBackend


def test_post_stop_attempts_fan_power_and_trial_recovery_after_fan_error(tmp_path, monkeypatch):
    monkeypatch.setattr(fan_daemon, 'RUNTIME', tmp_path)
    monkeypatch.setattr(fan_daemon, 'trusted', lambda path: Path(path))
    monkeypatch.setattr(fan_daemon.os, 'geteuid', lambda: 0)
    calls = []
    def fans(path):
        calls.append('fans')
        raise RuntimeError('Simulated fan error')
    def power(trial=False):
        calls.append('trial' if trial else 'power')
    monkeypatch.setattr(fan_daemon, 'recover_record', fans)
    monkeypatch.setattr(fan_daemon, 'recover_power_record', power)
    assert fan_daemon.main(['recover']) == 1
    assert calls == ['fans', 'power', 'trial']


def test_no_power_journal_means_no_nvml_or_process_start(tmp_path, monkeypatch):
    monkeypatch.setattr(fan_daemon, 'RUNTIME', tmp_path)
    def forbidden():
        raise AssertionError('Unexpected hardware access')
    monkeypatch.setattr(fan_daemon, 'nvml_factory', forbidden)
    fan_daemon.recover_power_record()
    fan_daemon.recover_power_record(trial=True)


def test_unkillable_power_worker_latches_fault_without_blocking(tmp_path):
    now = [0]
    class Process:
        kills = 0
        def is_alive(self):
            return True
        def kill(self):
            self.kills += 1
    backend = PowerBackend('GPU-test', tmp_path, clock=lambda: now[0])
    backend.process = Process()
    backend.deadline = 1
    now[0] = 1
    backend.poll()
    assert backend.process.kills == 1
    now[0] = 4
    backend.poll()
    assert backend.result == {'state': 'fault', 'error': 'worker_stuck'}
    assert backend.process.kills == 1
