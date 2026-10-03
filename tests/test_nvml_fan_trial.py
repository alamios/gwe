# SPDX-License-Identifier: GPL-3.0-or-later
"""No live driver calls: fixed fan experiment and recovery failure coverage."""
from types import SimpleNamespace

import pytest

from gwe.nvml_fan_trial import TrialError, exercise, observe, preflight, restore, selected, supervise


@pytest.fixture
def fake():
    state = {"policies": [0, 0], "speeds": [0, 0], "writes": [], "resets": []}

    def write(handle, fan, speed):
        state["writes"].append((fan, speed))
        state["policies"][fan] = 1
        state["speeds"][fan] = speed

    def reset(handle, fan):
        state["resets"].append(fan)
        state["policies"][fan] = 0

    return SimpleNamespace(
        state=state, NVML_TEMPERATURE_GPU=0, NVML_FAN_POLICY_MANUAL=1,
        NVML_FAN_POLICY_TEMPERATURE_CONTINOUS_SW=0,
        nvmlDeviceGetHandleByUUID=lambda uuid: "handle",
        nvmlDeviceGetUUID=lambda handle: "GPU-test",
        nvmlDeviceGetNumFans=lambda handle: 2,
        nvmlDeviceGetMinMaxFanSpeed=lambda handle: (30, 100),
        nvmlDeviceGetTemperature=lambda handle, sensor: 45,
        nvmlDeviceGetFanControlPolicy_v2=lambda handle, fan: state["policies"][fan],
        nvmlDeviceGetTargetFanSpeed=lambda handle, fan: state["speeds"][fan],
        nvmlDeviceGetFanSpeed_v2=lambda handle, fan: state["speeds"][fan],
        nvmlDeviceSetFanSpeed_v2=write, nvmlDeviceSetDefaultFanSpeed_v2=reset,
    )


def run(fake, **kwargs):
    exercise(fake, "GPU-test", emit=lambda state: None, sleep=kwargs.get("sleep", lambda _: None))


def test_success_restores_both(fake):
    run(fake)
    assert fake.state["writes"] == [(0, 40), (1, 40)]
    assert fake.state["resets"] == [0, 1]
    assert fake.state["policies"] == [0, 0]


@pytest.mark.parametrize("value", [None, -1, 60, float('nan')])
def test_invalid_temperature_never_writes(fake, value):
    fake.nvmlDeviceGetTemperature = lambda *args: value
    with pytest.raises(TrialError):
        run(fake)
    assert fake.state["writes"] == []


def test_stale_collection(fake):
    times = iter([0, 3])
    with pytest.raises(TrialError, match="two seconds"):
        observe(fake, "handle", clock=lambda: next(times))


@pytest.mark.parametrize("limits", [(41, 100), (0, 39), (100, 30), (30, 101)])
def test_bad_limits_never_write(fake, limits):
    fake.nvmlDeviceGetMinMaxFanSpeed = lambda handle: limits
    with pytest.raises(TrialError):
        run(fake)
    assert fake.state["writes"] == []


def test_existing_manual_policy_refused(fake):
    fake.state["policies"][1] = 1
    with pytest.raises(TrialError):
        preflight(fake, "handle")


def test_existing_higher_speed_refused(fake):
    fake.state["speeds"][0] = 50
    with pytest.raises(TrialError):
        preflight(fake, "handle")


def test_identity_mismatch(fake):
    with pytest.raises(TrialError):
        selected(fake, "GPU-other")
    assert fake.state["writes"] == []


@pytest.mark.parametrize("failed_fan", [0, 1])
def test_permission_or_partial_write_restores_all(fake, failed_fan):
    original = fake.nvmlDeviceSetFanSpeed_v2
    def write(handle, fan, speed):
        if fan == failed_fan:
            raise PermissionError()
        original(handle, fan, speed)
    fake.nvmlDeviceSetFanSpeed_v2 = write
    with pytest.raises(PermissionError):
        run(fake)
    assert fake.state["resets"] == [0, 1]
    assert fake.state["policies"] == [0, 0]


def test_telemetry_loss_during_manual_restores(fake):
    def sleep(_):
        fake.nvmlDeviceGetTemperature = lambda *args: None
    with pytest.raises(TrialError):
        run(fake, sleep=sleep)
    assert fake.state["policies"] == [0, 0]


def test_interrupt_restores(fake):
    def sleep(_):
        raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        run(fake, sleep=sleep)
    assert fake.state["policies"] == [0, 0]


def test_reset_failure_does_not_skip_other_fan(fake):
    original = fake.nvmlDeviceSetDefaultFanSpeed_v2
    def reset(handle, fan):
        if fan == 0:
            raise PermissionError()
        original(handle, fan)
    fake.nvmlDeviceSetDefaultFanSpeed_v2 = reset
    with pytest.raises(TrialError, match="fan 0 reset"):
        restore(fake, "GPU-test")
    assert fake.state["resets"] == [1]


def test_reset_success_without_policy_change_fails(fake):
    fake.state["policies"] = [1, 1]
    fake.nvmlDeviceSetDefaultFanSpeed_v2 = lambda *args: None
    with pytest.raises(TrialError, match="verification"):
        restore(fake, "GPU-test")


def test_timeout_kills_worker_before_parent_restores(fake, monkeypatch):
    events = []
    class Process:
        pid = None
        exitcode = None
        alive = False
        def start(self):
            self.pid = 123
            self.alive = True
        def join(self, timeout):
            events.append("join")
        def is_alive(self):
            return self.alive
        def kill(self):
            events.append("kill")
            self.alive = False
    original = fake.nvmlDeviceSetDefaultFanSpeed_v2
    def reset(handle, fan):
        events.append("reset")
        original(handle, fan)
    fake.nvmlDeviceSetDefaultFanSpeed_v2 = reset
    monkeypatch.setattr("gwe.nvml_fan_trial.signal.signal", lambda *args: None)
    with pytest.raises(TrialError, match="deadline"):
        supervise(fake, "GPU-test", SimpleNamespace(Process=lambda **kwargs: Process()))
    assert events == ["reset", "reset", "join", "kill", "join", "reset", "reset"]
