#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Grouped installed desktop acceptance; fault injection requires operator sudo authentication."""
import os
from pathlib import Path
import subprocess
import sys
import time

from check_controllers import main as check_controllers
from check_installed_session import readings, state

UNIT = 'gwe-fan-service.service'
SOCKET = 'gwe-fan-service.socket'


def admin(*args):
    subprocess.run(['sudo', '-n', 'systemctl', *args], check=True, timeout=65)


def inject_fault(signal):
    if signal not in ('SIGKILL', 'SIGSTOP'):
        raise ValueError('Unsupported supervisor fault')
    # Bulk cgroup SIGKILL can also kill the newly started ExecStopPost process.
    # Target the supervisor; systemd owns teardown and independent recovery.
    admin('kill', '--kill-whom=main', f'--signal={signal}', UNIT)


def emergency_recover():
    """Recover retained journals only after the unit has no live control process."""
    if (state(UNIT) not in ('inactive', 'failed')
            or state(UNIT, 'MainPID') != '0' or state(UNIT, 'ControlPID') != '0'):
        raise RuntimeError('Service still running; manual recovery requires inspection')
    subprocess.run(['sudo', '-n', '/usr/bin/python3', '-I', '-B',
                    '/opt/gwe-fan-service/entry.py', 'recover'], check=True, timeout=65)


def verify_fault(before, after, *, result, expected, service, socket, cooler_before, cooler_after):
    if (not before['policies'] or len(after['policies']) != len(before['policies'])
            or any(after['policies']) or before['power_mw'] != after['power_mw']
            or result != expected or service not in ('inactive', 'failed')
            or socket != 'active' or cooler_before != cooler_after):
        raise RuntimeError('Native fault recovery not verified; inspect service before further control')


def fault(nvml, signal, expected):
    if check_controllers() or state(UNIT) not in ('inactive', 'failed'):
        raise RuntimeError('Quit GWE and finish recovery before fault acceptance')
    uuid, before = readings(nvml)
    if before['temperature_c'] >= 65 or not before['policies'] or any(before['policies']):
        raise RuntimeError('GPU must be cool and all fan policies automatic')
    cooler = state('coolercontrold.service')
    admin('reset-failed', UNIT)
    # Normal startup/Quit is checked separately. A deliberately interrupted
    # session must not also print that normal-completion check as FAIL.
    process = subprocess.Popen(['/usr/bin/gwe-nvml'])
    try:
        deadline = time.monotonic() + 30
        while True:
            _, current = readings(nvml, uuid)
            if current['temperature_c'] >= 70 or current['power_mw'] != before['power_mw']:
                raise RuntimeError('Thermal/power guard failed')
            if current['policies'] and all(policy == 1 for policy in current['policies']):
                break
            if process.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError('Startup curve did not acquire all fans')
            time.sleep(.2)
        inject_fault(signal)
        deadline = time.monotonic() + 65
        while state(UNIT) not in ('inactive', 'failed'):
            if time.monotonic() >= deadline:
                raise RuntimeError('Post-stop recovery timed out')
            time.sleep(.2)
        _, after = readings(nvml, uuid)
        verify_fault(before, after, result=state(UNIT, 'Result'), expected=expected,
                     service=state(UNIT), socket=state(SOCKET), cooler_before=cooler,
                     cooler_after=state('coolercontrold.service'))
        print(f'Service supervisor {signal}: PASS; fans automatic, current power unchanged, cooling state restored', flush=True)
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if state(UNIT) not in ('inactive', 'failed'):
            admin('kill', '--kill-whom=main', '--signal=SIGCONT', UNIT)
            admin('stop', UNIT)
        _, after = readings(nvml, uuid)
        if (not after['policies'] or any(after['policies']) or after['power_mw'] != before['power_mw']
                or state('coolercontrold.service') != cooler):
            emergency_recover()
            _, after = readings(nvml, uuid)
            if (after['policies'] != before['policies'] or after['power_mw'] != before['power_mw']
                    or state('coolercontrold.service') != cooler):
                raise RuntimeError('Final recovery unverified; inspect service before restarting GWE')
            print('Emergency recovery verified; this does not turn a failed fault test into a pass', flush=True)
        if after['policies'] != before['policies'] or after['power_mw'] != before['power_mw']:
            raise RuntimeError('Final recovery unverified; inspect service before restarting GWE')


def main():
    if os.geteuid() == 0:
        raise RuntimeError('Run as the desktop user, without prefixing sudo')
    if check_controllers() or state(UNIT) not in ('inactive', 'failed'):
        raise RuntimeError('Quit GWE before acceptance')
    # Authenticate only the two explicitly requested service faults, never run GTK as root.
    subprocess.run(['sudo', '-v'], check=True)
    subprocess.run(['/usr/bin/python3', str(Path(__file__).with_name('check_installed_session.py')),
                    '--native'], check=True, timeout=160)
    sys.path.insert(0, '/usr/share/gwe-nvml/vendor')
    import pynvml
    for signal, expected in (('SIGKILL', 'signal'), ('SIGSTOP', 'watchdog')):
        fault(pynvml, signal, expected)
    admin('reset-failed', UNIT)
    print('Native installed startup, Quit, SIGKILL and watchdog recovery: PASS', flush=True)


if __name__ == '__main__':
    main()
