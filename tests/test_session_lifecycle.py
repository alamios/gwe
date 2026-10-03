# SPDX-License-Identifier: GPL-3.0-or-later
"""Session ownership and privileged cleanup with replaced system boundaries."""
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from gwe import fan_daemon as daemon


@pytest.fixture
def session(tmp_path, monkeypatch):
    monkeypatch.setattr(daemon, 'RUNTIME', tmp_path)
    monkeypatch.setattr(daemon, 'trusted', lambda path: Path(path))
    monkeypatch.setattr(daemon, 'SESSION_OVERRIDE', tmp_path / 'override.conf')
    monkeypatch.setattr(daemon, 'SESSION_TEMPLATE', tmp_path / 'template.conf')
    (tmp_path / 'template.conf').write_text('trusted template')
    monkeypatch.setattr(daemon, 'process_identity', lambda pid: (1000, 123))
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout=b'active')
    monkeypatch.setattr(daemon.subprocess, 'run', run)
    return tmp_path, calls


def test_prepare_and_recover_restore_cooler_and_remove_only_known_override(session):
    path, calls = session
    daemon.prepare_session(42, 1000)
    record = path / 'session.json'
    assert record.stat().st_mode & 0o777 == 0o600
    assert daemon.session_record()['pid'] == 42
    (path / 'override.conf').write_text('trusted template')
    daemon.recover_session()
    assert not record.exists() and not (path / 'override.conf').exists()
    assert calls[-2:] == [['systemctl', 'daemon-reload'], ['systemctl', 'start', 'coolercontrold.service']]


def test_stopped_cooler_is_not_started(session, monkeypatch):
    path, calls = session
    monkeypatch.setattr(daemon.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=3, stdout=b'inactive'))
    daemon.prepare_session(42, 1000)
    monkeypatch.setattr(daemon.subprocess, 'run', lambda *a, **kw: pytest.fail('Unexpected service start'))
    daemon.recover_session()
    assert not (path / 'session.json').exists()


def test_unknown_override_retains_record_and_stopped_cooler(session):
    path, calls = session
    daemon.prepare_session(42, 1000)
    (path / 'override.conf').write_text('unknown override')
    with pytest.raises(RuntimeError):
        daemon.recover_session()
    assert (path / 'session.json').exists()
    assert (path / 'override.conf').read_text() == 'unknown override'
    assert len(calls) == 1


def test_failed_cooler_restart_retains_retry_record(session, monkeypatch):
    path, calls = session
    daemon.prepare_session(42, 1000)
    def failed(*args, **kw):
        raise RuntimeError('service failure')
    monkeypatch.setattr(daemon.subprocess, 'run', failed)
    with pytest.raises(RuntimeError):
        daemon.recover_session()
    assert (path / 'session.json').exists()


@pytest.mark.parametrize('marker', ['owned.json', 'power-pending.json', 'power-trial.json'])
def test_pending_gpu_recovery_blocks_session_preparation(session, marker):
    path, calls = session
    (path / marker).touch()
    with pytest.raises(RuntimeError):
        daemon.prepare_session(42, 1000)
    assert not (path / 'session.json').exists() and not calls


def test_foreign_owner_is_rejected_before_any_service_action(session):
    path, calls = session
    with pytest.raises(ValueError):
        daemon.prepare_session(42, 1001)
    assert not calls and not (path / 'session.json').exists()


@pytest.mark.parametrize('change', [{'pid': True}, {'uid': 0}, {'start': -1},
                                  {'cooler_active': 'yes'}, {'extra': 'private'}, {'version': True}])
def test_malformed_private_record_never_restores_services(session, change):
    path, calls = session
    daemon.prepare_session(42, 1000)
    record = path / 'session.json'
    row = json.loads(record.read_text())
    record.write_text(json.dumps({**row, **change}))
    with pytest.raises(ValueError):
        daemon.recover_session()
    assert record.exists() and len(calls) == 1


def test_pid_reuse_rejected_and_descriptor_closed(session, monkeypatch):
    path, calls = session
    daemon.prepare_session(42, 1000)
    read_fd, write_fd = os.pipe()
    monkeypatch.setattr(daemon.os, 'pidfd_open', lambda pid: read_fd)
    monkeypatch.setattr(daemon, 'process_identity', lambda pid: (1000, 999))
    try:
        with pytest.raises(RuntimeError, match='owner changed'):
            daemon.session_owner(1000)
        with pytest.raises(OSError):
            os.fstat(read_fd)
    finally:
        os.close(write_fd)


def test_real_pidfd_detects_owner_exit_without_gpu_access():
    import subprocess
    import select
    child = subprocess.Popen(['/usr/bin/python3', '-c', 'import time; time.sleep(30)'])
    fd = os.pidfd_open(child.pid)
    try:
        assert daemon.process_identity(child.pid)[0] == os.geteuid()
        assert not select.select([fd], [], [], 0)[0]
        child.terminate()
        child.wait(timeout=5)
        assert select.select([fd], [], [], 0)[0] == [fd]
    finally:
        os.close(fd)
        if child.poll() is None:
            child.kill()
            child.wait()
