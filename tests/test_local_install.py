# SPDX-License-Identifier: GPL-3.0-or-later
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture(tmp_path):
    source = tmp_path / 'source'
    (source / 'gwe').mkdir(parents=True)
    (source / 'gwe/__init__.py').write_text('version = 1\n')
    (source / 'data').mkdir()
    (source / 'data/resource').write_text('resource')
    (source / 'COPYING.txt').write_text('License')
    (source / 'scripts').mkdir()
    for name in (*load('install_local').SCRIPTS, 'launch_local.py'):
        (source / 'scripts' / name).write_text('public source')
    (source / 'build').mkdir()
    (source / 'build/private.db').write_text('private')
    backup = tmp_path / 'private backup.db'
    backup.write_text('unchanged backup')
    return source, backup, tmp_path / 'install', tmp_path / 'applications'


def test_snapshot_update_rollback_and_private_configuration(tmp_path):
    source, backup, prefix, apps = fixture(tmp_path)
    installer = load('install_local')
    installer.install(prefix, apps, sys.executable, backup, source=source)
    first = (prefix / 'current').resolve()
    assert not list(first.rglob('*.db'))
    assert (prefix / 'config.json').stat().st_mode & 0o777 == 0o600
    assert json.loads((prefix / 'config.json').read_text())['database'] == str(backup)
    (prefix / 'state').mkdir()
    (prefix / 'state/log').write_text('retained')
    (source / 'gwe/__init__.py').write_text('version = 2\n')
    installer.install(prefix, apps, sys.executable, backup, source=source)
    second = (prefix / 'current').resolve()
    assert second != first and (prefix / 'previous').resolve() == first
    installer.install(prefix, apps, rollback=True)
    assert (prefix / 'current').resolve() == first
    assert (prefix / 'previous').resolve() == second
    assert (prefix / 'state/log').read_text() == 'retained'
    assert backup.read_text() == 'unchanged backup'
    assert 'Terminal=true' in (apps / 'gwe-nvml-local.desktop').read_text()


def test_changed_snapshot_refuses_reuse(tmp_path):
    source, backup, prefix, apps = fixture(tmp_path)
    installer = load('install_local')
    installer.install(prefix, apps, sys.executable, backup, source=source)
    (prefix / 'current/gwe/__init__.py').write_text('changed')
    with pytest.raises(RuntimeError, match='changed'):
        installer.install(prefix, apps, sys.executable, backup, source=source)


def test_corrupt_previous_snapshot_blocks_rollback_without_switching(tmp_path):
    source, backup, prefix, apps = fixture(tmp_path)
    installer = load('install_local')
    installer.install(prefix, apps, sys.executable, backup, source=source)
    first = (prefix / 'current').resolve()
    (source / 'gwe/__init__.py').write_text('version = 2\n')
    installer.install(prefix, apps, sys.executable, backup, source=source)
    current = (prefix / 'current').resolve()
    (first / 'gwe/__init__.py').write_text('corrupted')
    with pytest.raises(RuntimeError, match='changed'):
        installer.install(prefix, apps, rollback=True)
    assert (prefix / 'current').resolve() == current


def test_unrecognized_directory_is_preserved(tmp_path):
    source, backup, prefix, apps = fixture(tmp_path)
    prefix.mkdir()
    (prefix / 'keep').write_text('keep')
    with pytest.raises(RuntimeError, match='unrecognized'):
        load('install_local').install(prefix, apps, sys.executable, backup, source=source)
    assert (prefix / 'keep').read_text() == 'keep'


@pytest.mark.parametrize('names,apps', [(['com.leinardi.gwe'], []),
                                      (['com.leinardi.gwe.ServiceTrial'], []),
                                      ([], ['com.leinardi.gwe'])])
def test_competing_controller_blocked(names, apps):
    with pytest.raises(RuntimeError, match='Close'):
        load('check_controllers').check(names, apps)


def test_read_only_monitor_does_not_block():
    load('check_controllers').check(['com.leinardi.gwe.Monitor'], [])


def test_installed_launcher_uses_snapshot_and_shared_state(tmp_path, monkeypatch):
    source, backup, prefix, apps = fixture(tmp_path)
    load('install_local').install(prefix, apps, sys.executable, backup, source=source)
    launcher = load('launch_local')
    monkeypatch.setattr(launcher, '__file__', str(prefix / 'launch.py'))
    calls = []
    monkeypatch.setattr(launcher.os, 'execve', lambda *args: calls.append(args))
    launcher.main()
    command, argv, environment = calls[0]
    assert command == '/bin/bash' and argv[-1] == '--installed'
    assert argv[1].startswith(str((prefix / 'current').resolve()))
    assert environment['GWE_STATE_HOME'] == str(prefix / 'state')


def test_launcher_rejects_release_outside_installation(tmp_path, monkeypatch):
    prefix = tmp_path / 'install'
    prefix.mkdir()
    (prefix / 'config.json').write_text('{"version": 1}')
    (prefix / 'current').symlink_to(tmp_path)
    launcher = load('launch_local')
    monkeypatch.setattr(launcher, '__file__', str(prefix / 'launch.py'))
    with pytest.raises(RuntimeError, match='Invalid'):
        launcher.main()


def test_shared_state_survives_source_location_change(tmp_path, monkeypatch):
    state = tmp_path / 'state'
    monkeypatch.setenv('GWE_STATE_HOME', str(state))
    assert load('run_monitor').prepare_environment(tmp_path / 'one') == state / 'monitor'
    assert load('run_monitor').prepare_environment(tmp_path / 'two') == state / 'monitor'
