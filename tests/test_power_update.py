# SPDX-License-Identifier: GPL-3.0-or-later
"""Power/fan service updater tests using redirected paths and command doubles."""
import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
UPDATE = ROOT / 'data/fan-service/update.sh'


def make_update_tree(tmp_path):
    """Copy the updater inputs into a disposable tree and redirect fixed paths."""
    bundle = tmp_path / 'bundle'
    (bundle / 'lib/gwe').mkdir(parents=True)
    for name in ('fan_curve', 'fan_service', 'fan_process', 'fan_daemon',
                 'desktop_activation', 'native_setup',
                 'nvml_fan_control', 'nvml_power', 'power_process', 'power_trial', '__init__'):
        (bundle / f'lib/gwe/{name}.py').write_text(f'# new {name}\n')
    (bundle / 'lib/pynvml.py').write_text('# fake vendored binding\n')
    for name in ('entry.py', 'COPYING.txt', 'BINDING_VERSION', 'uninstall.sh'):
        (bundle / name).write_text('# update input\n')
    (bundle / 'SHA256SUMS').write_text('')
    (bundle / 'gwe-fan-service.service').write_text('new service unit\n')

    paths = {
        'code': tmp_path / 'opt/gwe-fan-service',
        'unit': tmp_path / 'etc/systemd/system/gwe-fan-service.service',
        'config': tmp_path / 'etc/gwe-fan-service.json',
        'runtime': tmp_path / 'run/gwe-fan-service',
    }
    for key in ('unit', 'config'):
        paths[key].parent.mkdir(parents=True, exist_ok=True)
    paths['runtime'].mkdir(parents=True)
    paths['code'].mkdir(parents=True)
    (paths['code'] / 'old-code.txt').write_text('old code\n')
    paths['unit'].write_text('old service unit\n')
    paths['config'].write_text('{"gpu_uuid":"GPU-test"}\n')
    # Exercise the entry point's final-location requirement, which an empty
    # entry stub previously missed. The real entry additionally requires root.
    (bundle / 'entry.py').write_text(
        'import os\nfrom pathlib import Path\n'
        f'assert Path(__file__).parent == Path({str(paths["code"])!r}), "Wrong installation path"\n'
        'if os.environ.get("UPDATE_FAIL_CHECK") == "1":\n'
        '    raise SystemExit(74)\n')

    script = UPDATE.read_text()
    script = script.replace('/opt/gwe-fan-service', str(paths['code']))
    script = script.replace('/etc/systemd/system/gwe-fan-service.service', str(paths['unit']))
    script = script.replace('/etc/gwe-fan-service.json', str(paths['config']))
    script = script.replace('/run/gwe-fan-service', str(paths['runtime']))
    updater = bundle / 'update.sh'
    updater.write_text(script)
    return bundle, updater, paths


def mock_commands(tmp_path):
    bindir = tmp_path / 'mock-bin'
    bindir.mkdir()

    commands = {
        'id': '#!/bin/sh\necho 0\n',
        'sha256sum': '#!/bin/sh\nexit 0\n',
        'systemctl': '''#!/bin/sh
if [ "$1" = show ]; then
    echo "${UPDATE_ACTIVE_STATE:-inactive}"
    exit 0
fi
if [ "$1" = daemon-reload ]; then
    exit 0
fi
exit 90
''',
        'install': '''#!/usr/bin/python3
import os
from pathlib import Path
import shutil
import sys

args = sys.argv[1:]
directory = False
mode = None
positional = []
index = 0
while index < len(args):
    arg = args[index]
    if arg == '-d':
        directory = True
    elif arg in ('-o', '-g'):
        index += 1
    elif arg == '-m':
        index += 1
        mode = int(args[index], 8)
    else:
        positional.append(arg)
    index += 1

target = Path(positional[-1])
if os.environ.get('UPDATE_FAIL_UNIT') == '1' and target == Path(os.environ['UPDATE_UNIT_PATH']):
    raise SystemExit(73)
if directory:
    target.mkdir(parents=True, exist_ok=True)
else:
    source = Path(positional[0])
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    if mode is not None:
        target.chmod(mode)
''',
    }
    for name, body in commands.items():
        path = bindir / name
        path.write_text(body)
        path.chmod(0o755)
    return bindir


def run_update(updater, bindir, paths, **extra_env):
    env = {
        **os.environ,
        'PATH': f'{bindir}:{os.environ["PATH"]}',
        'UPDATE_UNIT_PATH': str(paths['unit']),
        **extra_env,
    }
    return subprocess.run(['sh', str(updater)], cwd=updater.parent, env=env,
                          capture_output=True, text=True)


@pytest.mark.parametrize('refusal', ['active', 'owned', 'power_pending', 'previous'])
def test_update_refuses_active_or_recovery_state_without_mutation(tmp_path, refusal):
    _, updater, paths = make_update_tree(tmp_path)
    bindir = mock_commands(tmp_path)
    if refusal in ('owned', 'power_pending'):
        (paths['runtime'] / ('owned.json' if refusal == 'owned' else 'power-pending.json')).write_text('pending')
    elif refusal == 'previous':
        previous = paths['code'].with_name(paths['code'].name + '.previous')
        previous.mkdir()
        (previous / 'retain.txt').write_text('rollback review required')

    result = run_update(updater, bindir, paths,
                        UPDATE_ACTIVE_STATE='active' if refusal == 'active' else 'inactive')

    assert result.returncode != 0
    assert (paths['code'] / 'old-code.txt').read_text() == 'old code\n'
    assert paths['unit'].read_text() == 'old service unit\n'
    assert paths['config'].read_text() == '{"gpu_uuid":"GPU-test"}\n'
    assert not paths['code'].with_name(paths['code'].name + '.next').exists()
    if refusal == 'previous':
        assert (paths['code'].with_name(paths['code'].name + '.previous') / 'retain.txt').exists()
    if refusal in ('owned', 'power_pending'):
        marker_name = 'owned.json' if refusal == 'owned' else 'power-pending.json'
        assert (paths['runtime'] / marker_name).read_text() == 'pending'


def test_update_preserves_config_and_retains_old_code_and_unit(tmp_path):
    _, updater, paths = make_update_tree(tmp_path)
    bindir = mock_commands(tmp_path)
    original_config = paths['config'].read_bytes()

    result = run_update(updater, bindir, paths)

    assert result.returncode == 0, result.stderr
    assert paths['config'].read_bytes() == original_config
    assert (paths['code'] / 'lib/gwe/nvml_power.py').read_text() == '# new nvml_power\n'
    previous = paths['code'].with_name(paths['code'].name + '.previous')
    assert (previous / 'old-code.txt').read_text() == 'old code\n'
    assert (previous / 'unit.before-update').read_text() == 'old service unit\n'
    assert paths['unit'].read_text() == 'new service unit\n'
    assert not paths['code'].with_name(paths['code'].name + '.next').exists()
    assert 'not started or enabled' in result.stdout


@pytest.mark.parametrize('failure', ['UPDATE_FAIL_UNIT', 'UPDATE_FAIL_CHECK'])
def test_update_rolls_back_code_and_unit_after_post_swap_failure(tmp_path, failure):
    _, updater, paths = make_update_tree(tmp_path)
    bindir = mock_commands(tmp_path)
    original_config = paths['config'].read_bytes()

    result = run_update(updater, bindir, paths, **{failure: '1'})

    assert result.returncode != 0
    assert (paths['code'] / 'old-code.txt').read_text() == 'old code\n'
    assert not (paths['code'] / 'lib/gwe/nvml_power.py').exists()
    assert paths['unit'].read_text() == 'old service unit\n'
    assert paths['config'].read_bytes() == original_config
    assert not paths['code'].with_name(paths['code'].name + '.previous').exists()
    assert not paths['code'].with_name(paths['code'].name + '.next').exists()
