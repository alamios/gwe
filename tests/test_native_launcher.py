# SPDX-License-Identifier: GPL-3.0-or-later
"""The real native launcher can be inspected without a root service or GPU."""
import importlib.util
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


@pytest.fixture
def launcher(tmp_path, monkeypatch):
    from gwe import fan_service, native_configuration
    path = Path(__file__).resolve().parents[1] / 'scripts/run_native.py'
    spec = importlib.util.spec_from_file_location('native_launcher_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path))
    monkeypatch.setitem(sys.modules, 'check_controllers', SimpleNamespace(main=lambda: 0))
    monkeypatch.setattr(native_configuration, 'prepare', lambda base: {'startup_profile': 'Synthetic curve'})
    events, descriptors = [], []
    original_open = os.open
    def open_file(*args, **kwargs):
        descriptor = original_open(*args, **kwargs)
        descriptors.append(descriptor)
        return descriptor
    monkeypatch.setattr(module.os, 'open', open_file)
    class Client:
        def __init__(self, path):
            self.socket = SimpleNamespace(settimeout=lambda timeout: events.append(('timeout', timeout)))
        def request(self, operation, **fields):
            events.append(('request', operation, fields))
            return {'ok': True, 'state': 'idle', **fields}
        def close(self):
            events.append(('close',))
    monkeypatch.setattr(fan_service, 'FanClient', Client)
    try:
        yield module, events, tmp_path
    finally:
        for descriptor in descriptors:
            os.close(descriptor)


def test_native_launcher_authenticates_before_same_pid_exec_and_forwards_login_options(launcher, monkeypatch):
    module, events, directory = launcher
    monkeypatch.setattr(sys, 'argv', ['gwe-nvml', '--hide-window', '--delay', '--check-startup'])
    executed = []
    monkeypatch.setattr(module.os, 'execve', lambda *args: executed.append(args))
    module.main()
    assert events == [('timeout', 15), ('request', 'session', {'fan_control': True}), ('close',)]
    executable, command, environment = executed[0]
    assert executable == '/usr/bin/python3'
    assert command[2:] == ['--native', '--allow-power-control', '--continuous', '--allow-control',
                            '--hide-window', '--delay', '--check-startup']
    assert environment['GWE_STARTUP_PROFILE'] == 'Synthetic curve'
    assert environment['GWE_STATE_HOME'] == str(directory / 'gwe-nvml/state')
    assert 'sudo' not in command and '--database' not in command


def test_competing_controller_aborts_before_configuration_or_service(launcher, monkeypatch):
    from gwe import native_configuration
    module, events, directory = launcher
    monkeypatch.setattr(sys, 'argv', ['gwe-nvml'])
    monkeypatch.setitem(sys.modules, 'check_controllers', SimpleNamespace(main=lambda: 1))
    monkeypatch.setattr(native_configuration, 'prepare', lambda base: pytest.fail('Configuration touched'))
    with pytest.raises(RuntimeError):
        module.main()
    assert not events and not (directory / 'gwe-nvml').exists()


@pytest.mark.parametrize('saved,arguments', [(True, []), (False, ['--external-fans'])])
def test_external_fans_negotiated_before_gui_and_saved_curve_suppressed(launcher, monkeypatch, saved, arguments):
    from gwe import native_configuration
    module, events, directory = launcher
    monkeypatch.setattr(native_configuration, 'prepare', lambda base: {
        'startup_profile': 'Saved curve', 'external_fans': saved})
    monkeypatch.setenv('GWE_STARTUP_PROFILE', 'Inherited curve')
    monkeypatch.setattr(sys, 'argv', ['gwe-nvml', '--hide-window', '--delay', *arguments])
    executed = []
    monkeypatch.setattr(module.os, 'execve', lambda *args: executed.append(args))
    module.main()
    assert ('request', 'session', {'fan_control': False}) in events
    _, command, environment = executed[0]
    assert '--external-fans' in command and '--allow-control' not in command
    assert '--allow-power-control' in command and '--hide-window' in command and '--delay' in command
    assert 'GWE_STARTUP_PROFILE' not in environment


def test_wrong_service_mode_blocks_gui_launch(launcher, monkeypatch):
    from gwe import fan_service
    module, events, directory = launcher
    monkeypatch.setattr(sys, 'argv', ['gwe-nvml', '--external-fans'])
    monkeypatch.setattr(fan_service.FanClient, 'request', lambda *a, **kw: {
        'ok': True, 'state': 'idle', 'fan_control': True})
    monkeypatch.setattr(module.os, 'execve', lambda *args: pytest.fail('GUI launched with wrong mode'))
    with pytest.raises(RuntimeError):
        module.main()
    assert events[-1] == ('close',)
