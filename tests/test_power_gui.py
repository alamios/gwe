# SPDX-License-Identifier: GPL-3.0-or-later
"""Power GUI controller tests use only fake service clients and telemetry."""
import time
from types import SimpleNamespace

import pytest

from gwe.power_gui import PowerController, to_mw


GPU = 'GPU-test-only'
LOW = 100.0
CURRENT = 250.0
HIGH = 480.0
REQUESTED = 240.0


class View:
    def __init__(self, value=REQUESTED):
        self.value = value
        self.enabled = []

    def set_service_power_enabled(self, enabled, message):
        self.enabled.append((enabled, message))

    def get_power_limit(self):
        return LOW, self.value


class Service:
    def __init__(self, handler=None):
        self.calls = []
        self.closed = 0
        self.handler = handler or self.default
        self.responses = []

    def default(self, operation, fields):
        if operation == 'power_status':
            return {'ok': True, 'gpu_uuid': GPU, 'state': 'idle', 'operation_id': 0}
        if operation == 'power_apply':
            return {'ok': True, 'gpu_uuid': GPU, 'state': 'busy', 'operation_id': 1}
        raise AssertionError(f'Unexpected operation: {operation}')

    def request(self, operation, **fields):
        self.calls.append((operation, fields))
        return self.handler(operation, fields)

    def close(self):
        self.closed += 1


def gpu(*, uuid=GPU, minimum=LOW, limit=CURRENT, maximum=HIGH):
    return SimpleNamespace(info=SimpleNamespace(uuid=uuid),
                           power=SimpleNamespace(minimum=minimum, limit=limit, maximum=maximum))


@pytest.fixture
def setup():
    now = [10.0]
    view = View()
    service = Service()
    events = []
    controller = PowerController(view, '/fake/control.sock', allowed=True,
                                 factory=lambda path: service, clock=lambda: now[0],
                                 event_sink=lambda event, **fields: events.append((event, fields)))
    controller.telemetry(gpu())
    yield controller, view, service, now, events
    controller.close()


def settle(controller, timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        controller.pulse()
        if controller.pending is None:
            return
        time.sleep(.002)
    pytest.fail('Power controller request did not settle')


def make_available(controller):
    controller.pulse()
    settle(controller)
    assert controller.available


def test_construction_and_startup_are_status_only(setup):
    controller, view, service, now, events = setup
    assert service.calls == []
    assert not view.enabled[-1][0]
    controller.pulse()
    settle(controller)
    assert [operation for operation, _ in service.calls] == ['power_status']
    assert controller.available
    assert not view.enabled[-1][0] or controller.valid()


def test_native_read_only_polling_keeps_apply_enabled_but_writes_disable_it(setup, monkeypatch):
    from concurrent.futures import Future
    monkeypatch.setenv('GWE_NATIVE_DESKTOP', '1')
    controller, view, service, now, events = setup
    make_available(controller)
    controller.pending = Future()  # A pending background read, without scheduling or hardware access.
    controller.pending_operation = 'power_status'
    controller.refresh()
    assert view.enabled[-1][0] and not controller.busy
    controller.apply()
    assert controller.busy and not view.enabled[-1][0]
    settle(controller)
    assert service.calls[-1][0] == 'power_apply'


def test_allowed_false_never_sends_any_request():
    now = [10.0]
    service = Service()
    view = View()
    controller = PowerController(view, '/fake/control.sock', allowed=False,
                                 factory=lambda path: service, clock=lambda: now[0])
    controller.telemetry(gpu())
    controller.pulse()
    controller.apply()
    assert service.calls == []
    assert not view.enabled[-1][0]
    controller.close()


def test_gpu_identity_mismatch_disables_control_and_never_applies(setup):
    controller, view, service, now, events = setup
    service.handler = lambda operation, fields: {
        'ok': True, 'gpu_uuid': 'GPU-other', 'state': 'idle', 'operation_id': 0}
    controller.pulse()
    settle(controller)
    controller.apply()
    assert not controller.available
    assert 'no automatic retry' in controller.message
    assert [op for op, _ in service.calls] == ['power_status']


def test_apply_sends_milliwatts_and_compare_and_swap_value(setup):
    controller, view, service, now, events = setup
    make_available(controller)
    view.value = 239.5
    controller.apply()
    settle(controller)
    operation, fields = service.calls[-1]
    assert operation == 'power_apply'
    assert fields == {'limit_mw': 239_500, 'expected_mw': 250_000, 'expected_uuid': GPU}


@pytest.mark.parametrize('bad_value', [True, 239.50001, 0, -1, float('nan'), float('inf'), '240'])
def test_invalid_or_out_of_range_entry_never_sends_apply(setup, bad_value):
    controller, view, service, now, events = setup
    make_available(controller)
    view.value = bad_value
    controller.apply()
    assert not any(operation == 'power_apply' for operation, _ in service.calls)
    assert 'Invalid power limit' in controller.message


def test_missing_or_out_of_range_telemetry_blocks_control(setup):
    controller, view, service, now, events = setup
    controller.telemetry(gpu(limit=None))
    assert not controller.valid()
    controller.apply()
    assert service.calls == []
    controller.telemetry(gpu(minimum=300, limit=250, maximum=480))
    assert not controller.valid()
    controller.apply()
    assert service.calls == []


def test_stale_telemetry_disables_and_blocks_apply(setup):
    controller, view, service, now, events = setup
    make_available(controller)
    now[0] += 2.6
    controller.apply()
    assert not any(operation == 'power_apply' for operation, _ in service.calls)
    assert not controller.valid()


def test_active_fan_lease_blocks_power_status_and_apply(setup):
    controller, view, service, now, events = setup
    controller.fan_busy = lambda: True
    controller.pulse()
    controller.apply()
    assert service.calls == []
    assert not view.enabled[-1][0]


def test_fan_lease_becoming_busy_after_status_blocks_apply(setup):
    controller, view, service, now, events = setup
    make_available(controller)
    controller.fan_busy = lambda: True
    controller.apply()
    assert not any(operation == 'power_apply' for operation, _ in service.calls)


def test_verified_apply_and_rollback_status_are_reported(setup):
    controller, view, service, now, events = setup
    make_available(controller)
    service.responses = [
        {'ok': True, 'gpu_uuid': GPU, 'state': 'busy', 'operation_id': 7},
        {'ok': True, 'gpu_uuid': GPU, 'state': 'applied', 'operation_id': 7,
         'previous_mw': 250_000, 'applied_mw': 240_000},
    ]

    def scripted(operation, fields):
        if operation == 'power_apply':
            return service.responses.pop(0)
        if operation == 'power_status':
            return service.responses.pop(0) if service.responses else {
                'ok': True, 'gpu_uuid': GPU, 'state': 'idle', 'operation_id': 0}
        raise AssertionError(operation)

    service.handler = scripted
    view.value = REQUESTED
    controller.apply()
    settle(controller)
    assert controller.operation_id == 7 and controller.remote_busy
    now[0] += .3
    controller.pulse()
    settle(controller)
    assert controller.operation_id is None and not controller.remote_busy
    assert 'Power verified: 240 W (previous 250 W)' in controller.message
    assert ('power_verified', {'operation': 'power_status'}) in events


def test_rollback_status_is_reported(setup):
    controller, view, service, now, events = setup
    make_available(controller)
    controller.operation_id = 8
    controller.expected = 250_000
    controller.requested = 240_000
    controller.remote_busy = True
    controller.next_poll = now[0]
    service.handler = lambda operation, fields: {
        'ok': True, 'gpu_uuid': GPU, 'state': 'rolled_back', 'operation_id': 8,
        'previous_mw': 250_000, 'applied_mw': 250_000}
    controller.pulse()
    settle(controller)
    assert controller.operation_id is None and not controller.remote_busy
    assert 'previous limit restored and verified' in controller.message
    assert ('power_rolled_back', {'operation': 'power_status'}) in events


@pytest.mark.parametrize('response', [
    {'ok': True, 'gpu_uuid': 'GPU-other', 'state': 'applied', 'operation_id': 9,
     'previous_mw': 250_000, 'applied_mw': 240_000},
    {'ok': True, 'gpu_uuid': GPU, 'state': 'applied', 'operation_id': 9,
     'previous_mw': 249_000, 'applied_mw': 241_000},
])
def test_success_ack_must_match_gpu_and_exact_transaction_values(setup, response):
    controller, view, service, now, events = setup
    make_available(controller)
    service.handler = lambda operation, fields: {
        'ok': True, 'gpu_uuid': GPU, 'state': 'busy', 'operation_id': 9}
    view.value = REQUESTED
    controller.apply()
    settle(controller)
    assert controller.operation_id == 9 and controller.remote_busy
    now[0] += .3
    service.handler = lambda operation, fields: response
    controller.pulse()
    settle(controller)
    assert not any(event == 'power_verified' for event, fields in events)
    assert 'Power verified' not in controller.message
    assert controller.operation_id is None
    assert not controller.available


def test_error_timeout_and_raw_service_message_are_redacted_without_retry(setup):
    controller, view, service, now, events = setup
    make_available(controller)
    calls_before = len(service.calls)
    service.handler = lambda operation, fields: (_ for _ in ()).throw(
        TimeoutError('secret socket path and GPU identity'))
    controller.apply()
    settle(controller)
    assert not controller.available and controller.operation_id is None
    assert 'secret' not in controller.message and 'GPU identity' not in controller.message
    assert 'no automatic retry' in controller.message
    assert len([op for op, _ in service.calls[calls_before:] if op == 'power_apply']) == 1
    assert ('power_failed', {'operation': 'power_apply', 'error': 'socket_timeout'}) in events


def test_close_preserves_applied_limit_and_sends_no_reset(setup):
    controller, view, service, now, events = setup
    make_available(controller)
    service.handler = lambda operation, fields: {
        'ok': True, 'gpu_uuid': GPU, 'state': 'applied', 'operation_id': 1,
        'previous_mw': 250_000, 'applied_mw': 240_000}
    controller.apply()
    settle(controller)
    calls = list(service.calls)
    controller.close()
    controller.close()
    assert service.calls == calls
    assert all(operation in ('power_status', 'power_apply') for operation, _ in service.calls)
    assert controller.closed


@pytest.mark.parametrize('value', [True, 0, -1, 0.00001, float('nan'), float('inf'), '250'])
def test_to_mw_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        to_mw(value)


@pytest.mark.parametrize('code', ['trial_guard_active', 'stale_power', 'outside_limits',
                                 'power_busy', 'recovery_pending', 'identity_mismatch',
                                 'private path and UUID', None, ['private']])
def test_rejected_apply_displays_and_logs_only_allowlisted_reason(setup, code):
    controller, view, service, now, events = setup
    make_available(controller)
    service.handler = lambda operation, fields: {'ok': False, 'error': code}
    controller.apply()
    settle(controller)
    expected = code if isinstance(code, str) and code in {
        'trial_guard_active', 'stale_power', 'outside_limits', 'power_busy',
        'recovery_pending', 'identity_mismatch'} else 'request_refused'
    assert f'[{expected}]' in controller.message
    assert ('power_failed', {'operation': 'power_apply', 'error': expected}) in events
    assert 'private' not in controller.message
    assert not controller.available and controller.operation_id is None
    if code == 'trial_guard_active':
        assert 'only 240 W or 250 W' in controller.message


def test_recovered_startup_connection_clears_obsolete_error_without_apply(setup):
    controller, view, service, now, events = setup
    service.handler = lambda operation, fields: (_ for _ in ()).throw(FileNotFoundError('private'))
    controller.pulse()
    settle(controller)
    assert controller.last_error == 'service_connection_unavailable'
    service.handler = service.default
    now[0] += 2.1
    controller.telemetry(gpu())
    controller.pulse()
    settle(controller)
    assert controller.available and controller.last_error is None
    assert controller.message.startswith('Power service connected.')
    assert all(op == 'power_status' for op, fields in service.calls)


def test_idle_status_does_not_erase_trial_rejection_instructions(setup):
    controller, view, service, now, events = setup
    make_available(controller)
    service.handler = lambda operation, fields: {'ok': False, 'error': 'trial_guard_active'}
    controller.apply()
    settle(controller)
    service.handler = service.default
    now[0] += 2.1
    controller.telemetry(gpu())
    controller.pulse()
    settle(controller)
    assert controller.available
    assert 'only 240 W or 250 W' in controller.message
    assert [op for op, fields in service.calls].count('power_apply') == 1


@pytest.mark.parametrize('capability', [None, False, 'true', True])
def test_power_with_active_curve_requires_explicit_service_capability(setup, capability):
    controller, view, service, now, events = setup
    controller.fan_active = lambda: True
    def reply(operation, fields):
        result = service.default(operation, fields)
        result['power_with_fan'] = capability
        return result
    service.handler = reply
    make_available(controller)
    assert view.enabled[-1][0] == (capability is True)
    view.value = 320
    controller.apply()
    settle(controller)
    applies = [fields for op, fields in service.calls if op == 'power_apply']
    assert bool(applies) == (capability is True)
    if applies:
        assert applies[0]['limit_mw'] == 320000
