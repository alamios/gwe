# SPDX-License-Identifier: GPL-3.0-or-later
import json
import stat

import pytest

from gwe.fan_gui_log import FanGuiLog


def test_log_contains_only_bounded_fields_and_no_private_data(tmp_path):
    path = tmp_path / 'diagnostics' / 'trial.log'
    log = FanGuiLog(path)
    log.record('failed', state='fault', operation='acquire', error='service_busy',
               profile='private name', uuid='private UUID', points=[[40, 35]],
               exception='private message', database='private path')
    row = json.loads(path.read_text())
    assert set(row) == {'time_utc', 'event', 'state', 'operation', 'error'}
    assert row['error'] == 'service_busy' and row['operation'] == 'acquire'
    assert row['time_utc'].endswith('+00:00')
    assert 'private' not in path.read_text()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_unknown_values_are_redacted(tmp_path):
    path = tmp_path / 'trial.log'
    log = FanGuiLog(path)
    log.record('private event', state='private state', operation='private path', error='private UUID')
    row = json.loads(path.read_text())
    assert row['event'] == 'failed' and row['state'] == 'fault'
    assert row['error'] == 'client_error' and row['operation'] == 'preview'
    assert 'private' not in path.read_text()


def test_rotation_retains_two_small_private_logs(tmp_path):
    path = tmp_path / 'trial.log'
    log = FanGuiLog(path, max_bytes=512)
    for _ in range(20):
        log.record('active', state='active', operation='renew')
    files = list(tmp_path.iterdir())
    assert sorted(item.name for item in files) == ['trial.log', 'trial.log.1']
    for item in files:
        assert item.stat().st_size <= 512
        assert stat.S_IMODE(item.stat().st_mode) == 0o600
        for line in item.read_text().splitlines():
            assert json.loads(line)['event'] == 'active'


def test_symlink_cannot_overwrite_another_file(tmp_path):
    source = tmp_path / 'original'
    source.write_text('keep')
    path = tmp_path / 'trial.log'
    path.symlink_to(source)
    with pytest.raises(OSError):
        FanGuiLog(path)
    assert source.read_text() == 'keep'
