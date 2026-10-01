# SPDX-License-Identifier: GPL-3.0-or-later
import os
import threading

import pytest

from gwe.fan_curve import FanCurve
from gwe.fan_gui_session import FanGuiSession
from gwe.fan_service import FanService

CURVE = FanCurve(((40, 30), (80, 100)), 3, True)


class Client:
    def __init__(self):
        self.calls = []
        self.state = 'idle'
        self.owned = False
        self.closed = False
        self.refuse = None

    def request(self, operation, **fields):
        self.calls.append((operation, fields))
        if self.refuse == operation:
            return {'ok': False, 'error': 'private error'}
        if operation == 'acquire':
            self.state, self.owned = 'active', True
        elif operation == 'release':
            self.state, self.owned = 'stopping', False
        return {'ok': True, 'state': self.state, 'owned': self.owned}

    def close(self):
        self.closed = True


@pytest.fixture
def session():
    client = Client()
    now = [0]
    instance = FanGuiSession('unused', factory=lambda _: client, clock=lambda: now[0])
    return instance, client, now


def test_construction_and_preview_never_connect_or_acquire():
    instance = FanGuiSession('unused', factory=lambda _: pytest.fail('Unexpected connection'))
    instance.tick(0)
    instance.release()
    instance.close()
    assert instance.state == 'idle'


def test_explicit_apply_preserves_complete_curve(session):
    instance, client, now = session
    instance.begin(CURVE, (30, 100))
    assert client.calls[1] == ('acquire', {'points': [[40, 30], [80, 100]],
                                         'hysteresis': 3, 'vbios_silent': True})
    instance.tick(0)
    assert instance.state == 'active'
    assert client.calls[-1][0] == 'renew'


def test_incompatible_curve_never_connects(session):
    instance, client, now = session
    with pytest.raises(ValueError):
        instance.begin(FanCurve(((40, 0),)), (30, 100))
    assert client.calls == [] and instance.client is None


def test_busy_service_is_not_acquired_or_released(session):
    instance, client, now = session
    client.state = 'active'
    instance.begin(CURVE, (30, 100))
    assert [call[0] for call in client.calls] == ['status']
    assert client.closed and instance.state == 'fault'


def test_release_waits_for_verified_idle(session):
    instance, client, now = session
    instance.begin(CURVE, (30, 100))
    instance.release()
    instance.tick(0)
    assert instance.state == 'stopping'
    client.state = 'idle'
    instance.tick(0)
    assert instance.state == 'idle' and client.closed
    assert 'verified' in instance.message


def test_trial_deadline_stops_renewal_and_releases(session):
    instance, client, now = session
    instance.begin(CURVE, (30, 100))
    for instant in range(1, 11):
        now[0] = instant
        instance.tick(instant)
    assert instance.state == 'stopping'
    assert [call[0] for call in client.calls[-2:]] == ['release', 'status']


@pytest.mark.parametrize('heartbeat,now_value', [(1, 4), (4, 4), (-1, 1)])
def test_frozen_or_stale_ui_cannot_renew(session, heartbeat, now_value):
    instance, client, now = session
    instance.begin(CURVE, (30, 100))
    now[0] = now_value
    instance.tick(heartbeat)
    assert instance.state == 'fault' and client.closed
    assert all(call[0] != 'renew' for call in client.calls)
    with pytest.raises(RuntimeError):
        instance.begin(CURVE, (30, 100))


def test_lost_ownership_never_rearms_or_reports_restored(session):
    instance, client, now = session
    instance.begin(CURVE, (30, 100))
    client.owned = False
    instance.tick(0)
    assert instance.state == 'fault' and client.closed
    assert 'not verified' in instance.message


def test_recovery_deadline_is_bounded(session):
    instance, client, now = session
    instance.begin(CURVE, (30, 100))
    instance.release()
    for instant in range(1, 11):
        now[0] = instant
        instance.tick(instant)
    assert instance.state == 'fault' and client.closed


@pytest.mark.parametrize('operation', ['acquire', 'renew', 'release'])
def test_refusal_closes_and_redacts_error(session, operation):
    instance, client, now = session
    if operation == 'acquire':
        client.refuse = operation
    instance.begin(CURVE, (30, 100))
    client.refuse = operation
    if operation == 'renew':
        instance.tick(0)
    elif operation == 'release':
        instance.release()
    assert instance.state == 'fault' and client.closed
    assert 'private' not in instance.message


def test_real_socket_lifecycle_uses_service_verification(tmp_path):
    class Backend:
        curve = None
        stopped = False
        def start(self, curve):
            self.curve = curve
        def stop(self):
            self.stopped = True
    tmp_path.chmod(0o700)
    backend = Backend()
    service = FanService(tmp_path / 'control.sock', backend, allowed_uid=os.geteuid())
    stop = threading.Event()
    def serve():
        while not stop.is_set():
            service.step(.01)
    worker = threading.Thread(target=serve)
    worker.start()
    instance = FanGuiSession(tmp_path / 'control.sock')
    try:
        instance.begin(CURVE, (30, 100))
        instance.tick(instance.clock())
        assert instance.state == 'active' and backend.curve == CURVE
        instance.release()
        instance.tick(instance.clock())
        assert instance.state == 'idle' and backend.stopped
    finally:
        instance.close()
        stop.set()
        worker.join(2)
        service.close()
