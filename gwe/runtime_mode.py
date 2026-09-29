# SPDX-License-Identifier: GPL-3.0-or-later
"""Development monitor mode, read before application construction."""

import os


def monitor_only():
    return os.environ.get("GWE_MONITOR_ONLY") == "1"


def config_namespace(package_name):
    return package_name + "-monitor" if monitor_only() else package_name


def application_id(base_id):
    return base_id + ".Monitor" if monitor_only() else base_id
