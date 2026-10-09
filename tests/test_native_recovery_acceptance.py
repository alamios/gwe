# SPDX-License-Identifier: GPL-3.0-or-later
"""Reject incomplete fault recovery without calling NVML or systemd."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


def checker():
    scripts = Path(__file__).resolve().parents[1] / 'scripts'
    sys.path.insert(0, str(scripts))
    try:
        spec = importlib.util.spec_from_file_location('native_recovery_check', scripts / 'check_native_recovery.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(scripts))


def validator():
    return checker().verify_fault


@pytest.mark.parametrize('signal', ['SIGKILL', 'SIGSTOP'])
def test_injection_never_targets_post_stop_recovery(monkeypatch, signal):
    module = checker()
    calls = []
    monkeypatch.setattr(module, 'admin', lambda *args: calls.append(args))
    module.inject_fault(signal)
    assert calls == [('kill', '--kill-whom=main', f'--signal={signal}', module.UNIT)]


@pytest.mark.parametrize('active,main,control', [('active', '2', '0'), ('failed', '0', '2'),
                                             ('failed', '2', '0')])
def test_emergency_recovery_refuses_live_processes(monkeypatch, active, main, control):
    module = checker()
    monkeypatch.setattr(module, 'state', lambda unit, property='ActiveState':
                        {'ActiveState': active, 'MainPID': main, 'ControlPID': control}[property])
    monkeypatch.setattr(module.subprocess, 'run', lambda *a, **k: pytest.fail('Unexpected recovery'))
    with pytest.raises(RuntimeError, match='still running'):
        module.emergency_recover()


def test_emergency_recovery_uses_installed_helper_and_noninteractive_sudo(monkeypatch):
    module = checker()
    monkeypatch.setattr(module, 'state', lambda unit, property='ActiveState':
                        'failed' if property == 'ActiveState' else '0')
    calls = []
    monkeypatch.setattr(module.subprocess, 'run', lambda *a, **k: calls.append((a, k)))
    module.emergency_recover()
    assert calls == [((['sudo', '-n', '/usr/bin/python3', '-I', '-B',
                       '/opt/gwe-fan-service/entry.py', 'recover'],), {'check': True, 'timeout': 65})]


def test_failed_fault_check_recovers_without_reporting_acceptance(monkeypatch, capsys):
    module = checker()
    sampled = []
    recovered = []
    def readings(nvml, uuid=None):
        policies = [0, 0] if not sampled or recovered else [1, 1]
        sampled.append(policies)
        return 'synthetic', {'policies': policies, 'temperature_c': 35, 'power_mw': 250000}
    def state(unit, property='ActiveState'):
        if property in ('MainPID', 'ControlPID'):
            return '0'
        if property == 'Result':
            return 'signal'
        return 'failed' if unit == module.UNIT else 'active'
    monkeypatch.setattr(module, 'readings', readings)
    monkeypatch.setattr(module, 'state', state)
    monkeypatch.setattr(module, 'check_controllers', lambda: 0)
    monkeypatch.setattr(module, 'admin', lambda *args: None)
    monkeypatch.setattr(module.subprocess, 'Popen', lambda *a, **k: SimpleNamespace(poll=lambda: 1))
    monkeypatch.setattr(module, 'emergency_recover', lambda: recovered.append(True))
    with pytest.raises(RuntimeError, match='Native fault recovery not verified'):
        module.fault(None, 'SIGKILL', 'signal')
    assert recovered == [True] and sampled[-1] == [0, 0]
    output = capsys.readouterr().out
    assert 'Emergency recovery verified' in output and 'SIGKILL: PASS' not in output


@pytest.mark.parametrize('expected', ['signal', 'watchdog'])
def test_fault_acceptance_preserves_current_power(expected):
    validator()({'policies': [0, 0], 'power_mw': 330000}, {'policies': [0, 0], 'power_mw': 330000},
                result=expected, expected=expected, service='failed', socket='active',
                cooler_before='active', cooler_after='active')


@pytest.mark.parametrize('after,overrides', [
    ({'policies': [0, 1], 'power_mw': 330000}, {}),
    ({'policies': [], 'power_mw': 330000}, {}),
    ({'policies': [0, 0], 'power_mw': 250000}, {}),
    ({'policies': [0, 0], 'power_mw': 330000}, {'result': 'success'}),
    ({'policies': [0, 0], 'power_mw': 330000}, {'service': 'active'}),
    ({'policies': [0, 0], 'power_mw': 330000}, {'socket': 'failed'}),
    ({'policies': [0, 0], 'power_mw': 330000}, {'cooler_after': 'inactive'}),
])
def test_fault_acceptance_rejects_missing_recovery(after, overrides):
    options = dict(result='watchdog', expected='watchdog', service='failed', socket='active',
                   cooler_before='active', cooler_after='active')
    options.update(overrides)
    with pytest.raises(RuntimeError, match='not verified'):
        validator()({'policies': [0, 0], 'power_mw': 330000}, after, **options)
