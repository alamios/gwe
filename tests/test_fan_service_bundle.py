# SPDX-License-Identifier: GPL-3.0-or-later
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('stage_fan_service',ROOT/'scripts/stage_fan_service.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_bundle_is_independent_and_hashes_match(tmp_path):
    destination=module.stage(tmp_path/'bundle')
    for line in (destination/'SHA256SUMS').read_text().splitlines():
        expected,name=line.split('  ',1)
        path=destination/name
        assert not path.is_symlink()
        assert hashlib.sha256(path.read_bytes()).hexdigest()==expected
    assert (destination/'lib/pynvml.py').read_text().startswith('#####\n# Copyright')
    assert not (destination/'lib/gwe/di.py').exists()
    assert '"allowed_uid": 0' in (destination/'config.example.json').read_text()
    assert not any(path.suffix=='.db' for path in destination.rglob('*'))
    for script in ('install.sh','uninstall.sh'):
        subprocess.run(['sh','-n',str(destination/script)],check=True)
    code='import sys; sys.path.insert(0,sys.argv[1]); import gwe.fan_daemon, pynvml; print("imports-only")'
    result=subprocess.run([sys.executable,'-I','-B','-c',code,str(destination/'lib')],capture_output=True,text=True,check=True)
    assert result.stdout.strip()=='imports-only'


def test_staging_refuses_existing_destination(tmp_path):
    with pytest.raises(FileExistsError):module.stage(tmp_path)


def test_unit_has_no_boot_enablement_or_restart_loop():
    unit=(ROOT/'data/fan-service/gwe-fan-service.service').read_text()
    assert '\n[Install]' not in unit
    assert 'Restart=no' in unit
    assert 'RuntimeMaxSec=60s' in unit
    assert 'KillMode=control-group' in unit
    assert 'ExecStopPost=' in unit
    assert 'WatchdogSec=10s' in unit


@pytest.mark.parametrize('existing',['code','unit','config','symlink'])
def test_installer_refuses_existing_artifacts_before_any_mutation(tmp_path,existing):
    import os
    targets={'code':tmp_path/'opt/gwe-fan-service','unit':tmp_path/'etc/systemd/system/gwe-fan-service.service',
             'config':tmp_path/'etc/gwe-fan-service.json'}
    for target in targets.values():target.parent.mkdir(parents=True,exist_ok=True)
    target=targets.get(existing,targets['code'])
    if existing=='symlink':target.symlink_to(tmp_path/'absent')
    else:target.write_text('keep')
    script=(ROOT/'data/fan-service/install.sh').read_text()
    # Redirect every installation path into this disposable test tree.
    script=script.replace('/opt/gwe-fan-service',str(targets['code']))
    script=script.replace('/etc/systemd/system/gwe-fan-service.service',str(targets['unit']))
    script=script.replace('/etc/gwe-fan-service.json',str(targets['config']))
    executable=tmp_path/'install.sh';executable.write_text(script)
    commands=tmp_path/'bin';commands.mkdir()
    for name,body in {'id':'echo 0','sha256sum':'exit 0','install':'exit 99','systemctl':'exit 99'}.items():
        command=commands/name;command.write_text('#!/bin/sh\n'+body+'\n');command.chmod(0o755)
    result=subprocess.run(['sh',str(executable)],env={**os.environ,'PATH':str(commands)+':'+os.environ['PATH']},capture_output=True,text=True)
    assert result.returncode==1
    assert 'refusing overwrite' in result.stdout
    if existing=='symlink':assert target.is_symlink()
    else:assert target.read_text()=='keep'
