# SPDX-License-Identifier: GPL-3.0-or-later
import json
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
