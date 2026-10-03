# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise the unified package's emitted socket activation maintainer guards."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_builder(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'scripts'))
    spec = importlib.util.spec_from_file_location('activation_guard_builder', ROOT / 'scripts/build_debs.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def unified_scripts(tmp_path_factory):
    if shutil.which('dpkg-deb') is None:
        pytest.skip('Unified maintainer scripts are emitted by the native package builder')
    from _pytest.monkeypatch import MonkeyPatch

    monkeypatch = MonkeyPatch()
    try:
        module = load_builder(monkeypatch)

        def stage(destination):
            destination = Path(destination)
            destination.mkdir(parents=True)
            for name in ('install.sh', 'update.sh', 'uninstall.sh', 'SHA256SUMS', 'entry.py'):
                (destination / name).write_text('fixture\n')
            (destination / 'gwe-fan-service.service').write_text(
                '[Service]\nExecStart=/usr/bin/python3 entry.py run\n'
                'RuntimeMaxSec=60s\nTimeoutStartSec=10s\nTimeoutStopSec=25s\n'
                'KillMode=control-group\n')
            return destination

        def resources(application, destination):
            destination = Path(destination)
            destination.mkdir(parents=True, exist_ok=True)
            for name in ('com.leinardi.gwe.gresource', 'com.leinardi.gwe.gschema.xml', 'gschemas.compiled'):
                (destination / name).write_text('fixture\n')
            return destination / 'com.leinardi.gwe.gresource'

        monkeypatch.setattr(module, 'stage', stage)
        monkeypatch.setattr(module, 'vendor', lambda path: module.write(path / 'BUNDLED_VERSIONS', 'fixture\n'))
        monkeypatch.setattr(module, 'prepare_resources', resources)
        destination = tmp_path_factory.mktemp('unified-guard-build') / 'package'
        module.build(destination, '1.0.0~guardtest', 1700000000)
        tree = destination / 'package-tree' / 'DEBIAN'
        return {name: tree / name for name in ('preinst', 'prerm')}
    finally:
        monkeypatch.undo()


@pytest.fixture
def sandbox(tmp_path):
    runtime = tmp_path / 'run/gwe-fan-service'
    runtime.mkdir(parents=True)
    systemd = tmp_path / 'run/systemd/system'
    systemd.mkdir(parents=True)
    helper = tmp_path / 'opt/gwe-fan-service'
    helper.parent.mkdir(parents=True)
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    log = tmp_path / 'commands.log'
    script = bindir / 'systemctl'
    script.write_text('''#!/bin/sh
set -eu
printf '%s\\n' "$*" >> "$COMMAND_LOG"
if [ "$1" = show ]; then
    case "$2" in
        gwe-fan-service.service)
            count=0
            [ ! -f "$SERVICE_SHOW_COUNT" ] || count=$(cat "$SERVICE_SHOW_COUNT")
            count=$((count + 1))
            printf '%s\\n' "$count" > "$SERVICE_SHOW_COUNT"
            if [ "$count" -gt 1 ] && [ "${ACTIVE_AFTER_STOP:-0}" = 1 ]; then
                echo active
            else
                echo inactive
            fi
            ;;
        gwe-fan-service.socket) echo loaded ;;
        *) exit 2 ;;
    esac
elif [ "$1" = stop ] && [ "$2" = gwe-fan-service.socket ]; then
    if [ "${PENDING_AFTER_STOP:-0}" = 1 ]; then
        ln -s missing-target "$RUNTIME/owned.json"
    fi
    [ "${STOP_FAIL:-0}" != 1 ] || exit 1
else
    exit 2
fi
''')
    script.chmod(0o755)
    query = bindir / 'dpkg-query'
    query.write_text('#!/bin/sh\nexit 1\n')
    query.chmod(0o755)
    return {'root': tmp_path, 'runtime': runtime, 'systemd': systemd, 'helper': helper,
            'bindir': bindir, 'log': log}


def emitted_script(path, sandbox):
    text = path.read_text()
    text = text.replace('/run/gwe-fan-service', str(sandbox['runtime']))
    text = text.replace('/run/systemd/system', str(sandbox['systemd']))
    text = text.replace('/opt/gwe-fan-service', str(sandbox['helper']))
    target = sandbox['root'] / path.name
    target.write_text(text)
    target.chmod(0o755)
    return target


def invoke(script, sandbox, *arguments, **settings):
    environment = dict(os.environ, PATH=str(sandbox['bindir']) + ':/usr/bin:/bin',
                       COMMAND_LOG=str(sandbox['log']), RUNTIME=str(sandbox['runtime']),
                       SERVICE_SHOW_COUNT=str(sandbox['root'] / 'service-show-count'))
    environment.update({key: str(value) for key, value in settings.items()})
    return subprocess.run([str(script), *arguments], env=environment, capture_output=True, text=True)


@pytest.mark.parametrize('maintainer_script,args', [('preinst', ('install',)), ('prerm', ('remove',))])
def test_socket_stop_failure_blocks_package_operation(unified_scripts, sandbox, maintainer_script, args):
    script = emitted_script(unified_scripts[maintainer_script], sandbox)
    result = invoke(script, sandbox, *args, STOP_FAIL=1)
    assert result.returncode != 0
    assert 'stop gwe-fan-service.socket' in sandbox['log'].read_text()


@pytest.mark.parametrize('maintainer_script,args', [('preinst', ('install',)), ('prerm', ('remove',))])
def test_service_activated_during_socket_quiesce_is_caught_on_recheck(
        unified_scripts, sandbox, maintainer_script, args):
    script = emitted_script(unified_scripts[maintainer_script], sandbox)
    result = invoke(script, sandbox, *args, ACTIVE_AFTER_STOP=1)
    assert result.returncode != 0
    assert sandbox['log'].read_text().count('show gwe-fan-service.service') == 2


@pytest.mark.parametrize('maintainer_script,args', [('preinst', ('install',)), ('prerm', ('remove',))])
def test_broken_recovery_marker_symlink_blocks_quiesce(unified_scripts, sandbox, maintainer_script, args):
    script = emitted_script(unified_scripts[maintainer_script], sandbox)
    (sandbox['runtime'] / 'owned.json').symlink_to('missing-target')
    result = invoke(script, sandbox, *args)
    assert result.returncode != 0
    assert 'stop gwe-fan-service.socket' not in sandbox['log'].read_text()


@pytest.mark.parametrize('maintainer_script,args', [('preinst', ('install',)), ('prerm', ('remove',))])
def test_pending_recovery_appearing_during_quiesce_is_caught_on_recheck(
        unified_scripts, sandbox, maintainer_script, args):
    script = emitted_script(unified_scripts[maintainer_script], sandbox)
    result = invoke(script, sandbox, *args, PENDING_AFTER_STOP=1)
    assert result.returncode != 0
    assert 'stop gwe-fan-service.socket' in sandbox['log'].read_text()
    assert (sandbox['runtime'] / 'owned.json').is_symlink()
