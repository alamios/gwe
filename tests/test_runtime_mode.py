# SPDX-License-Identifier: GPL-3.0-or-later
import pytest
from gwe.runtime_mode import application_id, config_namespace, monitor_only


@pytest.mark.parametrize("value,enabled", [(None, False), ("0", False), ("1", True)])
def test_monitor_mode_is_explicit_and_isolates_state(monkeypatch, value, enabled):
    monkeypatch.delenv("GWE_MONITOR_ONLY", raising=False)
    if value is not None:
        monkeypatch.setenv("GWE_MONITOR_ONLY", value)
    assert monitor_only() is enabled
    assert config_namespace("gwe") == ("gwe-monitor" if enabled else "gwe")
    assert application_id("com.leinardi.gwe") == (
        "com.leinardi.gwe.Monitor" if enabled else "com.leinardi.gwe")


def test_service_trial_always_blocks_direct_writes_and_isolates_state(monkeypatch):
    monkeypatch.setenv('GWE_SERVICE_TRIAL', '1')
    monkeypatch.setenv('GWE_MONITOR_ONLY', '0')
    assert monitor_only()
    assert config_namespace('gwe') == 'gwe-service-trial'
    assert application_id('com.leinardi.gwe') == 'com.leinardi.gwe.ServiceTrial'
