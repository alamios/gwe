# SPDX-License-Identifier: GPL-3.0-or-later
"""External cooling sessions must never acquire or restore GPU fans."""
import json
import os
from pathlib import Path
import socket
import threading
from types import SimpleNamespace

import pytest

from gwe import desktop_activation, fan_daemon, native_configuration
from gwe.fan_service import FanClient, FanService, Lease, decode


def packet(op, **fields):
    return json.dumps({'version': 1, 'op': op, **fields}).encode()


@pytest.mark.parametrize('enabled', [False, True])
def test_mode_handshake_is_peeked_without_consuming_request(enabled):
    left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    with left, right:
        data = packet('session', fan_control=enabled)
        left.sendall(data)
        assert desktop_activation.session_fan_control(right) is enabled
        assert right.recv(4096) == data


def test_legacy_status_retains_exclusive_mode():
    left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    with left, right:
        left.sendall(packet('status'))
        assert desktop_activation.session_fan_control(right) is True


@pytest.mark.parametrize('data', [packet('session', fan_control=0), packet('session', fan_control='false'),
                                packet('session'), packet('power_status'), b'', b'{' ,
                                b'{"version":1,"op":"session","fan_control":true,"fan_control":false}'])
def test_invalid_handshake_cannot_select_a_mode(data):
    peer = SimpleNamespace(settimeout=lambda seconds: None, recv=lambda *args: data)
    with pytest.raises(ValueError):
        desktop_activation.session_fan_control(peer)


def test_preference_roundtrip_preserves_other_configuration(tmp_path):
    original = native_configuration.prepare(tmp_path, config_home=tmp_path / 'config')
    assert not native_configuration.read_external_fans(tmp_path)
    for value in (True, False):
        native_configuration.set_external_fans(value, tmp_path)
        assert native_configuration.read_external_fans(tmp_path) is value
        assert json.loads((tmp_path / 'config.json').read_text()) == {**original, 'external_fans': value}
        assert (tmp_path / 'config.json').stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('value', [None, 0, 1, 'false', [], {}])
def test_invalid_preference_fails_closed(value):
    with pytest.raises(ValueError):
        native_configuration.external_fans({'external_fans': value})


def test_preference_write_failure_preserves_previous_value(tmp_path, monkeypatch):
    native_configuration.prepare(tmp_path, config_home=tmp_path / 'config')
    original = (tmp_path / 'config.json').read_bytes()
    def fail(*args):
        raise PermissionError('simulated failure')
    monkeypatch.setattr(native_configuration.os, 'replace', fail)
    with pytest.raises(PermissionError):
        native_configuration.set_external_fans(True, tmp_path)
    assert (tmp_path / 'config.json').read_bytes() == original
    assert not list(tmp_path.glob('.config-*'))


class Power:
    uuid = 'GPU-test'

    def __init__(self, *args):
        self.calls = []
        self.result = {'state': 'idle'}

    def poll(self):
        pass

    def status(self):
        return {'ok': True, **self.result}

    def start(self, requested, expected):
        self.calls.append((requested, expected))
        return {'ok': True, 'state': 'busy'}

    def close(self):
        self.calls.append('close')


def test_external_service_blocks_every_fan_operation_but_allows_power(tmp_path):
    tmp_path.chmod(0o700)
    backend = fan_daemon.ExternalFanBackend()
    power = Power()
    service = FanService(tmp_path / 'control.sock', backend, allowed_uid=os.getuid(),
                         power=power, fan_control=False)
    stopped = threading.Event()
    def serve():
        while not stopped.is_set():
            service.step(.01)
    thread = threading.Thread(target=serve)
    thread.start()
    client = FanClient(service.path)
    try:
        assert client.request('session', fan_control=False)['fan_control'] is False
        assert client.request('session', fan_control=True)['error'] == 'session_mode_mismatch'
        for op, fields in [('acquire', dict(points=[[0, 40], [80, 100]], hysteresis=2, vbios_silent=False)),
                           ('release', {}), ('renew', {})]:
            assert client.request(op, **fields) == {'ok': False, 'error': 'fan_control_disabled'}
        assert client.request('power_status')['state'] == 'idle'
        assert client.request('power_apply', expected_uuid='GPU-other', expected_mw=250000,
                              limit_mw=240000)['error'] == 'identity_mismatch'
        assert client.request('power_apply', expected_uuid=power.uuid, expected_mw=250000,
                              limit_mw=240000)['ok']
        assert power.calls == [(240000, 250000)]
        client.socket.sendall(b'{')
        assert json.loads(client.socket.recv(4096))['error'] == 'invalid_request'
        assert client.request('status') == {'ok': True, 'state': 'idle', 'owned': False}
    finally:
        client.close()
        stopped.set()
        thread.join(2)
        service.close()
    assert backend.close() is True
    assert not (tmp_path / 'owned.json').exists()


@pytest.fixture
def daemon_runtime(tmp_path, monkeypatch):
    tmp_path.chmod(0o711)
    monkeypatch.setattr(fan_daemon, 'RUNTIME', tmp_path)
    monkeypatch.setattr(fan_daemon, 'trusted', lambda path: Path(path))
    monkeypatch.setattr(fan_daemon, 'SESSION_OVERRIDE', tmp_path / 'override')
    monkeypatch.setattr(fan_daemon, 'process_identity', lambda pid: (1000, 123))
    monkeypatch.setattr(fan_daemon.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(fan_daemon, 'load_config', lambda path: {'allowed_uid': 1000, 'gpu_uuid': 'GPU-test'})
    monkeypatch.setattr(fan_daemon, 'nvml_factory', lambda: pytest.fail('Fan NVML initialized'))
    monkeypatch.setattr(fan_daemon, 'ProcessBackend', lambda *a, **kw: pytest.fail('Fan worker created'))
    monkeypatch.setattr(fan_daemon, 'PowerBackend', Power)
    monkeypatch.setattr(fan_daemon.subprocess, 'run', lambda *a, **kw: pytest.fail('Cooling service touched'))
    monkeypatch.setattr(fan_daemon.signal, 'signal', lambda *a: None)
    original_iterdir = Path.iterdir
    monkeypatch.setattr(Path, 'iterdir', lambda path: iter(()) if path == Path('/proc') else original_iterdir(path))
    left, right = os.pipe()
    monkeypatch.setattr(fan_daemon, 'session_owner', lambda uid: os.dup(left))
    peer = SimpleNamespace(settimeout=lambda seconds: None,
                           recv=lambda *args: packet('session', fan_control=False), close=lambda: None)
    monkeypatch.setattr(desktop_activation, 'activated_listener',
                        lambda *a: (SimpleNamespace(close=lambda: None), peer, 42))
    def service(path, backend, **kwargs):
        assert kwargs['fan_control'] is False
        assert kwargs['power_with_fan'] is False
        result = FanService.__new__(FanService)
        result.fan_control = False
        result.lease = Lease(backend)
        result.power = kwargs['power']
        result.close = lambda: None
        return result
    monkeypatch.setattr(fan_daemon, 'FanService', service)
    yield tmp_path
    os.close(left)
    os.close(right)


@pytest.mark.parametrize('failure', [False, True])
def test_desktop_shutdown_and_poststop_leave_external_fans_untouched(daemon_runtime, monkeypatch, failure):
    def serve(service, backend, power, stopping, **kwargs):
        assert service.request(object(), decode(packet('release')))['error'] == 'fan_control_disabled'
        assert service.request(object(), decode(packet('power_status')))['ok']
        if failure:
            raise RuntimeError('Simulated supervisor failure')
    monkeypatch.setattr(fan_daemon, 'serve', serve)
    assert fan_daemon.main(['run', '--desktop']) == (1 if failure else 0)
    assert fan_daemon.session_record()['cooler_active'] is False
    assert not (daemon_runtime / 'owned.json').exists()
    assert fan_daemon.main(['recover']) == 0
    assert not (daemon_runtime / 'session.json').exists()


@pytest.mark.parametrize('marker', ['owned.json', 'power-pending.json', 'power-trial.json', 'session.json'])
def test_external_mode_cannot_bypass_pending_recovery(daemon_runtime, monkeypatch, marker):
    (daemon_runtime / marker).write_text('pending')
    monkeypatch.setattr(desktop_activation, 'activated_listener', lambda *a: pytest.fail('Accepted before recovery'))
    assert fan_daemon.main(['run', '--desktop']) == 1
    assert (daemon_runtime / marker).read_text() == 'pending'


def test_external_mode_refuses_stale_manual_override(daemon_runtime):
    (daemon_runtime / 'override').write_text('stale manual session')
    assert fan_daemon.main(['run', '--desktop']) == 1
    assert not (daemon_runtime / 'session.json').exists()
    assert (daemon_runtime / 'override').read_text() == 'stale manual session'
