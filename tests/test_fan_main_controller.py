# SPDX-License-Identifier: GPL-3.0-or-later
"""Main-window adapter with real I/O scheduling and simulated service requests."""
import time
from types import SimpleNamespace
import pytest
from gwe.fan_curve import FanCurve
from gwe.fan_gui_session import FanGuiSession
from gwe.fan_main_controller import FanMainController
from gwe.fan_profiles import SavedFanProfile


class View:
    def __init__(self):
        self.calls = {}
    def __getattr__(self, name):
        return lambda *values: self.calls.__setitem__(name, values)


class Client:
    def __init__(self):
        self.calls = []
        self.state = 'idle'
        self.closed = False
    def request(self, operation, **fields):
        self.calls.append(operation)
        if operation == 'acquire':
            self.state = 'active'
        if operation == 'release':
            self.state = 'idle'
        return {'ok': True, 'state': self.state, 'owned': self.state == 'active'}
    def close(self):
        self.closed = True


@pytest.fixture
def controller():
    view, client, now = View(), Client(), [0]
    session = FanGuiSession('unused', factory=lambda _: client, clock=lambda: now[0])
    profiles = (SavedFanProfile(1, '<Saved & curve>', FanCurve(((40, 30), (80, 100)), 3, True), None),
                SavedFanProfile(2, 'Incompatible', FanCurve(((40, 0), (80, 100))), None))
    instance = FanMainController(view, profiles, (30, 100), session,
                                 allow_control=True, clock=lambda: now[0])
    instance.start()
    yield instance, view, client, now
    instance.close()


def settle(instance):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        instance.pulse()
        if instance.pending is None:
            return
        time.sleep(.005)
    pytest.fail('Controller I/O did not settle')


def activate(controller):
    instance, view, client, now = controller
    instance.telemetry(True)
    instance.select(1)
    instance.apply()
    settle(instance)
    assert instance.session.state == 'active'


def test_startup_does_not_select_or_apply_saved_profiles(controller):
    instance, view, client, now = controller
    assert instance.selected is None and not client.calls
    rows, active = view.calls['refresh_fan_profile_combobox']
    assert rows[0] == (1, '&lt;Saved &amp; curve&gt;') and active is None
    assert len(rows) == 2
    assert view.calls['set_apply_fan_profile_button_enabled'] == (False,)


def test_selection_preserves_curve_settings_without_applying(controller):
    instance, view, client, now = controller
    instance.select(1)
    curve, = view.calls['refresh_service_curve']
    assert curve.points == ((40, 30), (80, 100)) and curve.hysteresis == 3 and curve.vbios_silent
    assert not client.calls


def test_preview_flag_blocks_apply_even_with_telemetry(controller):
    instance, view, client, now = controller
    instance.allow_control = False
    instance.select(1)
    instance.telemetry(True)
    instance.apply()
    assert not client.calls and instance.pending is None


def test_missing_telemetry_blocks_apply(controller):
    instance, view, client, now = controller
    instance.select(1)
    instance.apply()
    assert not client.calls and instance.pending is None


def test_incompatible_profile_cannot_be_applied(controller):
    instance, view, client, now = controller
    instance.telemetry(True)
    instance.select(2)
    instance.apply()
    assert not client.calls and instance.pending is None
    assert 'explicit review' in view.calls['show_main_infobar_message'][0]


def test_active_control_blocks_selection_and_enables_release(controller):
    activate(controller)
    instance, view, client, now = controller
    instance.select(2)
    assert instance.selected.identifier == 1
    assert view.calls['set_service_selection_enabled'] == (False,)
    assert view.calls['set_edit_fan_profile_button_enabled'] == (True,)


def test_release_displays_verified_automatic(controller):
    activate(controller)
    instance, view, client, now = controller
    instance.release()
    now[0] = 1
    settle(instance)
    assert instance.session.state == 'idle' and client.closed
    assert 'recovery verified' in view.calls['show_main_infobar_message'][0]


def test_lost_ui_telemetry_releases_ownership(controller):
    activate(controller)
    instance, view, client, now = controller
    instance.telemetry(False)
    now[0] = 1
    settle(instance)
    assert 'release' in client.calls and client.closed
    assert view.calls['set_apply_fan_profile_button_enabled'] == (False,)


def test_stalled_main_loop_cannot_resume_renewal(controller):
    activate(controller)
    instance, view, client, now = controller
    count = client.calls.count('renew')
    now[0] = 4
    settle(instance)
    assert instance.session.state == 'fault' and client.closed
    assert client.calls.count('renew') == count
    assert view.calls['set_apply_fan_profile_button_enabled'] == (False,)


def test_window_close_disconnects_and_is_idempotent(controller):
    activate(controller)
    instance, view, client, now = controller
    instance.close()
    instance.close()
    assert client.closed and instance.session.client is None
    assert not instance.pulse()


@pytest.mark.parametrize('message', [
    'Applying power limit; awaiting service verification.',
    'Power verified: 240 W (previous 250 W). Closing preserves this limit.',
    'Power result unavailable or rejected. Check live limit and service; no automatic retry.',
])
@pytest.mark.parametrize('fan_enabled', [False, True])
def test_idle_power_status_precedes_optional_fan_instructions(controller, message, fan_enabled):
    instance, view, client, now = controller
    instance.allow_control = fan_enabled
    instance.power = SimpleNamespace(busy=False, message=message, close=lambda: None)
    instance.refresh()
    displayed = view.calls['show_main_infobar_message'][0]
    assert displayed.startswith(message)
    assert ('Select a saved curve.' in displayed) == fan_enabled
    assert not client.calls


def test_active_fan_recovery_message_keeps_priority_over_power(controller):
    activate(controller)
    instance, view, client, now = controller
    instance.power = SimpleNamespace(busy=False, message='Power unavailable during fan control.', close=lambda: None)
    instance.refresh()
    assert view.calls['show_main_infobar_message'][0].startswith(instance.session.message)
