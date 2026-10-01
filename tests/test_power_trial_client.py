# SPDX-License-Identifier: GPL-3.0-or-later
"""Power-trial client and wrapper checks with simulated boundaries."""
import importlib.util
import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_trial_client():
    spec = importlib.util.spec_from_file_location(
        'power_service_trial', ROOT / 'scripts/power_service_trial.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeClient:
    def __init__(self, response_fn):
        self.response_fn = response_fn
        self.calls = []
        self.closed = 0

    def request(self, operation, **fields):
        self.calls.append((operation, fields))
        return self.response_fn(operation, fields)

    def close(self):
        self.closed += 1


class FakeNvmlBackend:
    def __init__(self, harness):
        self.harness = harness

    def read_snapshot(self, uuid=None):
        self.harness.read_uuids.append(uuid)
        return {'gpus': [{
            'uuid': {'value': self.harness.gpu_uuid},
            'power_limit_w': {'value': self.harness.current_mw / 1000},
            'temperature_c': {'value': 55},
        }]}


class TrialHarness:
    def __init__(self, monkeypatch, *, initial_status=None, apply_results=None, guard=True):
        self.module = load_trial_client()
        self.gpu_uuid = 'GPU-trial-test'
        self.current_mw = 250000
        self.read_uuids = []
        self.calls = []
        self.clients = []
        self.initial_status = initial_status or {
            'ok': True, 'gpu_uuid': self.gpu_uuid, 'state': 'idle'}
        self.apply_results = list(apply_results or [])
        self.guard = guard
        self.operation_id = 0
        self.poll_responses = []

        def response(operation, fields):
            self.calls.append((operation, fields))
            if operation == 'power_status':
                if self.initial_status is not None:
                    result, self.initial_status = self.initial_status, None
                    return result
                if self.poll_responses:
                    return self.poll_responses.pop(0)
                return {'ok': True, 'gpu_uuid': self.gpu_uuid,
                        'operation_id': self.operation_id, 'state': 'idle'}
            if operation == 'power_apply':
                if self.apply_results:
                    result = self.apply_results.pop(0)
                else:
                    self.operation_id += 1
                    result = {
                        'ok': True, 'gpu_uuid': self.gpu_uuid,
                        'operation_id': self.operation_id, 'state': 'applied',
                        'previous_mw': fields['expected_mw'],
                        'applied_mw': fields['limit_mw'],
                    }
                if result.get('ok') and result.get('state') == 'applied':
                    self.current_mw = result['applied_mw']
                return result
            raise AssertionError(f'unexpected operation: {operation}')

        def create_client(_path):
            client = FakeClient(response)
            self.clients.append(client)
            return client

        harness = self

        class GuardPath:
            def __init__(self, value):
                self.value = value

            def exists(self):
                assert self.value == '/run/gwe-fan-service/power-trial.json'
                return harness.guard

        monkeypatch.setattr(self.module, 'FanClient', create_client)
        monkeypatch.setattr(self.module, 'NvmlBackend', lambda: FakeNvmlBackend(self))
        monkeypatch.setattr(self.module, 'Path', GuardPath)
        monkeypatch.setattr(self.module.time, 'sleep', lambda _seconds: None)
        monkeypatch.setattr(self.module.time, 'monotonic', lambda: 0)


def test_client_verifies_250_to_240_to_250_with_fresh_clients(monkeypatch, capsys):
    trial = TrialHarness(monkeypatch)

    trial.module.main()

    assert [(op, fields.get('limit_mw'), fields.get('expected_mw'))
            for op, fields in trial.calls] == [
        ('power_status', None, None),
        ('power_apply', 240000, 250000),
        ('power_apply', 250000, 240000),
    ]
    assert all(fields.get('expected_uuid') == trial.gpu_uuid
               for op, fields in trial.calls if op == 'power_apply')
    assert trial.current_mw == 250000
    assert trial.read_uuids == [None, trial.gpu_uuid, trial.gpu_uuid,
                                trial.gpu_uuid]
    assert len(trial.clients) == len(trial.calls)
    assert all(client.closed == 1 for client in trial.clients)
    output = capsys.readouterr().out
    assert 'survives client disconnect' in output
    assert output.count('Power verified by service and independent read:') == 2


def test_client_refusal_is_not_retried(monkeypatch):
    trial = TrialHarness(monkeypatch, apply_results=[
        {'ok': False, 'error': 'stale_power'}])

    with pytest.raises(RuntimeError, match='Service refused power request'):
        trial.module.main()

    assert len([call for call in trial.calls if call[0] == 'power_apply']) == 1


def test_recovery_trial_hold_commits_only_240_for_independent_guard(monkeypatch):
    trial = TrialHarness(monkeypatch)
    assert trial.module.main(hold=True) == trial.gpu_uuid
    assert trial.current_mw == 240000
    assert [fields['limit_mw'] for op, fields in trial.calls if op == 'power_apply'] == [240000]


@pytest.mark.parametrize('status', [
    {'ok': True, 'gpu_uuid': 'GPU-other', 'state': 'idle'},
    {'ok': True, 'gpu_uuid': 'GPU-trial-test', 'state': 'busy'},
    {'ok': False, 'gpu_uuid': 'GPU-trial-test', 'state': 'idle'},
])
def test_client_refuses_service_status_mismatch_before_apply(monkeypatch, status):
    trial = TrialHarness(monkeypatch, initial_status=status)

    with pytest.raises(RuntimeError, match='Service not ready for this GPU'):
        trial.module.main()

    assert not [call for call in trial.calls if call[0] == 'power_apply']


def test_client_requires_independent_trial_guard(monkeypatch):
    trial = TrialHarness(monkeypatch, guard=False)

    with pytest.raises(RuntimeError, match='Missing independent trial recovery guard'):
        trial.module.main()

    assert trial.calls == []


@pytest.mark.parametrize(('uuid', 'operation_id'), [
    ('GPU-other', 5), ('GPU-trial-test', 6),
])
def test_poll_identity_mismatch_stops_without_reapplying(monkeypatch, uuid, operation_id):
    trial = TrialHarness(monkeypatch)
    trial.apply_results = [{
        'ok': True, 'gpu_uuid': trial.gpu_uuid, 'operation_id': 5, 'state': 'busy'}]
    trial.poll_responses = [{
        'ok': True, 'gpu_uuid': uuid, 'operation_id': operation_id, 'state': 'applied',
        'previous_mw': 250000, 'applied_mw': 240000,
    }]

    with pytest.raises(RuntimeError, match='Power result identity changed'):
        trial.module.main()

    assert len([call for call in trial.calls if call[0] == 'power_apply']) == 1


def make_wrapper_fixture(tmp_path):
    root = tmp_path / 'checkout'
    (root / 'scripts').mkdir(parents=True)
    (root / 'scripts/power_service_trial.py').write_text('# placeholder\n')
    runtime = tmp_path / 'run/gwe-fan-service'
    runtime.mkdir(parents=True)
    installed = tmp_path / 'opt/gwe-fan-service'
    installed.mkdir(parents=True)
    (installed / 'entry.py').write_text('# placeholder\n')
    bundle = tmp_path / 'bundle'
    bundle.mkdir()
    update = bundle / 'update.sh'
    update.write_text('#!/bin/sh\necho update >> "$TRIAL_LOG"\n')
    update.chmod(0o755)

    script = (ROOT / 'scripts/validate_power_service.sh').read_text()
    script = script.replace('/opt/gwe-fan-service', str(installed))
    script = script.replace('/run/gwe-fan-service', str(runtime))
    script = script.replace('/usr/bin/python3', str(tmp_path / 'mock-bin/installed-python'))
    wrapper = root / 'scripts/validate_power_service.sh'
    wrapper.write_text(script)
    return root, wrapper, bundle, installed, runtime


def make_wrapper_commands(tmp_path):
    bindir = tmp_path / 'mock-bin'
    bindir.mkdir(exist_ok=True)
    commands = {
        'sudo': '''#!/bin/sh
echo "sudo $*" >> "$TRIAL_LOG"
if [ "$1" = -v ]; then exit 0; fi
exec "$@"
''',
        'systemctl': '''#!/bin/sh
echo "systemctl $*" >> "$TRIAL_LOG"
if [ "$1" = show ]; then echo inactive; exit 0; fi
if [ "$1" = is-active ]; then
    if [ "${COOLER_ACTIVE:-1}" = 1 ]; then exit 0; else exit 3; fi
fi
if [ "$1" = stop ] || [ "$1" = start ]; then exit 0; fi
exit 91
''',
        'install': '''#!/bin/sh
echo "install $*" >> "$TRIAL_LOG"
mkdir -p "$TRIAL_RUNTIME"
chmod 0711 "$TRIAL_RUNTIME"
''',
    }
    for name, body in commands.items():
        path = bindir / name
        path.write_text(body)
        path.chmod(0o755)

    fake_python = bindir / 'installed-python'
    fake_python.write_text('''#!/bin/bash
action=${@: -1}
echo "entry $action" >> "$TRIAL_LOG"
case "$action" in
    check) exit 0 ;;
    prepare-power-trial)
        touch "$TRIAL_RUNTIME/power-trial.json"
        exit "${FAIL_PREPARE:-0}" ;;
    recover)
        if [ "${FAIL_RECOVER:-0}" = 1 ]; then exit 44; fi
        rm -f "$TRIAL_RUNTIME/owned.json" "$TRIAL_RUNTIME/power-pending.json" \\
              "$TRIAL_RUNTIME/power-trial.json"
        exit 0 ;;
esac
exit 92
''')
    fake_python.chmod(0o755)
    trial = bindir / 'trial-python'
    trial.write_text('''#!/bin/sh
echo "trial" >> "$TRIAL_LOG"
exit "${TRIAL_EXIT:-0}"
''')
    trial.chmod(0o755)
    return bindir, fake_python, trial


def run_wrapper(tmp_path, wrapper, bundle, runtime, bindir, trial_python, **extra_env):
    log = tmp_path / 'wrapper.log'
    env = {
        **os.environ,
        'PATH': f'{bindir}:{os.environ["PATH"]}',
        'TRIAL_LOG': str(log),
        'TRIAL_RUNTIME': str(runtime),
        **extra_env,
    }
    result = subprocess.run(['bash', str(wrapper), str(trial_python), str(bundle)],
                            cwd=wrapper.parents[1], env=env, capture_output=True, text=True)
    return result, log.read_text() if log.exists() else ''


@pytest.mark.parametrize(('cooler_active', 'expect_restart'), [(1, True), (0, False)])
def test_wrapper_recovers_and_preserves_cooler_state(
        tmp_path, cooler_active, expect_restart):
    _, wrapper, bundle, _installed, runtime = make_wrapper_fixture(tmp_path)
    bindir, _fake_python, trial_python = make_wrapper_commands(tmp_path)

    result, log = run_wrapper(tmp_path, wrapper, bundle, runtime, bindir, trial_python,
                              COOLER_ACTIVE=str(cooler_active))

    assert result.returncode == 0, result.stderr
    assert 'entry prepare-power-trial' in log and 'trial' in log
    assert log.index('systemctl stop gwe-fan-service.service') < log.index('entry recover')
    assert not (runtime / 'power-trial.json').exists()
    starts = [row for row in log.splitlines()
              if row == 'sudo systemctl start coolercontrold.service']
    assert bool(starts) is expect_restart


def test_wrapper_keeps_cooler_stopped_when_recovery_fails(tmp_path):
    _, wrapper, bundle, _installed, runtime = make_wrapper_fixture(tmp_path)
    bindir, _fake_python, trial_python = make_wrapper_commands(tmp_path)

    result, log = run_wrapper(tmp_path, wrapper, bundle, runtime, bindir, trial_python,
                              COOLER_ACTIVE='1', FAIL_RECOVER='1')

    assert result.returncode != 0
    assert 'entry recover' in log
    assert 'Recovery pending; CoolerControl remains stopped' in result.stdout
    assert 'sudo systemctl start coolercontrold.service' not in log


def test_wrapper_runs_recovery_even_when_trial_command_fails(tmp_path):
    _, wrapper, bundle, _installed, runtime = make_wrapper_fixture(tmp_path)
    bindir, _fake_python, trial_python = make_wrapper_commands(tmp_path)

    result, log = run_wrapper(tmp_path, wrapper, bundle, runtime, bindir, trial_python,
                              COOLER_ACTIVE='1', TRIAL_EXIT='17')

    assert result.returncode == 17
    assert 'trial' in log and 'entry recover' in log
    assert 'sudo systemctl start coolercontrold.service' in log


def test_wrapper_installed_mode_creates_missing_runtime_before_guard(tmp_path):
    _, wrapper, _bundle, _installed, runtime = make_wrapper_fixture(tmp_path)
    runtime.rmdir()
    bindir, _fake_python, trial_python = make_wrapper_commands(tmp_path)
    result, log = run_wrapper(tmp_path, wrapper, '--installed', runtime, bindir, trial_python)
    assert result.returncode == 0, result.stderr
    assert '\nupdate\n' not in '\n' + log
    assert 'entry check' in log
    assert log.index('install -d') < log.index('entry prepare-power-trial')
    assert log.index('entry prepare-power-trial') < log.index('systemctl start gwe-fan-service.service')
    assert runtime.stat().st_mode & 0o777 == 0o711
    assert 'entry recover' in log
    assert not (runtime / 'power-trial.json').exists()


def test_gui_wrapper_uses_explicit_backup_and_power_flag_with_guarded_cleanup(tmp_path):
    _, wrapper, _bundle, _installed, runtime = make_wrapper_fixture(tmp_path)
    bindir, _fake_python, trial_python = make_wrapper_commands(tmp_path)
    database = tmp_path / 'backup.db'
    database.write_text('test-only placeholder')
    trial_python.write_text('#!/bin/sh\necho "gui_args $*" >> "$TRIAL_LOG"\n')
    log = tmp_path / 'gui-wrapper.log'
    result = subprocess.run(
        ['bash', str(wrapper), str(trial_python), '--installed', '--gui', str(database)],
        env={**os.environ, 'PATH': f'{bindir}:{os.environ["PATH"]}',
             'TRIAL_LOG': str(log), 'TRIAL_RUNTIME': str(runtime)},
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    events = log.read_text()
    assert f'gui_args scripts/run_service_gui.py --database {database} --allow-power-control' in events
    assert '--allow-control' not in events
    assert events.index('entry prepare-power-trial') < events.index('gui_args') < events.index('entry recover')
    assert 'systemctl start coolercontrold.service' in events
    assert not (runtime / 'power-trial.json').exists()


@pytest.mark.parametrize('trial_exit', ['0', '17'])
def test_recovery_wrapper_routes_one_command_and_always_cleans_up(tmp_path, trial_exit):
    _, wrapper, _bundle, _installed, runtime = make_wrapper_fixture(tmp_path)
    bindir, _fake_python, trial_python = make_wrapper_commands(tmp_path)
    trial_python.write_text('#!/bin/sh\necho "recovery_args $*" >> "$TRIAL_LOG"\nexit "$TRIAL_EXIT"\n')
    log = tmp_path / 'recovery-wrapper.log'
    result = subprocess.run(['bash', str(wrapper), str(trial_python), '--installed', '--recovery'],
                            env={**os.environ, 'PATH': f'{bindir}:{os.environ["PATH"]}',
                                 'TRIAL_LOG': str(log), 'TRIAL_RUNTIME': str(runtime),
                                 'TRIAL_EXIT': trial_exit}, capture_output=True, text=True)
    assert result.returncode == int(trial_exit), result.stderr
    events = log.read_text()
    assert 'recovery_args scripts/power_recovery_trial.py' in events
    assert events.index('entry prepare-power-trial') < events.index('recovery_args') < events.index('entry recover')
    assert 'systemctl start coolercontrold.service' in events
    assert not (runtime / 'power-trial.json').exists()
