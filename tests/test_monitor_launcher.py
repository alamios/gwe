# SPDX-License-Identifier: GPL-3.0-or-later
"""Check isolation before any GTK or application import."""

import importlib.util
import os
from pathlib import Path


def test_launcher_overrides_existing_profile_paths_and_control_mode(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[1] / 'scripts' / 'run_monitor.py'
    spec = importlib.util.spec_from_file_location('monitor_launcher', script)
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    for key in ('XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_CACHE_HOME', 'GSETTINGS_SCHEMA_DIR'):
        monkeypatch.setenv(key, '/must-not-use')
    monkeypatch.setenv('GWE_MONITOR_ONLY', '0')
    build = launcher.prepare_environment(tmp_path)
    assert os.environ['GWE_MONITOR_ONLY'] == '1'
    assert Path(os.environ['XDG_CONFIG_HOME']) == build / 'config'
    assert Path(os.environ['XDG_DATA_HOME']) == build / 'data'
    assert Path(os.environ['XDG_CACHE_HOME']) == build / 'cache'
    assert Path(os.environ['GSETTINGS_SCHEMA_DIR']) == build
    assert (build / 'config').is_dir()
