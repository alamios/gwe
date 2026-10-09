# SPDX-License-Identifier: GPL-3.0-or-later
"""Saved native power targets use simulated service responses and temporary settings."""
import json
import sqlite3

import pytest

from gwe.power_preference import PowerPreference
from test_power_gui import GPU, Service, View, gpu, settle
from gwe.power_gui import PowerController


class Settings:
    def __init__(self, path):
        self.database = sqlite3.connect(path)
        self.database.execute('CREATE TABLE IF NOT EXISTS setting (key TEXT PRIMARY KEY, value BLOB)')

    def get_str(self, key, default):
        row = self.database.execute('SELECT value FROM setting WHERE key=?', (key,)).fetchone()
        return row[0].decode() if row else default

    def set_str(self, key, value):
        self.database.execute('INSERT OR REPLACE INTO setting VALUES (?, ?)', (key, value.encode()))
        self.database.commit()


@pytest.fixture
def saved(tmp_path):
    settings = Settings(tmp_path / 'settings.db')
    preference = PowerPreference(settings)
    preference.save(GPU, 320000)
    now = [10.0]
    service = Service()
    view = View(value=240)
    controller = PowerController(view, '/fake', allowed=True, factory=lambda path: service,
                                 clock=lambda: now[0], preference=preference)
    controller.telemetry(gpu())
    yield controller, service, now, preference
    controller.close()
    settings.database.close()


def applies(service):
    return [fields for operation, fields in service.calls if operation == 'power_apply']


def test_saved_limit_survives_database_reopen(tmp_path):
    path = tmp_path / 'settings.db'
    first = Settings(path)
    PowerPreference(first).save(GPU, 320000)
    first.database.close()
    second = Settings(path)
    assert PowerPreference(second).load() == (GPU, 320000)
    second.database.close()


def test_restore_uses_saved_target_and_fresh_compare_and_set_once(saved):
    controller, service, now, preference = saved
    settle(controller)
    assert applies(service) == [{'limit_mw': 320000, 'expected_mw': 250000, 'expected_uuid': GPU}]
    assert not controller.startup_pending
    now[0] += .3
    controller.pulse()
    settle(controller)
    assert len(applies(service)) == 1


@pytest.mark.parametrize('sample', [gpu(uuid='GPU-other'), gpu(maximum=300)])
def test_saved_identity_or_changed_limits_block_startup_write(saved, sample):
    controller, service, now, preference = saved
    controller.telemetry(sample)
    service.handler = lambda operation, fields: {
        'ok': True, 'gpu_uuid': sample.info.uuid, 'state': 'idle', 'operation_id': 0}
    settle(controller)
    assert not applies(service)
    assert 'Saved power was not restored' in controller.message
    assert not controller.startup_pending


def test_matching_live_limit_needs_no_setter(saved):
    controller, service, now, preference = saved
    controller.telemetry(gpu(limit=320))
    settle(controller)
    assert not applies(service)
    assert not controller.startup_pending


def test_restore_waits_for_fresh_telemetry_and_stable_fan_session(saved):
    controller, service, now, preference = saved
    now[0] += 3
    controller.pulse()
    assert not service.calls
    controller.telemetry(gpu())
    controller.fan_busy = lambda: True
    controller.pulse()
    assert not service.calls
    controller.fan_busy = lambda: False
    controller.fan_active = lambda: True
    settle(controller)
    assert not applies(service)
    service.handler = lambda operation, fields: dict(service.default(operation, fields), power_with_fan=True)
    now[0] += 2
    controller.telemetry(gpu())
    settle(controller)
    assert len(applies(service)) == 1


@pytest.mark.parametrize('response', [
    {'ok': False, 'error': 'recovery_pending'},
    {'ok': True, 'gpu_uuid': GPU, 'state': 'fault', 'operation_id': 0, 'error': 'recovery_failed'},
    {'ok': True, 'gpu_uuid': GPU, 'state': 'failed', 'operation_id': 0, 'error': 'driver_error'},
])
def test_status_failure_cancels_startup_even_if_service_recovers(saved, response):
    controller, service, now, preference = saved
    service.handler = lambda operation, fields: response
    settle(controller)
    service.handler = service.default
    now[0] += 2
    controller.telemetry(gpu())
    settle(controller)
    assert not applies(service)


def test_rejected_restore_is_not_retried_and_does_not_replace_saved_value(saved):
    controller, service, now, preference = saved
    service.handler = lambda operation, fields: (service.default(operation, fields)
        if operation == 'power_status' else {'ok': False, 'error': 'stale_power'})
    settle(controller)
    now[0] += 2
    controller.telemetry(gpu(limit=260))
    settle(controller)
    assert len(applies(service)) == 1
    assert preference.load() == (GPU, 320000)


def test_only_exact_verified_user_apply_replaces_saved_limit(saved):
    controller, service, now, preference = saved
    # User Apply before initial status cancels automatic restoration.
    controller.apply()
    settle(controller)
    service.handler = lambda operation, fields: {
        'ok': True, 'gpu_uuid': GPU, 'state': 'applied', 'operation_id': 1,
        'previous_mw': 250000, 'applied_mw': 240000}
    controller.apply()
    settle(controller)
    assert preference.load() == (GPU, 240000)


@pytest.mark.parametrize('state,applied', [('rolled_back', 250000), ('applied', 241000)])
def test_rollback_or_mismatched_verification_does_not_save(saved, state, applied):
    controller, service, now, preference = saved
    controller.apply()
    settle(controller)
    service.handler = lambda operation, fields: {
        'ok': True, 'gpu_uuid': GPU, 'state': state, 'operation_id': 1,
        'previous_mw': 250000, 'applied_mw': applied}
    controller.apply()
    settle(controller)
    assert preference.load() == (GPU, 320000)


@pytest.mark.parametrize('raw', ['bad json', json.dumps({'version': 1, 'gpu_uuid': GPU, 'limit_mw': True}),
                              json.dumps({'version': 2, 'gpu_uuid': GPU, 'limit_mw': 320000})])
def test_corrupt_preference_never_writes(saved, raw):
    controller, service, now, preference = saved
    preference.settings.set_str(preference.KEY, raw)
    settle(controller)
    assert not applies(service)
    assert 'saved_power_invalid' in controller.message


def test_storage_failure_preserves_hardware_success_and_reports_unsaved_limit(saved):
    controller, service, now, preference = saved
    controller.apply()
    settle(controller)
    def fail(*args):
        raise OSError('private path')
    preference.save = fail
    service.handler = lambda operation, fields: {
        'ok': True, 'gpu_uuid': GPU, 'state': 'applied', 'operation_id': 1,
        'previous_mw': 250000, 'applied_mw': 240000}
    controller.apply()
    settle(controller)
    assert controller.available and controller.operation_id is None
    assert 'Power verified' in controller.message and 'Could not save' in controller.message
    assert 'private' not in controller.message


def test_close_and_read_only_mode_cannot_restore(saved):
    controller, service, now, preference = saved
    controller.allowed = False
    controller.pulse()
    assert not service.calls
    controller.close()
    controller.allowed = True
    controller.pulse()
    assert not service.calls


def test_empty_preference_does_not_adopt_or_write_current_limit(saved):
    controller, service, now, preference = saved
    preference.settings.set_str(preference.KEY, '')
    settle(controller)
    assert not applies(service) and preference.load() is None
