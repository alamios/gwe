# SPDX-License-Identifier: GPL-3.0-or-later
import os
from pathlib import Path
import socket
import threading

import pytest
from gwe import desktop_activation as activation
from gwe.fan_service import FanClient, FanService


class Backend:
    def __init__(self):
        self.stops = 0
    def start(self, curve):
        pass
    def stop(self):
        self.stops += 1


@pytest.fixture
def endpoint(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    path = tmp_path / 'fan.sock'
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    listener.bind(str(path))
    path.chmod(0o600)
    listener.listen(8)
    duplicate = os.dup
    monkeypatch.setattr(activation.os, 'dup', lambda fd: duplicate(listener.fileno()))
    monkeypatch.setenv('LISTEN_PID', str(os.getpid()))
    monkeypatch.setenv('LISTEN_FDS', '1')
    try:
        yield path, listener
    finally:
        listener.close()


def test_authenticated_initial_peer_is_preserved_and_lease_recovers(endpoint):
    path, _ = endpoint
    client = FanClient(path)
    listener, peer, pid = activation.activated_listener(path, os.getuid())
    assert pid == os.getpid()
    backend = Backend()
    service = FanService(path, backend, allowed_uid=os.getuid(), listener=listener, initial_peer=peer)
    stopped = threading.Event()
    def serve():
        while not stopped.is_set():
            service.step(.01)
    thread = threading.Thread(target=serve)
    thread.start()
    try:
        assert client.request('status')['state'] == 'idle'
        assert client.request('acquire', points=[[40, 30], [80, 100]], hysteresis=2, vbios_silent=False)['ok']
        client.close()
    finally:
        stopped.set()
        thread.join(2)
        service.close()
    assert backend.stops == 1
    assert path.exists()  # Only systemd removes its activation endpoint.


@pytest.mark.parametrize('variable,value', [('LISTEN_PID', '1'), ('LISTEN_FDS', '2')])
def test_wrong_activation_environment_is_rejected(endpoint, monkeypatch, variable, value):
    path, _ = endpoint
    monkeypatch.setenv(variable, value)
    with pytest.raises(RuntimeError):
        activation.activated_listener(path, os.getuid())


def test_unsafe_socket_permissions_rejected_before_peer_accept(endpoint):
    path, _ = endpoint
    path.chmod(0o666)
    with pytest.raises(RuntimeError):
        activation.activated_listener(path, os.getuid())


def test_unauthorized_peer_does_not_enter_service(endpoint, monkeypatch):
    path, _ = endpoint
    # Keep file ownership valid but change the credentials returned by the peer.
    import struct
    original = socket.socket.getsockopt
    def credentials(self, level, option, *args):
        if option == socket.SO_PEERCRED:
            return struct.pack('3i', os.getpid(), os.getuid() + 1, os.getgid())
        return original(self, level, option, *args)
    monkeypatch.setattr(socket.socket, 'getsockopt', credentials)
    client = FanClient(path)
    try:
        with pytest.raises(PermissionError):
            activation.activated_listener(path, os.getuid())
    finally:
        client.close()


def test_existing_authorization_is_preserved_without_nvml_calls(tmp_path, monkeypatch):
    from gwe import fan_daemon as daemon, native_setup as setup
    config = tmp_path / 'config.json'
    original = '{"private fixture": true}'
    config.write_text(original)
    monkeypatch.setattr(daemon, 'load_config', lambda path: {'allowed_uid': 1000})
    monkeypatch.setattr(daemon, 'trusted', lambda path: Path(path))
    monkeypatch.setattr(setup, 'OWNER_OVERRIDE', tmp_path / 'socket.d/10-owner.conf')
    setup.configure(config, uid=2000)
    assert config.read_text() == original
    assert setup.OWNER_OVERRIDE.read_text() == '[Socket]\nSocketUser=1000\n'


@pytest.mark.parametrize('device_count', [1, 2])
def test_new_authorization_uses_read_only_identity_and_refuses_ambiguous_gpu(tmp_path, monkeypatch, device_count):
    from types import SimpleNamespace
    import sys
    from gwe import fan_daemon as daemon, native_setup as setup
    calls = []
    monkeypatch.setattr(daemon, 'trusted', lambda path: Path(path))
    monkeypatch.setattr(setup, 'OWNER_OVERRIDE', tmp_path / 'socket.d/10-owner.conf')
    monkeypatch.setattr(setup.pwd, 'getpwuid', lambda uid: SimpleNamespace(pw_uid=uid))
    # Deliberately no setter API in the binding fixture.
    monkeypatch.setitem(sys.modules, 'pynvml', SimpleNamespace(
        nvmlInit=lambda: calls.append('init'), nvmlShutdown=lambda: calls.append('shutdown'),
        nvmlDeviceGetCount=lambda: device_count, nvmlDeviceGetHandleByIndex=lambda index: object(),
        nvmlDeviceGetUUID=lambda handle: 'GPU-11111111-2222-3333-4444-555555555555'))
    config = tmp_path / 'private.json'
    if device_count == 1:
        setup.configure(config, uid=1000)
        assert config.stat().st_mode & 0o777 == 0o600
        import json
        assert json.loads(config.read_text())['allowed_uid'] == 1000
    else:
        with pytest.raises(ValueError):
            setup.configure(config, uid=1000)
        assert not config.exists() and not setup.OWNER_OVERRIDE.exists()
    assert calls == ['init', 'shutdown']
