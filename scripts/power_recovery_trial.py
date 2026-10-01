#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Two bounded installed-service faults; the wrapper owns cleanup and exclusivity."""
from pathlib import Path
import subprocess
import time

import power_service_trial as trial

UNIT = 'gwe-fan-service.service'
RUNTIME = Path('/run/gwe-fan-service')
ENTRY = '/opt/gwe-fan-service/entry.py'


def command(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=35).stdout.strip()


def verify_recovery(uuid):
    if any((RUNTIME / name).exists() for name in (
            'owned.json', 'power-pending.json', 'power-trial.json')):
        raise RuntimeError('Recovery record remains')
    actual, power = trial.reading(uuid)
    if actual != uuid or power != 250000:
        raise RuntimeError('Power baseline not restored')
    import pynvml as nvml
    nvml.nvmlInit()
    try:
        handle = nvml.nvmlDeviceGetHandleByUUID(uuid)
        if nvml.nvmlDeviceGetNumFans(handle) != 2 or any(
                nvml.nvmlDeviceGetFanControlPolicy_v2(handle, fan) != 0 for fan in range(2)):
            raise RuntimeError('Fan automatic policy not verified')
    finally:
        nvml.nvmlShutdown()


def wait_for_stop(expected, uuid, *, clock=time.monotonic, sleep=time.sleep):
    deadline = clock() + 25
    while clock() < deadline:
        state = command('systemctl', 'show', UNIT, '-p', 'ActiveState', '--value')
        if state in ('inactive', 'failed'):
            result = command('systemctl', 'show', UNIT, '-p', 'Result', '--value')
            if result != expected:
                raise RuntimeError('Unexpected service failure result')
            verify_recovery(uuid)
            return
        sleep(.2)
    raise RuntimeError('Service did not finish post-stop recovery in time')


def main():
    for index, (signal, result) in enumerate((('SIGKILL', 'signal'), ('SIGSTOP', 'watchdog'))):
        if index:
            command('sudo', '/usr/bin/python3', '-I', '-B', ENTRY, 'prepare-power-trial')
            command('sudo', 'systemctl', 'reset-failed', UNIT)
            command('sudo', 'systemctl', 'start', UNIT)
        uuid = trial.main(hold=True)
        command('sudo', 'systemctl', 'kill', '--kill-whom=all', f'--signal={signal}', UNIT)
        wait_for_stop(result, uuid)
        print(f'{signal}: PASS; 250 W restored, both fans automatic', flush=True)
    print('Power service recovery: PASS', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'Power recovery trial: FAIL ({type(error).__name__}); wrapper will recover', flush=True)
        raise SystemExit(1)
