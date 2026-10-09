# SPDX-License-Identifier: GPL-3.0-or-later
"""Suspend differs from process stalls; recovery must precede reacquisition."""
import pytest
from types import SimpleNamespace

from gwe.fan_curve import FanCurve
from gwe.fan_gui_session import FanGuiSession
from gwe.fan_service import Lease
from gwe.fan_profiles import SavedFanProfile
from gwe.native_fan_controller import NativeFanController
from gwe.fan_process import ProcessBackend

CURVE = FanCurve(((40, 30), (80, 100)), 3, True)


class Backend:
    state = 'idle'
    delayed = False
    reject_start = False

    def __init__(self):
        self.curves = []
        self.stops = 0

    def poll(self):
        return self.state

    def start(self, curve):
        if self.reject_start:
            raise RuntimeError('Invalid fresh telemetry or changed limits')
        self.curves.append(curve)
        self.state = 'active'

    def stop(self):
        self.stops += 1
        self.state = 'stopping' if self.delayed else 'idle'


@pytest.fixture
def control():
    times = [0., 0.]
    backend = Backend()
    lease = Lease(backend, clock=lambda: times[0])
    clients, events = [], []
    class Client:
        def request(self, op, **fields):
            if op == 'acquire':
                fields['curve'] = FanCurve(fields['points'], fields['hysteresis'], fields['vbios_silent'])
            return lease.request(self, {'op': op, **fields})

        def close(self):
            lease.disconnect(self)
    def factory(path):
        client = Client()
        clients.append(client)
        return client
    session = FanGuiSession('unused', factory=factory, clock=lambda: times[0],
                            active_clock=lambda: times[1], continuous=True,
                            event_sink=lambda event, **fields: events.append(event))
    session.begin(CURVE, (30, 100))
    session.tick(times[0])
    assert session.state == 'active'
    yield session, backend, times, events
    session.close()


def suspend(times, sleeping=60, awake=.1):
    times[0] += sleeping + awake
    times[1] += awake


def test_resume_reapplies_exact_applied_curve_after_verified_idle(control):
    session, backend, times, events = control
    suspend(times)
    session.tick(times[0])
    assert session.state == 'starting'
    assert backend.curves == [CURVE, CURVE] and backend.stops == 1
    assert events.index('resume_recovery_verified') < events.index('resume_acquired')
    times[0] += 1
    times[1] += 1
    session.tick(times[0])
    assert session.state == 'active' and len(backend.curves) == 2
    assert 'failed' not in events


def test_resume_waits_for_verified_recovery(control):
    session, backend, times, events = control
    backend.delayed = True
    suspend(times)
    session.tick(times[0])
    assert session.state == 'resuming' and len(backend.curves) == 1
    times[0] += 1
    times[1] += 1
    session.tick(times[0])
    assert session.state == 'resuming' and len(backend.curves) == 1
    backend.state = 'idle'
    session.tick(times[0])
    assert session.state == 'starting' and len(backend.curves) == 2


def test_recovery_timeout_latches_fault(control):
    session, backend, times, events = control
    backend.delayed = True
    suspend(times)
    session.tick(times[0])
    times[0] += 15
    times[1] += 15
    session.tick(times[0])
    assert session.state == 'fault' and session.last_error == 'resume_recovery_timeout'
    backend.state = 'idle'
    session.tick(times[0])
    assert len(backend.curves) == 1


@pytest.mark.parametrize('action', ['close', 'release'])
def test_quit_or_release_cancels_pending_resume(control, action):
    session, backend, times, events = control
    backend.delayed = True
    suspend(times)
    session.tick(times[0])
    getattr(session, action)()
    backend.state = 'idle'
    session.tick(times[0])
    assert session.client is None and len(backend.curves) == 1


def test_stopping_before_suspend_never_reapplies(control):
    session, backend, times, events = control
    session.release()
    suspend(times)
    session.tick(times[0])
    assert len(backend.curves) == 1 and 'suspend_detected' not in events


def test_process_stall_is_not_suspend(control):
    session, backend, times, events = control
    times[0] += 20
    times[1] += 20
    session.tick(times[0])
    assert session.state == 'fault' and session.last_error == 'worker_heartbeat_expired'
    assert len(backend.curves) == 1 and 'suspend_detected' not in events


def test_small_clock_difference_does_not_rearm(control):
    session, backend, times, events = control
    suspend(times, sleeping=.5, awake=4)
    session.tick(times[0])
    assert session.state == 'fault' and len(backend.curves) == 1


def test_bounded_trial_never_rearms_after_suspend(control):
    session, backend, times, events = control
    session.continuous = False
    suspend(times)
    session.tick(times[0])
    assert session.state == 'fault' and len(backend.curves) == 1


def test_suspend_never_clears_existing_fault(control):
    session, backend, times, events = control
    session._fail(TimeoutError())
    suspend(times)
    session.tick(times[0])
    assert session.state == 'fault' and len(backend.curves) == 1


def test_resume_revalidates_backend_before_writing(control):
    session, backend, times, events = control
    backend.reject_start = True
    suspend(times)
    session.tick(times[0])
    assert session.state == 'fault' and len(backend.curves) == 1
    assert backend.state == 'idle' and 'resume_acquired' not in events


def test_socket_error_during_resume_is_not_retried(control):
    session, backend, times, events = control
    def unavailable(path):
        raise TimeoutError('private detail')
    session.factory = unavailable
    suspend(times)
    session.tick(times[0])
    assert session.state == 'fault' and session.last_error == 'socket_timeout'
    session.tick(times[0])
    assert len(backend.curves) == 1 and 'private' not in session.message


def test_slow_status_cannot_extend_resume_deadline(control):
    session, backend, times, events = control
    factory = session.factory
    def delayed_factory(path):
        client = factory(path)
        request = client.request
        def slow_status(*args, **kwargs):
            times[0] += 16
            times[1] += 16
            return request(*args, **kwargs)
        client.request = slow_status
        return client
    session.factory = delayed_factory
    suspend(times)
    session.tick(times[0])
    assert session.state == 'fault' and session.last_error == 'resume_recovery_timeout'
    assert len(backend.curves) == 1


def test_unowned_active_service_is_never_taken_over(control):
    session, backend, times, events = control
    class OtherOwner:
        def request(self, *args, **kwargs):
            return {'ok': True, 'state': 'active', 'owned': False}
        def close(self):
            pass
    session.factory = lambda _: OtherOwner()
    suspend(times)
    session.tick(times[0])
    assert session.state == 'fault' and session.last_error == 'resume_service_not_idle'
    assert len(backend.curves) == 1


def test_deleting_applied_profile_cancels_pending_native_resume(monkeypatch, control):
    session, backend, times, events = control
    backend.delayed = True
    suspend(times)
    session.tick(times[0])
    automatic = SavedFanProfile(2, 'Automatic', None, None, automatic=True)
    monkeypatch.setattr('gwe.native_fan_controller.read_profiles', lambda *a, **k: (automatic,))
    view = SimpleNamespace(refresh_fan_profile_combobox=lambda *a: None,
                           refresh_service_curve=lambda *a: None)
    controller = NativeFanController.__new__(NativeFanController)
    controller.database = SimpleNamespace(database='unused')
    controller.view = view
    controller.selected = SavedFanProfile(1, 'Applied', CURVE, None)
    controller.session = session
    controller.applied_identifier = 1
    controller.refresh = lambda: None
    controller.release = session.release
    controller.reload()
    backend.state = 'idle'
    session.tick(times[0])
    assert controller.desired is automatic
    assert session.state == 'idle' and len(backend.curves) == 1


@pytest.mark.parametrize('sleeping,prior_fault,expected_fault', [(20, False, False),
                                                             (0, False, True), (20, True, True)])
def test_supervisor_distinguishes_suspend_from_stall_without_clearing_faults(
        monkeypatch, sleeping, prior_fault, expected_fault):
    times = [0., 0.]
    monkeypatch.setattr('gwe.fan_process.boot_time', lambda: times[0])
    backend = ProcessBackend('GPU-test', active_clock=lambda: times[1])
    killed = []
    backend.worker = SimpleNamespace(is_alive=lambda: True, kill=lambda: killed.append(True))
    backend.state = 'active'
    backend.deadline = 5
    backend.failure = prior_fault
    monkeypatch.setattr(backend, '_drain', lambda: None)
    times[0] = 20
    times[1] = 20 - sleeping
    assert backend.poll() == 'stopping'
    assert killed == [True] and backend.failure is expected_fault
