#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unprivileged fixed 250->240->250 W trial through the installed service."""
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gwe.fan_service import FanClient
from gwe.nvml_backend import NvmlBackend


def request(operation, **fields):
    client = FanClient('/run/gwe-fan-service/control.sock')
    try:
        return client.request(operation, **fields)
    finally:
        client.close()


def reading(uuid=None):
    report = NvmlBackend().read_snapshot(uuid)
    if len(report.get('gpus', [])) != 1:
        raise RuntimeError('Expected one GPU')
    gpu = report['gpus'][0]
    identity = gpu.get('uuid', {}).get('value')
    power = gpu.get('power_limit_w', {}).get('value')
    temperature = gpu.get('temperature_c', {}).get('value')
    if not identity or power is None or temperature is None or temperature >= 65:
        raise RuntimeError('Unusable preflight telemetry')
    return identity, round(power * 1000)


def apply_and_wait(uuid, desired, expected):
    result = request('power_apply', limit_mw=desired, expected_mw=expected, expected_uuid=uuid)
    if result.get('ok') is not True:
        raise RuntimeError('Service refused power request')
    operation_id = result.get('operation_id')
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        if result.get('gpu_uuid') != uuid or result.get('operation_id') != operation_id:
            raise RuntimeError('Power result identity changed')
        if result.get('state') == 'applied':
            if result.get('previous_mw') != expected or result.get('applied_mw') != desired:
                raise RuntimeError('Power result mismatch')
            if reading(uuid)[1] != desired:
                raise RuntimeError('Independent readback mismatch')
            print(f'Power verified by service and independent read: {expected / 1000:g} -> {desired / 1000:g} W', flush=True)
            return
        if result.get('state') != 'busy':
            raise RuntimeError('Power operation did not complete')
        time.sleep(.1)
        result = request('power_status')
    raise RuntimeError('Power operation timed out')


def main():
    uuid, previous = reading()
    if previous != 250000:
        raise RuntimeError('Baseline must be 250 W')
    # Root-owned trial guard must already exist; do not create it from the GUI.
    if not Path('/run/gwe-fan-service/power-trial.json').exists():
        raise RuntimeError('Missing independent trial recovery guard')
    status = request('power_status')
    if status.get('ok') is not True or status.get('gpu_uuid') != uuid or status.get('state') != 'idle':
        raise RuntimeError('Service not ready for this GPU')
    try:
        apply_and_wait(uuid, 240000, 250000)
        # Every request uses a fresh connection: disconnect must preserve commit.
        time.sleep(1)
        if reading(uuid)[1] != 240000:
            raise RuntimeError('Committed limit changed after disconnect')
        print('Verified committed limit survives client disconnect', flush=True)
        apply_and_wait(uuid, 250000, 240000)
    finally:
        # Uncertain results are not blindly retried. The wrapper stops the unit;
        # its independent trial guard then restores the original baseline.
        print('Trial ending; wrapper must stop service and verify guarded recovery', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'Power trial failed: {type(error).__name__}; stop service for guarded recovery', flush=True)
        raise SystemExit(1)
