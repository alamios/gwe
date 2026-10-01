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
