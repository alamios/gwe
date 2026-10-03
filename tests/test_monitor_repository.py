# SPDX-License-Identifier: GPL-3.0-or-later
"""Repository boundary checks: monitor mode cannot reach X11 or subprocess writes."""

import pytest

from gwe.repository import nvidia_repository as module
from gwe.interactor.has_nvidia_driver_interactor import HasNvidiaDriverInteractor, HasNvidiaDriverResult


@pytest.fixture
def repository(monkeypatch):
    monkeypatch.setenv("GWE_MONITOR_ONLY", "1")
    def forbidden(*args, **kwargs):
        raise AssertionError("Monitor mode reached a legacy GPU operation")
    monkeypatch.setattr(module.display, "Display", forbidden)
    monkeypatch.setattr(module, "run_and_get_stdout", forbidden)
    monkeypatch.setattr(module.py3nvml, "nvmlInit", forbidden)
    return module.NvidiaRepository()


@pytest.mark.parametrize("operation,args", [
    ("set_fan_speed", (0, 30, True)),
    ("set_fan_speed", (0, 100, False)),
    ("set_overclock", (0, 0, 0, 0)),
    ("set_power_limit", (0, 200)),
])
def test_repository_rejects_all_writes(repository, operation, args):
    with pytest.raises(RuntimeError, match="disabled"):
        getattr(repository, operation)(*args)


def test_cleanup_does_not_reset_live_fans(repository):
    repository._gpu_count = 2
    repository.set_all_gpus_fan_to_auto()


def test_cleanup_releases_only_the_read_only_library_session(repository, monkeypatch):
    calls = []
    monkeypatch.setattr(repository._monitor._backend, 'close', lambda: calls.append('close'))
    repository.set_all_gpus_fan_to_auto()
    assert calls == ['close']


def test_startup_skips_x11_and_old_binding(repository, monkeypatch):
    monkeypatch.setattr(repository._monitor, "is_available", lambda: True)
    interactor = HasNvidiaDriverInteractor(repository)
    assert interactor._has_nvidia_driver() == HasNvidiaDriverResult.POSITIVE
    monkeypatch.setattr(repository._monitor, "is_available", lambda: False)
    assert interactor._has_nvidia_driver() == HasNvidiaDriverResult.NVML_MISSING


def test_repository_routes_status_to_monitor(repository, monkeypatch):
    expected = object()
    monkeypatch.setattr(repository._monitor, "get_status", lambda: expected)
    assert repository.get_status() is expected


def test_default_mode_keeps_x11_gate(monkeypatch):
    monkeypatch.delenv("GWE_MONITOR_ONLY", raising=False)
    repository = module.NvidiaRepository()
    monkeypatch.setattr(repository, "has_nv_control_extension", lambda: False)
    assert not repository.monitor_only
    assert HasNvidiaDriverInteractor(repository)._has_nvidia_driver() == HasNvidiaDriverResult.NV_CONTROL_MISSING


def test_service_mode_repository_cannot_write_even_without_monitor_flag(monkeypatch):
    monkeypatch.setenv('GWE_SERVICE_TRIAL', '1')
    monkeypatch.delenv('GWE_MONITOR_ONLY', raising=False)
    repository = module.NvidiaRepository()
    for operation, arguments in [('set_fan_speed', (0, 40, True)),
                                 ('set_overclock', (0, 0, 0, 0)), ('set_power_limit', (0, 200))]:
        with pytest.raises(RuntimeError, match='disabled'):
            getattr(repository, operation)(*arguments)
    repository.set_all_gpus_fan_to_auto()
