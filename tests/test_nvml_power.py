# SPDX-License-Identifier: GPL-3.0-or-later
"""Power limit transactions against a fake NVML device only."""
import json
import os
from pathlib import Path

import pytest

from gwe.nvml_power import PowerError, PowerRecord, apply, milliwatts, recover


GPU = 'GPU-test-only'
LOW = 100_000
HIGH = 480_000
BEFORE = 250_000
REQUESTED = 240_000


class FakeNvml:
    NVML_SUCCESS = 0

    def __init__(self, *, current=BEFORE, uuid=GPU):
        self.current = current
        self.uuid = uuid
        self.initialized = 0
        self.shutdowns = 0
        self.setter_calls = []
        self.reads = 0
        self.on_set = None
        self.after_set = None
        self.read_values = None

    def nvmlInit(self):
        self.initialized += 1

    def nvmlShutdown(self):
        self.shutdowns += 1

    def nvmlDeviceGetHandleByUUID(self, uuid):
        assert uuid == GPU
        return object()

    def nvmlDeviceGetUUID(self, handle):
        return self.uuid

    def nvmlDeviceGetPowerManagementLimitConstraints(self, handle):
        return [LOW, HIGH]

    def nvmlDeviceGetPowerManagementLimit(self, handle):
        self.reads += 1
        if self.read_values:
            return self.read_values.pop(0)
        return self.current

    def nvmlDeviceSetPowerManagementLimit(self, handle, value):
        self.setter_calls.append(value)
        if self.on_set:
            self.on_set(value)
        self.current = value
        if self.after_set:
            self.after_set(value)


@pytest.fixture
def setup(tmp_path):
    directory = tmp_path / 'power-state'
    directory.mkdir(mode=0o700)
    directory.chmod(0o700)
    return directory, PowerRecord(directory), FakeNvml()


@pytest.mark.parametrize('value', [True, False, 1.0, 0, -1, 0x1_0000_0000, '250000', None])
def test_milliwatts_accepts_only_positive_u32_integers(value):
    with pytest.raises(PowerError, match='invalid_power'):
        milliwatts(value)


@pytest.mark.parametrize('value', [1, 100_000, 250_000, 0xffff_ffff])
def test_milliwatts_accepts_positive_u32_integers(value):
    assert milliwatts(value) == value


def test_apply_is_uuid_bound_and_does_not_write_on_mismatch(setup):
    directory, record, nvml = setup
    nvml.uuid = 'GPU-some-other-device'
    with pytest.raises(PowerError, match='identity_mismatch'):
        apply(nvml, record, GPU, REQUESTED, BEFORE)
    assert nvml.setter_calls == []
    assert not record.pending.exists()
    assert nvml.initialized == nvml.shutdowns == 1


@pytest.mark.parametrize('requested', [LOW - 1, HIGH + 1])
def test_apply_rejects_value_outside_live_limits(setup, requested):
    _, record, nvml = setup
    with pytest.raises(PowerError, match='outside_limits'):
        apply(nvml, record, GPU, requested, BEFORE)
    assert nvml.setter_calls == []
    assert not record.pending.exists()


def test_apply_accepts_both_live_limit_edges(setup):
    _, record, nvml = setup
    assert apply(nvml, record, GPU, LOW, BEFORE)['applied_mw'] == LOW
    assert record.read(record.last)['outcome'] == 'applied'

    # Each transaction has a new previous value and a new private journal.
    assert apply(nvml, record, GPU, HIGH, LOW)['applied_mw'] == HIGH
    assert record.read(record.last)['previous_mw'] == LOW


def test_apply_rejects_stale_compare_and_swap_value(setup):
    _, record, nvml = setup
    nvml.current = 251_000
    with pytest.raises(PowerError, match='stale_power'):
        apply(nvml, record, GPU, REQUESTED, BEFORE)
    assert nvml.setter_calls == []
    assert not record.pending.exists()


def test_apply_rechecks_compare_and_swap_after_durable_journal(setup):
    _, record, nvml = setup
    # Initial read matches expected; another actor changes it during journal I/O.
    nvml.read_values = [BEFORE, BEFORE + 1]
    with pytest.raises(PowerError, match='stale_power'):
        apply(nvml, record, GPU, REQUESTED, BEFORE)
    assert nvml.setter_calls == []
    assert record.read(record.pending)['outcome'] == 'pending'
    assert recover(nvml, record, GPU)['state'] == 'rolled_back'
    assert nvml.current == BEFORE


def test_recovery_never_overwrites_a_third_party_power_change(setup):
    _, record, nvml = setup
    external = 260_000
    original_begin = record.begin

    def begin_then_external_change(uuid, previous, requested):
        row = original_begin(uuid, previous, requested)
        nvml.current = external
        return row

    record.begin = begin_then_external_change
    with pytest.raises(PowerError, match='stale_power'):
        apply(nvml, record, GPU, REQUESTED, BEFORE)
    with pytest.raises(PowerError, match='external_power_change'):
        recover(nvml, record, GPU)
    assert nvml.current == external
    assert nvml.setter_calls == []
    assert record.pending.exists()


def test_apply_persists_pending_journal_before_setter(setup):
    _, record, nvml = setup

    def inspect_journal(value):
        assert value == REQUESTED
        row = record.read(record.pending)
        assert row == {'version': 1, 'gpu_uuid': GPU, 'previous_mw': BEFORE,
                       'requested_mw': REQUESTED, 'outcome': 'pending'}

    nvml.on_set = inspect_journal
    result = apply(nvml, record, GPU, REQUESTED, BEFORE)
    assert result == {'state': 'applied', 'previous_mw': BEFORE, 'applied_mw': REQUESTED}
    assert not record.pending.exists()
    assert record.read(record.last)['outcome'] == 'applied'


def test_apply_requires_exact_readback_and_rolls_back_mismatch(setup):
    _, record, nvml = setup
    # Reads: preflight, CAS recheck, then verification returns a rounded/different value.
    nvml.read_values = [BEFORE, BEFORE, REQUESTED + 1]
    with pytest.raises(PowerError, match='verification_failed'):
        apply(nvml, record, GPU, REQUESTED, BEFORE)
    assert record.pending.exists()
    result = recover(nvml, record, GPU)
    assert result['state'] == 'rolled_back'
    assert nvml.current == BEFORE
    assert not record.pending.exists()


def test_permission_denial_during_setter_leaves_recoverable_journal(setup):
    _, record, nvml = setup

    def denied(value):
        raise PermissionError('simulated NVML permission denial')

    nvml.on_set = denied
    with pytest.raises(PermissionError):
        apply(nvml, record, GPU, REQUESTED, BEFORE)
    assert record.read(record.pending)['outcome'] == 'pending'
    nvml.on_set = None
    assert recover(nvml, record, GPU)['state'] == 'rolled_back'
    assert nvml.current == BEFORE


@pytest.mark.parametrize('when', ['before', 'after'])
def test_setter_exception_leaves_journal_and_recovery_restores_previous(setup, when):
    _, record, nvml = setup

    def fail(value):
        if when == 'after':
            nvml.current = value
        raise RuntimeError('simulated setter failure')

    nvml.on_set = fail
    with pytest.raises(RuntimeError, match='simulated setter failure'):
        apply(nvml, record, GPU, REQUESTED, BEFORE)
    assert record.read(record.pending)['previous_mw'] == BEFORE
    # The injected failure models one setter invocation; recovery gets a fresh attempt.
    nvml.on_set = None
    result = recover(nvml, record, GPU)
    assert result['state'] == 'rolled_back'
    assert nvml.current == BEFORE
    assert not record.pending.exists()


def test_recovery_does_not_set_when_device_already_has_previous_value(setup):
    _, record, nvml = setup
    row = record.begin(GPU, BEFORE, REQUESTED)
    assert recover(nvml, record, GPU)['state'] == 'rolled_back'
    assert nvml.setter_calls == []
    assert record.read(record.last) == {**row, 'outcome': 'rolled_back'}


def test_committed_value_survives_close_and_recovery_is_noop(setup):
    _, record, nvml = setup
    apply(nvml, record, GPU, REQUESTED, BEFORE)
    committed = record.read(record.last)
    assert committed['outcome'] == 'applied'
    assert committed['previous_mw'] == BEFORE
    assert committed['requested_mw'] == REQUESTED
    assert not record.pending.exists()

    nvml.setter_calls.clear()
    assert recover(nvml, record, GPU) == {'state': 'idle'}
    assert nvml.setter_calls == []
    assert nvml.current == REQUESTED
    assert record.read(record.last) == committed


def test_recovery_rejects_previous_value_outside_current_limits(setup):
    _, record, nvml = setup
    record.begin(GPU, 99_000, REQUESTED)
    with pytest.raises(PowerError, match='recovery_failed'):
        recover(nvml, record, GPU)
    assert record.pending.exists()
    assert nvml.setter_calls == []


def test_recovery_keeps_journal_when_rollback_cannot_be_verified(setup):
    _, record, nvml = setup
    record.begin(GPU, BEFORE, REQUESTED)
    nvml.setter_calls.clear()
    nvml.read_values = [REQUESTED, REQUESTED]
    with pytest.raises(PowerError, match='recovery_failed'):
        recover(nvml, record, GPU)
    assert record.pending.exists()


def test_record_read_rejects_invalid_permissions_and_corruption(setup):
    directory, record, _ = setup
    record.begin(GPU, BEFORE, REQUESTED)
    record.pending.chmod(0o640)
    with pytest.raises(PowerError, match='invalid_record'):
        record.read(record.pending)

    record.pending.unlink()
    record.pending.write_text('{invalid json')
    record.pending.chmod(0o600)
    with pytest.raises(json.JSONDecodeError):
        record.read(record.pending)

    record.pending.write_text(json.dumps({'version': True}))
    with pytest.raises((PowerError, TypeError)):
        record.read(record.pending)


def test_record_read_refuses_symlink(setup):
    directory, record, _ = setup
    target = directory / 'target.json'
    target.write_text('{}')
    target.chmod(0o600)
    record.pending.symlink_to(target.name)
    with pytest.raises(OSError):
        record.read(record.pending)
