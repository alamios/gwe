# SPDX-License-Identifier: GPL-3.0-or-later
import importlib.util
from pathlib import Path

import pytest


def acceptance():
    path = Path(__file__).resolve().parents[1] / 'scripts/check_installed_session.py'
    spec = importlib.util.spec_from_file_location('installed_acceptance', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_acceptance_preserves_current_power_instead_of_old_baseline():
    readings = {'policies': [0, 0], 'power_mw': 330000}
    acceptance().verify_after(readings, readings, returncode=0, service='inactive', result='success',
                              cooler_before='active', cooler_after='active')


@pytest.mark.parametrize('after,options', [
    ({'policies': [0, 1], 'power_mw': 330000}, {}),
    ({'policies': [0], 'power_mw': 330000}, {}),
    ({'policies': [], 'power_mw': 330000}, {}),
    ({'policies': [0, 0], 'power_mw': 320000}, {}),
    ({'policies': [0, 0], 'power_mw': 330000}, {'service': 'active'}),
    ({'policies': [0, 0], 'power_mw': 330000}, {'result': 'watchdog'}),
    ({'policies': [0, 0], 'power_mw': 330000}, {'cooler_after': 'inactive'}),
    ({'policies': [0, 0], 'power_mw': 330000}, {'returncode': 1}),
])
def test_acceptance_rejects_incomplete_recovery_or_power_change(after, options):
    parameters = dict(returncode=0, service='inactive', result='success',
                      cooler_before='active', cooler_after='active')
    parameters.update(options)
    with pytest.raises(RuntimeError, match='acceptance failed'):
        acceptance().verify_after({'policies': [0, 0], 'power_mw': 330000}, after, **parameters)
