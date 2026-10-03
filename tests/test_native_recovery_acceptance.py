# SPDX-License-Identifier: GPL-3.0-or-later
"""Reject incomplete fault recovery without calling NVML or systemd."""
import importlib.util
from pathlib import Path
import sys

import pytest


def validator():
    scripts = Path(__file__).resolve().parents[1] / 'scripts'
    sys.path.insert(0, str(scripts))
    try:
        spec = importlib.util.spec_from_file_location('native_recovery_check', scripts / 'check_native_recovery.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.verify_fault
    finally:
        sys.path.remove(str(scripts))


@pytest.mark.parametrize('expected', ['signal', 'watchdog'])
def test_fault_acceptance_preserves_current_power(expected):
    validator()({'policies': [0, 0], 'power_mw': 330000}, {'policies': [0, 0], 'power_mw': 330000},
                result=expected, expected=expected, service='failed', socket='active',
                cooler_before='active', cooler_after='active')


@pytest.mark.parametrize('after,overrides', [
    ({'policies': [0, 1], 'power_mw': 330000}, {}),
    ({'policies': [], 'power_mw': 330000}, {}),
    ({'policies': [0, 0], 'power_mw': 250000}, {}),
    ({'policies': [0, 0], 'power_mw': 330000}, {'result': 'success'}),
    ({'policies': [0, 0], 'power_mw': 330000}, {'service': 'active'}),
    ({'policies': [0, 0], 'power_mw': 330000}, {'socket': 'failed'}),
    ({'policies': [0, 0], 'power_mw': 330000}, {'cooler_after': 'inactive'}),
])
def test_fault_acceptance_rejects_missing_recovery(after, overrides):
    options = dict(result='watchdog', expected='watchdog', service='failed', socket='active',
                   cooler_before='active', cooler_after='active')
    options.update(overrides)
    with pytest.raises(RuntimeError, match='not verified'):
        validator()({'policies': [0, 0], 'power_mw': 330000}, after, **options)
