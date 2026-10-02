# SPDX-License-Identifier: GPL-3.0-or-later
"""Development monitor mode, read before application construction."""

import os


def monitor_only():
    return os.environ.get("GWE_MONITOR_ONLY") == "1" or service_trial()


def service_trial():
    return os.environ.get("GWE_SERVICE_TRIAL") == "1"


def config_namespace(package_name):
    if service_trial():
        if os.environ.get('GWE_UI_SMOKE_TEST') == '1':
            return package_name + '-service-smoke'
        return package_name + "-service-trial"
    return package_name + "-monitor" if monitor_only() else package_name


def application_id(base_id):
    if service_trial():
        if os.environ.get('GWE_UI_SMOKE_TEST') == '1':
            return base_id + '.ServiceTrial.Smoke'
        return base_id + ".ServiceTrial"
    return base_id + ".Monitor" if monitor_only() else base_id
