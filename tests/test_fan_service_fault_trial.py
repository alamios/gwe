# SPDX-License-Identifier: GPL-3.0-or-later
"""Fault orchestration is simulated; no real systemctl kill or driver call."""
from types import SimpleNamespace
import subprocess
import pytest
from gwe.fan_service_fault_trial import kill_and_verify


def scenario(final=None, marker=False):
    states=[{'ActiveState':'active'}, final or {'ActiveState':'failed','Result':'signal','ExecMainStatus':'9','ControlPID':'0'}]
    records=iter([True,marker]);calls=[]
    return dict(state=lambda:states.pop(0) if len(states)>1 else states[0],
                record=SimpleNamespace(exists=lambda:next(records)),snapshot=lambda:calls.append('verified'),
                command=lambda *args,**kwargs:calls.append(args[0]),sleep=lambda _:None),calls


def test_kills_only_fixed_unit_and_verifies_recovery_after_exit():
    arguments,calls=scenario()
    kill_and_verify(**arguments)
    assert calls==[['sudo','-n','systemctl','kill','--kill-whom=all','--signal=SIGKILL','gwe-fan-service.service'],'verified']


def test_marker_remaining_is_not_success():
    arguments,calls=scenario(marker=True)
    with pytest.raises(RuntimeError,match='ownership record'):kill_and_verify(**arguments)
    assert 'verified' not in calls


def test_unexpected_result_is_not_success():
    arguments,calls=scenario(final={'ActiveState':'failed','ControlPID':'0','Result':'exit-code','ExecMainStatus':'1'})
    with pytest.raises(RuntimeError,match='Unexpected'):kill_and_verify(**arguments)


def test_inactive_service_cannot_be_killed():
    arguments,calls=scenario();arguments['state']=lambda:{'ActiveState':'inactive'}
    with pytest.raises(RuntimeError,match='Active service'):kill_and_verify(**arguments)
    assert calls==[]


def test_privilege_failure_never_claims_recovery():
    arguments,calls=scenario()
    def denied(*args,**kwargs):raise subprocess.CalledProcessError(1,args[0])
    arguments['command']=denied
    with pytest.raises(subprocess.CalledProcessError):kill_and_verify(**arguments)
    assert calls==[]


def test_wait_has_bounded_deadline():
    arguments,calls=scenario(final={'ActiveState':'deactivating','ControlPID':'12'})
    now=iter([0,0,21]);arguments['clock']=lambda:next(now)
    with pytest.raises(RuntimeError,match='deadline'):kill_and_verify(**arguments)
    assert 'verified' not in calls


def watchdog_scenario(final=None, marker=False):
    arguments, calls = scenario(final=final or {
        'ActiveState': 'failed', 'Result': 'watchdog', 'ExecMainStatus': '9', 'ControlPID': '0'
    }, marker=marker)
    original_state = arguments['state']
    def state():
        return {**original_state(), 'WatchdogUSec': '10s', 'WatchdogSignal': '9',
                'KillMode': 'control-group', 'TimeoutStopUSec': '15s', 'SendSIGKILL': 'yes'}
    arguments.update(state=state, watchdog=True)
    return arguments, calls


def test_watchdog_stops_complete_unit_and_requires_watchdog_result():
    arguments, calls = watchdog_scenario()
    kill_and_verify(**arguments)
    assert calls == [['sudo', '-n', 'systemctl', 'kill', '--kill-whom=all',
                      '--signal=SIGSTOP', 'gwe-fan-service.service'], 'verified']


def test_watchdog_refuses_unexpected_configuration():
    arguments, calls = watchdog_scenario()
    original_state = arguments['state']
    arguments['state'] = lambda: {**original_state(), 'WatchdogUSec': '0'}
    with pytest.raises(RuntimeError, match='configuration'):
        kill_and_verify(**arguments)
    assert calls == []


def test_watchdog_does_not_accept_external_kill_as_success():
    arguments, calls = watchdog_scenario(final={
        'ActiveState': 'failed', 'Result': 'signal', 'ExecMainStatus': '9', 'ControlPID': '0'
    })
    with pytest.raises(RuntimeError, match='Unexpected service'):
        kill_and_verify(**arguments)
    assert 'verified' not in calls


def test_watchdog_remaining_record_is_not_success():
    arguments, calls = watchdog_scenario(marker=True)
    with pytest.raises(RuntimeError, match='ownership record'):
        kill_and_verify(**arguments)
    assert 'verified' not in calls


def test_watchdog_wait_allows_teardown_but_is_bounded():
    arguments, calls = watchdog_scenario(final={'ActiveState': 'deactivating', 'ControlPID': '12'})
    now = iter([0, 0, 25, 41])
    arguments['clock'] = lambda: next(now)
    with pytest.raises(RuntimeError, match='deadline'):
        kill_and_verify(**arguments)
    assert 'verified' not in calls
