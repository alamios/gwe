# SPDX-License-Identifier: GPL-3.0-or-later
import importlib.util
from pathlib import Path
import subprocess

import pytest


def installer():
    path = Path(__file__).resolve().parents[1] / 'scripts/install_native.py'
    spec = importlib.util.spec_from_file_location('native_install', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dependency_plan_pins_only_reviewed_new_packages():
    assert installer().approved_dependencies(
        'Inst python3-xlib (0.33-2 Ubuntu:24.04/noble [all])\n'
        'Conf python3-xlib (0.33-2 Ubuntu:24.04/noble [all])\n'
    ) == ['python3-xlib=0.33-2']


@pytest.mark.parametrize('line', [
    'Inst nvidia-driver-615 (615.0 Ubuntu [amd64])',
    'Inst python3-xlib [0.32] (0.33-2 Ubuntu [all])',
    'Remv python3-xlib [0.33-2]',
    'Conf unrelated-package (1.0 Ubuntu [all])',
])
def test_dependency_plan_refuses_unreviewed_changes(line):
    with pytest.raises(RuntimeError):
        installer().approved_dependencies(line)


@pytest.mark.parametrize('remove_succeeds', [True, False])
def test_rollback_preserves_archive_if_package_removal_fails(tmp_path, remove_succeeds):
    module = installer()
    archive = tmp_path / 'archive'
    archive.mkdir()
    (archive / 'manual-helper').mkdir()
    (archive / 'manual-helper/entry.py').write_text('original code')
    (archive / 'manual.service').write_text('original unit')
    commands = tmp_path / 'bin'
    commands.mkdir()
    for name, body in [('systemctl', 'echo inactive'),
                       ('dpkg', 'exit ' + ('0' if remove_succeeds else '1'))]:
        path = commands / name
        path.write_text('#!/bin/sh\n' + body + '\n')
        path.chmod(0o755)
    script = module.restore_script()
    for original, replacement in [
        ('/opt/gwe-fan-service', str(tmp_path / 'restored-helper')),
        ('/etc/systemd/system/gwe-fan-service.service', str(tmp_path / 'restored.service')),
        ('/run/gwe-fan-service', str(tmp_path / 'runtime')),
        ('/run/systemd/system', str(tmp_path / 'systemd')),
    ]:
        script = script.replace(original, replacement)
    (archive / 'restore.sh').write_text(script)
    result = subprocess.run(['sh', str(archive / 'restore.sh')],
                            env={'PATH': str(commands) + ':/usr/bin:/bin'}, capture_output=True)
    assert (result.returncode == 0) == remove_succeeds
    if remove_succeeds:
        assert (tmp_path / 'restored-helper/entry.py').read_text() == 'original code'
        assert (tmp_path / 'restored.service').read_text() == 'original unit'
    else:
        assert (archive / 'manual-helper/entry.py').read_text() == 'original code'
        assert (archive / 'manual.service').read_text() == 'original unit'
        assert not (tmp_path / 'restored-helper').exists()
