# SPDX-License-Identifier: GPL-3.0-or-later
"""Continuous launcher checks redirect all privileged paths and commands."""
import os
from pathlib import Path
import subprocess

import pytest

from test_power_trial_client import make_wrapper_commands, make_wrapper_fixture

ROOT = Path(__file__).resolve().parents[1]


def run_session(tmp_path, *, installed=False, old_backup=False, override_exists=False, **extra):
    root, _, bundle, code, runtime = make_wrapper_fixture(tmp_path)
    bindir, _, python = make_wrapper_commands(tmp_path)
    installed_python = bindir / 'installed-python'
    installed_python.write_text(installed_python.read_text().replace(
        'recover)\n', 'recover)\n'
        '        if [ "${FAIL_FINAL_RECOVER:-0}" = 1 ]; then\n'
        '            if [ -f "$TRIAL_RUNTIME/recovered-once" ]; then exit 44; fi\n'
        '            touch "$TRIAL_RUNTIME/recovered-once"\n'
        '        fi\n'))
    installed_python.write_text(installed_python.read_text().replace(
        '    recover)\n', '    prepare-session) touch "$TRIAL_RUNTIME/session.json"; exit 0 ;;\n    recover)\n').replace(
        'rm -f "$TRIAL_RUNTIME/owned.json"', 'rm -f "$TRIAL_RUNTIME/session.json" "$TRIAL_RUNTIME/owned.json"'))
    sudo = bindir / 'sudo'
    sudo.write_text(sudo.read_text().replace('exec "$@"', 'if [ "$1" = -n ]; then shift; fi\nexec "$@"'))
    override_root = tmp_path / 'runtime-systemd'
    script = (ROOT / 'scripts/run_control_session.sh').read_text()
    script = script.replace('/opt/gwe-fan-service', str(code))
    script = script.replace('/run/gwe-fan-service', str(runtime))
    script = script.replace('/run/systemd/system', str(override_root))
    script = script.replace('/usr/bin/python3', str(bindir / 'installed-python'))
    wrapper = root / 'scripts/run_control_session.sh'
    wrapper.write_text(script)
    backup = tmp_path / 'backup.db'
    backup.write_text('unchanged private test backup')
    (bundle / 'continuous.conf').write_text('[Service]\n')
    (code / 'continuous.conf').write_text('[Service]\n')
    previous = code.with_name(code.name + '.previous')
    if old_backup:
        previous.mkdir()
        (previous / 'keep').write_text('older rollback')
    override = override_root / 'gwe-fan-service.service.d/90-gwe-continuous.conf'
    if override_exists:
        override.parent.mkdir(parents=True)
        override.write_text('existing session')
    (bindir / 'systemctl').write_text('''#!/bin/sh
echo "systemctl $*" >> "$TRIAL_LOG"
case "$1" in
 show) echo "${UNIT_STATE:-inactive}" ;;
 is-active) [ "${COOLER_ACTIVE:-1}" = 1 ] ;;
 reset-failed)
    if [ "${UNIT_STATE:-inactive}" != failed ]; then
        echo 'Unit not loaded' >&2; exit 1
    fi ;;
 stop|start|daemon-reload) exit 0 ;;
 *) exit 91 ;;
esac
''')
    (bindir / 'install').write_text('''#!/bin/bash
if [ "$1" = -d ]; then mkdir -p "${@: -1}"; else cp "${@: -2:1}" "${@: -1}"; fi
''')
    python.write_text('''#!/bin/sh
echo "gui_args $*" >> "$TRIAL_LOG"
exit "${TRIAL_EXIT:-0}"
''')
    log = tmp_path / 'session.log'
    result = subprocess.run(['bash', str(wrapper), str(python), str(backup),
                             '--installed' if installed else str(bundle)],
                            env={**os.environ, 'PATH': f'{bindir}:{os.environ["PATH"]}',
                                 'TRIAL_LOG': str(log), 'TRIAL_RUNTIME': str(runtime), **extra},
                            capture_output=True, text=True)
    return result, log.read_text(), backup, override, code


@pytest.mark.parametrize('installed', [False, True])
def test_launch_and_close_restore_original_unit_and_cooler(tmp_path, installed):
    result, log, backup, override, code = run_session(tmp_path, installed=installed)
    assert result.returncode == 0, result.stderr
    assert '--allow-control --allow-power-control --continuous' in log
    assert f'--database {backup}' in log
    assert backup.read_text() == 'unchanged private test backup'
    assert not override.exists()
    assert log.index('stop coolercontrold') < log.index('gui_args')
    assert log.index('gui_args') < log.rindex('entry recover') < log.index('start coolercontrold')
    assert ('\nupdate\n' in '\n' + log) == (not installed)


def test_gui_failure_still_recovers_and_removes_override(tmp_path):
    result, log, _, override, _ = run_session(tmp_path, TRIAL_EXIT='17')
    assert result.returncode == 17
    assert not override.exists()
    assert 'entry recover' in log and 'start coolercontrold' in log


def test_cooler_initially_stopped_is_not_started(tmp_path):
    result, log, _, _, _ = run_session(tmp_path, COOLER_ACTIVE='0')
    assert result.returncode == 0
    assert 'start coolercontrold' not in log


def test_recovery_failure_does_not_launch_gui_or_restart_cooler(tmp_path):
    result, log, _, override, _ = run_session(tmp_path, FAIL_RECOVER='1')
    assert result.returncode != 0
    assert 'gui_args' not in log and 'start coolercontrold' not in log
    assert not override.exists()


def test_failed_final_recovery_keeps_cooler_stopped_and_retains_override(tmp_path):
    result, log, _, override, _ = run_session(tmp_path, FAIL_FINAL_RECOVER='1')
    assert result.returncode != 0
    assert 'gui_args' in log and 'start coolercontrold' not in log
    assert override.exists()
    assert 'Cleanup not verified' in result.stdout


def test_old_rollback_copy_is_archived_without_deletion(tmp_path):
    result, log, _, _, code = run_session(tmp_path, old_backup=True)
    assert result.returncode == 0, result.stderr
    archives = list(code.parent.glob('gwe-fan-service.previous.*'))
    assert len(archives) == 1 and (archives[0] / 'keep').read_text() == 'older rollback'


def test_existing_runtime_override_is_preserved_and_refuses_launch(tmp_path):
    result, log, _, override, _ = run_session(tmp_path, override_exists=True)
    assert result.returncode != 0
    assert override.read_text() == 'existing session'
    assert 'gui_args' not in log


def test_continuous_override_retains_watchdog_and_no_boot_enablement():
    override = (ROOT / 'data/fan-service/continuous.conf').read_text()
    unit = (ROOT / 'data/fan-service/gwe-fan-service.service').read_text()
    assert 'run --continuous' in override and 'RuntimeMaxSec=infinity' in override
    assert 'KillMode=mixed' in override
    assert 'ReadWritePaths=/run/systemd/system/gwe-fan-service.service.d' in override
    assert 'WatchdogSec=10s' in unit and 'ExecStopPost=' in unit
    assert '[Install]' not in override


@pytest.mark.parametrize('state', ['inactive', 'failed'])
def test_only_failed_units_are_reset_after_recovery(tmp_path, state):
    result, log, _, _, _ = run_session(tmp_path, UNIT_STATE=state)
    assert result.returncode == 0, result.stderr
    assert ('systemctl reset-failed' in log) == (state == 'failed')
    assert 'gui_args' in log
