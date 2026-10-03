# SPDX-License-Identifier: GPL-3.0-or-later
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def diagnostic():
    spec = importlib.util.spec_from_file_location('video_diagnostic', Path(__file__).resolve().parents[1] / 'scripts/check_video_engines.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Process:
    def __init__(self):
        self.returncode = None
        self.polls = 0
        self.terminated = False
    def poll(self):
        self.polls += 1
        if self.polls > 1 and not self.terminated:
            self.returncode = 0
        return self.returncode
    def terminate(self):
        self.terminated = True
        self.returncode = -15
    def wait(self, timeout=None):
        return self.returncode


def test_video_counter_comparison_and_shutdown(monkeypatch):
    module, process, calls = diagnostic(), Process(), []
    nvml = SimpleNamespace(nvmlInit=lambda: calls.append('init'), nvmlShutdown=lambda: calls.append('shutdown'),
                           nvmlDeviceGetHandleByUUID=lambda _: object(),
                           nvmlDeviceGetTemperature=lambda *_: 50,
                           nvmlDeviceGetEncoderUtilization=lambda _: (4, 100000))
    monkeypatch.setattr(module.subprocess, 'Popen', lambda *a, **k: process)
    backend = SimpleNamespace(read_snapshot=lambda _: {'gpus': [{'encoder_utilization': {'status': 'ok', 'value': {'percent': 5}}}]})
    monkeypatch.setattr(module, 'NvmlBackend', lambda _: backend)
    monkeypatch.setattr(module.time, 'sleep', lambda _: None)
    result = module.run_phase(['fake-ffmpeg'], None, nvml, 'simulated', 'encoder')
    assert result['raw_percent'] == 4 and result['backend_percent'] == 5
    assert calls == ['init', 'shutdown']


def test_video_thermal_stop_terminates_process(monkeypatch):
    module, process, calls = diagnostic(), Process(), []
    # Keep it running until cleanup explicitly terminates it.
    monkeypatch.setattr(process, 'poll', lambda: process.returncode)
    nvml = SimpleNamespace(nvmlInit=lambda: None, nvmlShutdown=lambda: calls.append('shutdown'),
                           nvmlDeviceGetHandleByUUID=lambda _: object(), nvmlDeviceGetTemperature=lambda *_: 80)
    monkeypatch.setattr(module.subprocess, 'Popen', lambda *a, **k: process)
    with pytest.raises(RuntimeError, match='thermal stop'):
        module.run_phase(['fake-ffmpeg'], None, nvml, 'simulated', 'encoder')
    assert process.terminated and calls == ['shutdown']
