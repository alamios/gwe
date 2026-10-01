# SPDX-License-Identifier: GPL-3.0-or-later
"""Recovery runner tests replace all system and GPU boundaries."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest


@pytest.fixture
def runner(monkeypatch, tmp_path):
    scripts = Path(__file__).resolve().parents[1] / 'scripts'
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location('recovery_runner', scripts / 'power_recovery_trial.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'RUNTIME', tmp_path)
    return module


def test_both_faults_are_verified_before_next_guard(runner, monkeypatch):
    events = []
    monkeypatch.setattr(runner.trial, 'main', lambda **kw: events.append(('hold', kw)) or 'GPU-test')
    monkeypatch.setattr(runner, 'command', lambda *args: events.append(args))
    monkeypatch.setattr(runner, 'wait_for_stop', lambda *args: events.append(('verify', *args)))
    runner.main()
    assert events[0] == ('hold', {'hold': True})
    assert '--signal=SIGKILL' in events[1]
    assert events[2] == ('verify', 'signal', 'GPU-test')
    assert events[3][-1] == 'prepare-power-trial'
    assert events[4][2] == 'reset-failed'
    assert events[5][2] == 'start'
    assert events[6] == ('hold', {'hold': True})
    assert '--signal=SIGSTOP' in events[7]
    assert events[8] == ('verify', 'watchdog', 'GPU-test')


def test_failed_first_recovery_prevents_second_write(runner, monkeypatch):
    events = []
    monkeypatch.setattr(runner.trial, 'main', lambda **kw: events.append('apply') or 'GPU-test')
    monkeypatch.setattr(runner, 'command', lambda *args: events.append(args))
    def failed(*args):
        raise RuntimeError('Recovery failed')
    monkeypatch.setattr(runner, 'wait_for_stop', failed)
    with pytest.raises(RuntimeError):
        runner.main()
    assert events.count('apply') == 1
    assert len(events) == 2


def test_failed_apply_does_not_inject_fault(runner, monkeypatch):
    def failed(**kwargs):
        raise RuntimeError('Apply failed')
    monkeypatch.setattr(runner.trial, 'main', failed)
    monkeypatch.setattr(runner, 'command', lambda *args: pytest.fail('No signal after failed apply'))
    with pytest.raises(RuntimeError):
        runner.main()


@pytest.mark.parametrize('result', ['signal', 'watchdog', 'success'])
def test_stop_result_must_match_before_recovery_claim(runner, monkeypatch, result):
    monkeypatch.setattr(runner, 'command', lambda *args: 'failed' if 'ActiveState' in args else result)
    checked = []
    monkeypatch.setattr(runner, 'verify_recovery', lambda uuid: checked.append(uuid))
    if result == 'watchdog':
        runner.wait_for_stop('watchdog', 'GPU-test')
        assert checked == ['GPU-test']
    else:
        with pytest.raises(RuntimeError, match='Unexpected service'):
            runner.wait_for_stop('watchdog', 'GPU-test')
        assert not checked


def test_stalled_stop_has_bounded_deadline(runner, monkeypatch):
    monkeypatch.setattr(runner, 'command', lambda *args: 'active')
    now = [0]
    def sleep(seconds):
        now[0] += seconds
    with pytest.raises(RuntimeError, match='in time'):
        runner.wait_for_stop('watchdog', 'GPU-test', clock=lambda: now[0], sleep=sleep)
    assert 25 <= now[0] < 26


@pytest.mark.parametrize('marker', ['owned.json', 'power-pending.json', 'power-trial.json'])
def test_remaining_marker_blocks_verified_recovery(runner, marker):
    (runner.RUNTIME / marker).touch()
    with pytest.raises(RuntimeError, match='record remains'):
        runner.verify_recovery('GPU-test')


@pytest.mark.parametrize('identity,power,policies', [
    ('GPU-test', 250000, (0, 0)), ('GPU-other', 250000, (0, 0)),
    ('GPU-test', 240000, (0, 0)), ('GPU-test', 250000, (0, 1)),
])
def test_independent_reads_require_same_gpu_baseline_and_automatic_fans(
        runner, monkeypatch, identity, power, policies):
    monkeypatch.setattr(runner.trial, 'reading', lambda uuid: (identity, power))
    fake = SimpleNamespace(nvmlInit=lambda: None, nvmlShutdown=lambda: None,
                           nvmlDeviceGetHandleByUUID=lambda uuid: uuid,
                           nvmlDeviceGetNumFans=lambda handle: 2,
                           nvmlDeviceGetFanControlPolicy_v2=lambda handle, fan: policies[fan])
    monkeypatch.setitem(sys.modules, 'pynvml', fake)
    if identity == 'GPU-test' and power == 250000 and policies == (0, 0):
        runner.verify_recovery('GPU-test')
    else:
        with pytest.raises(RuntimeError):
            runner.verify_recovery('GPU-test')
