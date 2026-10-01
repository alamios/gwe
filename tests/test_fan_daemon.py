# SPDX-License-Identifier: GPL-3.0-or-later
import json
from types import SimpleNamespace
from pathlib import Path

import pytest
from gwe import fan_daemon


def test_ownership_record_is_exclusive_private_and_explicitly_cleared(tmp_path):
    path=tmp_path/'owned.json'
    record=fan_daemon.OwnershipRecord(path,'GPU-test')
    record.record((0,1))
    assert path.stat().st_mode & 0o777 == 0o600
    assert json.loads(path.read_text())['fans']==[0,1]
    with pytest.raises(FileExistsError):record.record((0,1))
    record.clear()
    assert not path.exists()


@pytest.mark.parametrize('change',[
 {'allowed_uid':0},{'allowed_uid':True},{'version':True},
 {'gpu_uuid':'GPU-test'},{'power_limit':250},
])
def test_configuration_rejects_invalid_identity_or_extra_operations(tmp_path,monkeypatch,change):
    monkeypatch.setattr(fan_daemon,'trusted',lambda p:Path(p))
    config={'version':1,'allowed_uid':1000,'gpu_uuid':'GPU-00000000-0000-0000-0000-000000000001'}
    config.update(change)
    path=tmp_path/'config.json';path.write_text(json.dumps(config))
    with pytest.raises(ValueError):fan_daemon.load_config(path)


def test_check_configuration_never_initializes_nvml(tmp_path,monkeypatch):
    monkeypatch.setattr(fan_daemon,'trusted',lambda p:Path(p))
    monkeypatch.setattr(fan_daemon.os,'geteuid',lambda:0)
    monkeypatch.setattr(fan_daemon,'nvml_factory',lambda:pytest.fail('Unexpected hardware access'))
    path=tmp_path/'config.json'
    path.write_text(json.dumps({'version':1,'allowed_uid':1000,'gpu_uuid':'GPU-00000000-0000-0000-0000-000000000001'}))
    assert fan_daemon.main(['check','--config',str(path)])==0


def test_missing_record_never_initializes_nvml(tmp_path,monkeypatch):
    monkeypatch.setattr(fan_daemon,'nvml_factory',lambda:pytest.fail('Unexpected hardware access'))
    fan_daemon.recover_record(tmp_path/'absent.json')


def test_malformed_record_cannot_select_replacement(tmp_path,monkeypatch):
    monkeypatch.setattr(fan_daemon,'trusted',lambda p:Path(p))
    path=tmp_path/'owned.json';path.write_text('{"version":1,"fans":[true]}')
    with pytest.raises(ValueError):fan_daemon.recover_record(path)
    assert path.exists()


def test_trusted_rejects_symlink(tmp_path):
    original=tmp_path/'file';original.write_text('data')
    link=tmp_path/'link';link.symlink_to(original)
    with pytest.raises(ValueError):fan_daemon.trusted(link)


@pytest.mark.parametrize('continuous,steps', [(False, 1), (True, 3)])
def test_session_lifetime_keeps_watchdog_without_trial_expiry(monkeypatch, continuous, steps):
    now, notifications = [0], []
    service = SimpleNamespace(steps=0)
    def step():
        service.steps += 1
        now[0] += 61
    service.step = step
    monkeypatch.setattr(fan_daemon, 'boot_time', lambda: now[0])
    monkeypatch.setattr(fan_daemon, 'notify', notifications.append)
    fan_daemon.serve(service, SimpleNamespace(state='idle'), SimpleNamespace(result={'state': 'idle'}),
                     lambda: service.steps >= 3, continuous=continuous)
    assert service.steps == steps
    assert notifications == ['READY=1'] + ['WATCHDOG=1'] * steps


@pytest.mark.parametrize('fan,power', [('recovery_failed', 'idle'), ('idle', 'fault')])
def test_continuous_backend_fault_still_stops_service(monkeypatch, fan, power):
    monkeypatch.setattr(fan_daemon, 'notify', lambda msg: None)
    with pytest.raises(RuntimeError, match='Backend recovery failed'):
        fan_daemon.serve(SimpleNamespace(step=lambda: None), SimpleNamespace(state=fan),
                         SimpleNamespace(result={'state': power}), lambda: False, continuous=True)


def test_continuous_flag_rejected_for_configuration_check():
    with pytest.raises(SystemExit):
        fan_daemon.main(['check', '--continuous'])
