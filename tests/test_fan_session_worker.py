# SPDX-License-Identifier: GPL-3.0-or-later
"""Continuous ownership must survive GTK delays, never a lost service lease."""
import threading
import time

import pytest

from gwe.fan_curve import FanCurve
from gwe.fan_gui_session import FanGuiSession
from gwe.fan_main_controller import FanMainController
from gwe.fan_profiles import SavedFanProfile
from gwe.fan_service import Lease
from gwe.fan_session_worker import FanSessionWorker


CURVE = FanCurve(((40, 30), (80, 100)))


class Backend:
    def __init__(self):
        self.starts = self.stops = 0

    def start(self, curve):
        self.starts += 1

    def stop(self):
        self.stops += 1


class Client:
    def __init__(self, lease):
        self.lease = lease
        self.calls = []
        self.threads = set()

    def request(self, operation, **fields):
        self.threads.add(threading.get_ident())
        self.calls.append(operation)
        return self.lease.request(self, {'op': operation, 'curve': CURVE})

    def close(self):
        self.threads.add(threading.get_ident())
        self.lease.disconnect(self)


class View:
    def __getattr__(self, name):
        return lambda *args: None


def test_continuous_controller_keeps_lease_without_gtk_pulses_or_telemetry_refresh():
    backend = Backend()
    lease = Lease(backend)
    client = Client(lease)
    session = FanGuiSession('unused', factory=lambda _: client, continuous=True)
    profile = SavedFanProfile(1, 'Synthetic', CURVE, None)
    controller = FanMainController(View(), (profile,), (30, 100), session, allow_control=True)
    try:
        controller.telemetry(True)
        controller.select(1)
        controller.apply()
        controller.pending.result(timeout=2)
        assert session.state == 'active'
        # Stop dispatching GTK entirely for longer than the service lease.
        # Expire it independently, as the real daemon does, while the client
        # continues serial renewals without any UI telemetry refresh.
        until = time.monotonic() + 6.2
        while time.monotonic() < until:
            time.sleep(.05)
            lease.expire()
            assert lease.owner is client and backend.stops == 0
        assert client.calls.count('renew') >= 6
        assert backend.starts == 1
        controller.telemetry(False)
        controller.pulse()
        assert session.state == 'active'  # Thermal safety belongs to the service.
    finally:
        controller.close()
    assert backend.stops == 1 and lease.owner is None
    assert len(client.threads) == 1
    assert not controller.executor.thread.is_alive()


def test_continuous_session_survives_48_simulated_hours():
    now = [0]
    backend = Backend()
    lease = Lease(backend, clock=lambda: now[0])
    client = Client(lease)
    session = FanGuiSession('unused', factory=lambda _: client, continuous=True, clock=lambda: now[0])
    session.begin(CURVE, (30, 100))
    for second in range(48 * 60 * 60):
        now[0] = second
        session.tick(second)
        assert session.state == 'active' and lease.owner is client
    assert backend.starts == 1 and backend.stops == 0
    session.release()
    session.tick(now[0])
    assert session.state == 'idle' and backend.stops == 1


@pytest.mark.parametrize('fault', ['worker_delay', 'service_expiry', 'backend_fault', 'socket_loss'])
def test_worker_faults_disconnect_and_never_reacquire(fault):
    now = [0]
    backend = Backend()
    lease = Lease(backend, clock=lambda: now[0])
    client = Client(lease)
    session = FanGuiSession('unused', factory=lambda _: client, continuous=True, clock=lambda: now[0])
    worker = FanSessionWorker(session)
    try:
        worker.submit(session.begin, CURVE, (30, 100)).result(timeout=2)
        assert session.state == 'active'
        def inject():
            if fault == 'worker_delay':
                now[0] += 4
            elif fault == 'service_expiry':
                lease.deadline = -1
            elif fault == 'backend_fault':
                lease.state = 'fault'
            else:
                def disconnected(*args, **kwargs):
                    raise OSError('private detail')
                client.request = disconnected
        worker.submit(inject).result(timeout=2)
        assert session.state == 'fault' and session.client is None
        worker.submit(lambda: None).result(timeout=2)
        assert backend.starts == 1
        assert 'private' not in session.message
    finally:
        worker.shutdown()
    assert backend.stops == 1


def test_release_and_shutdown_remain_serial_with_renewals():
    backend = Backend()
    client = Client(Lease(backend))
    session = FanGuiSession('unused', factory=lambda _: client, continuous=True)
    worker = FanSessionWorker(session)
    try:
        worker.submit(session.begin, CURVE, (30, 100)).result(timeout=2)
        worker.submit(session.release).result(timeout=2)
        assert session.state == 'idle' and backend.stops == 1
    finally:
        worker.shutdown()
    assert len(client.threads) == 1
    with pytest.raises(RuntimeError):
        worker.submit(session.begin, CURVE, (30, 100))
