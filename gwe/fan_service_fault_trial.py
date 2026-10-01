# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit installed-service SIGKILL experiment; imported only by the trial client."""
from pathlib import Path
import subprocess
import time

UNIT = 'gwe-fan-service.service'
RECORD = Path('/run/gwe-fan-service/owned.json')


def unit_state():
    output = subprocess.check_output(
        ['systemctl', 'show', UNIT, '-p', 'ActiveState', '-p', 'Result',
         '-p', 'ExecMainStatus', '-p', 'ControlPID'], text=True, timeout=2)
    return dict(line.split('=', 1) for line in output.splitlines() if '=' in line)


def automatic_snapshot():
    import pynvml as nvml
    nvml.nvmlInit()
    try:
        if nvml.nvmlDeviceGetCount() != 1:
            raise RuntimeError('Independent verification requires exactly one GPU')
        handle = nvml.nvmlDeviceGetHandleByIndex(0)
        if nvml.nvmlDeviceGetName(handle) != 'NVIDIA GeForce RTX 3090 Ti':
            raise RuntimeError('Unexpected verification device')
        if nvml.nvmlDeviceGetNumFans(handle) != 2:
            raise RuntimeError('Unexpected fan count')
        policies = [nvml.nvmlDeviceGetFanControlPolicy_v2(handle, fan) for fan in range(2)]
        if policies != [nvml.NVML_FAN_POLICY_TEMPERATURE_CONTINOUS_SW] * 2:
            raise RuntimeError('Automatic policy was not restored on both fans')
        return {'policies': policies, 'temperature_c': nvml.nvmlDeviceGetTemperature(handle, 0),
                'power_limit_w': nvml.nvmlDeviceGetPowerManagementLimit(handle) / 1000}
    finally:
        nvml.nvmlShutdown()


def kill_and_verify(*, state=unit_state, record=RECORD, snapshot=automatic_snapshot,
                    command=subprocess.run, clock=time.monotonic, sleep=time.sleep):
    if state().get('ActiveState') != 'active' or not record.exists():
        raise RuntimeError('Active service and ownership record required before fault injection')
    command(['sudo', '-n', 'systemctl', 'kill', '--kill-whom=all', '--signal=SIGKILL', UNIT],
            check=True, timeout=3)
    print('SIGKILL sent to the service and its control processes', flush=True)
    deadline = clock() + 20
    while clock() < deadline:
        result = state()
        if result.get('ActiveState') in ('failed', 'inactive') and result.get('ControlPID') == '0':
            if result.get('Result') != 'signal' or result.get('ExecMainStatus') != '9':
                raise RuntimeError('Unexpected service failure result')
            if record.exists():
                raise RuntimeError('Post-stop recovery left an unresolved ownership record')
            telemetry = snapshot()
            print('Post-stop recovery verified:', telemetry, flush=True)
            print('Expected service result: signal / SIGKILL; recovery completed', flush=True)
            return
        sleep(.1)
    raise RuntimeError('Systemd post-stop recovery deadline exceeded')
