#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""One supervised installed-startup/close acceptance; preserve the current power limit."""
import json
import os
from pathlib import Path
import subprocess


def state(unit, property='ActiveState'):
    return subprocess.check_output(['systemctl', 'show', unit, '-p', property, '--value'], text=True).strip()


def readings(nvml, uuid=None):
    nvml.nvmlInit()
    try:
        if uuid is None:
            if nvml.nvmlDeviceGetCount() != 1:
                raise RuntimeError('Acceptance requires exactly one GPU')
            uuid = nvml.nvmlDeviceGetUUID(nvml.nvmlDeviceGetHandleByIndex(0))
        handle = nvml.nvmlDeviceGetHandleByUUID(uuid)
        return uuid, {'temperature_c': nvml.nvmlDeviceGetTemperature(handle, 0),
                      'power_mw': nvml.nvmlDeviceGetPowerManagementLimit(handle),
                      'policies': [nvml.nvmlDeviceGetFanControlPolicy_v2(handle, index)
                                   for index in range(nvml.nvmlDeviceGetNumFans(handle))]}
    finally:
        nvml.nvmlShutdown()


def verify_after(before, after, *, returncode, service, result, cooler_before, cooler_after):
    if (returncode or not after['policies'] or any(after['policies'])
            or len(after['policies']) != len(before['policies'])
            or after['power_mw'] != before['power_mw'] or service != 'inactive'
            or result != 'success' or cooler_after != cooler_before):
        raise RuntimeError('Installed session acceptance failed; review service recovery before further writes')


def main():
    import pynvml
    prefix = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'gwe-nvml'
    config = json.loads((prefix / 'config.json').read_text())
    release = (prefix / 'current').resolve(strict=True)
    if config.get('version') != 1 or not config.get('startup_profile') or release.parent != prefix / 'releases':
        raise RuntimeError('Reviewed local installation and startup preference required')
    uuid, before = readings(pynvml)
    if before['temperature_c'] >= 80 or not before['policies'] or any(before['policies']):
        raise RuntimeError('Wait for temperature below 80 C and verified automatic fan policies')
    cooler = state('coolercontrold.service')
    environment = dict(os.environ, GWE_STATE_HOME=str(prefix / 'state'),
                       GWE_STARTUP_PROFILE=config['startup_profile'])
    result = subprocess.run(['bash', str(release / 'scripts/run_control_session.sh'), config['python'],
                             config['database'], '--installed', '--check-startup'], env=environment)
    _, after = readings(pynvml, uuid)
    verify_after(before, after, returncode=result.returncode, service=state('gwe-fan-service.service'),
                 result=state('gwe-fan-service.service', 'Result'), cooler_before=cooler,
                 cooler_after=state('coolercontrold.service'))
    print('Installed startup/close: PASS; fans automatic, power unchanged, cooling service restored')


if __name__ == '__main__':
    main()
