# SPDX-License-Identifier: GPL-3.0-or-later
"""Power protocol and service arbitration tests using only simulated backends."""
import json
import pytest

from gwe.fan_service import FanService, decode


class FanBackend:
    def __init__(self):
        self.starts = []
        self.stops = 0
        self.state = 'idle'

    def start(self, curve):
        self.starts.append(curve)
        self.state = 'active'

    def stop(self):
        self.stops += 1
        self.state = 'idle'


class PowerBackend:
    """Service-facing double; deliberately has no NVML or device access."""

    def __init__(self, state='idle', uuid='GPU-test'):
        self.uuid = uuid
        self.result = {'state': state}
        self.starts = []

    def status(self):
        return {'ok': True, 'operation_id': 0, 'gpu_uuid': self.uuid, **self.result}

    def start(self, requested, expected):
        self.starts.append((requested, expected))
        self.result = {'state': 'busy'}
        return self.status()


def request(op, **fields):
    return {'version': 1, 'op': op, **fields}


@pytest.mark.parametrize(('limit', 'expected'), [
    (True, 200000), (200000.0, 200000), (0, 200000), (-1, 200000),
    (0x100000000, 200000), (200000, False), (200000, 200000.0),
    (200000, 0), (200000, -1), (200000, 0x100000000),
])
def test_power_apply_requires_exact_bounded_integer_milliwatts(limit, expected):
    packet = json.dumps(request('power_apply', expected_uuid='GPU-test', limit_mw=limit,
                                expected_mw=expected)).encode()
    with pytest.raises(ValueError, match='Invalid power request'):
        decode(packet)


@pytest.mark.parametrize('op', ['power_apply', 'power_status'])
def test_power_operations_reject_extra_or_missing_fields(op):
    packet = request(op)
    if op == 'power_apply':
        packet.update(expected_uuid='GPU-test', limit_mw=200000, expected_mw=200000)
    with pytest.raises(ValueError):
        decode(json.dumps({**packet, 'gpu_uuid': 'GPU-private'}).encode())
    if op == 'power_apply':
        packet.pop('expected_mw')
        with pytest.raises(ValueError):
            decode(json.dumps(packet).encode())


@pytest.mark.parametrize('uuid', ['', None, True, 7, ['GPU-test']])
def test_power_apply_requires_nonempty_uuid_string(uuid):
    packet = json.dumps(request('power_apply', expected_uuid=uuid,
                                limit_mw=250000, expected_mw=200000)).encode()
    with pytest.raises(ValueError):
        decode(packet)


def test_old_status_request_remains_valid_and_power_request_shape_is_strict():
    assert decode(b'{"version":1,"op":"status"}') == {
        'version': 1, 'op': 'status'}
    assert decode(b'{"version":1,"op":"power_status"}') == {
        'version': 1, 'op': 'power_status'}
    assert decode(b'{"version":1,"op":"power_apply","expected_uuid":"GPU-test",'
                  b'"limit_mw":250000,"expected_mw":200000}') == {
        'version': 1, 'op': 'power_apply', 'expected_uuid': 'GPU-test', 'limit_mw': 250000,
        'expected_mw': 200000}


def test_power_is_optional_and_reports_unavailable():
    service = object.__new__(FanService)
    service.power = None
    response = service.request(object(), decode(b'{"version":1,"op":"power_status"}'))
    assert response == {'ok': False, 'error': 'power_unavailable'}


def test_fan_acquire_is_blocked_while_power_is_busy_or_faulted():
    service = object.__new__(FanService)
    fan = FanBackend()
    service.lease = type('LeaseStub', (), {
        'request': lambda self, client, req: fan.start(req['curve'])})()
    power = PowerBackend()
    service.power = power
    acquire = decode(json.dumps(request(
        'acquire', points=[[40, 30], [80, 100]], hysteresis=2,
        vbios_silent=False)).encode())

    for state in ('busy', 'fault'):
        power.result = {'state': state}
        assert service.request(object(), acquire) == {'ok': False, 'error': 'power_busy'}
    assert fan.starts == []


@pytest.mark.parametrize('lease_state,owned', [
    ('active', True), ('stopping', False), ('fault', False),
    ('recovery_failed', False)])
def test_power_apply_is_blocked_while_fan_is_owned_or_not_idle(lease_state, owned):
    service = object.__new__(FanService)
    service.power = PowerBackend()
    service.lease = type('LeaseStub', (), {
        'owner': object() if owned else None, 'state': lease_state,
        'expire': lambda self: None})()
    client = object()
    command = decode(b'{"version":1,"op":"power_apply","expected_uuid":"GPU-test",'
                     b'"limit_mw":250000,'
                     b'"expected_mw":200000}')
    assert service.request(client, command) == {'ok': False, 'error': 'busy'}
    assert service.power.starts == []


def test_power_apply_requires_current_configured_gpu_identity():
    service = object.__new__(FanService)
    service.power = PowerBackend(uuid='GPU-configured')
    service.lease = type('LeaseStub', (), {
        'owner': None, 'state': 'idle', 'expire': lambda self: None})()
    command = decode(b'{"version":1,"op":"power_apply","expected_uuid":"GPU-other",'
                     b'"limit_mw":250000,"expected_mw":200000}')
    assert service.request(object(), command) == {
        'ok': False, 'error': 'identity_mismatch'}
    assert service.power.starts == []


def test_power_backend_receives_validated_values_without_real_device():
    # Construct the service with the narrow service-facing fake, so the test
    # exercises arbitration and argument forwarding without spawning NVML.
    service = object.__new__(FanService)
    service.power = PowerBackend()
    service.lease = type('LeaseStub', (), {
        'owner': None, 'state': 'idle', 'expire': lambda self: None})()
    command = decode(b'{"version":1,"op":"power_apply","expected_uuid":"GPU-test",'
                     b'"limit_mw":250000,'
                     b'"expected_mw":200000}')
    assert service.request(object(), command) == {
        'ok': True, 'operation_id': 0, 'gpu_uuid': 'GPU-test', 'state': 'busy'}
    assert service.power.starts == [(250000, 200000)]
