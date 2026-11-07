# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise login entries in temporary directories without starting GWE."""
import importlib.util
from pathlib import Path

import pytest
from xdg import BaseDirectory

from gwe.util.desktop.desktop_parser import DesktopParser


@pytest.fixture
def desktop_entry(tmp_path, monkeypatch):
    monkeypatch.setenv('GWE_NATIVE_DESKTOP', '1')
    monkeypatch.setattr(BaseDirectory, 'xdg_config_home', str(tmp_path / 'config'))
    monkeypatch.setattr(BaseDirectory, 'xdg_data_home', str(tmp_path / 'data'))
    path = Path(__file__).resolve().parents[1] / 'gwe/util/desktop_entry.py'
    spec = importlib.util.spec_from_file_location('isolated_desktop_entry', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('flag', ['true', 'false'])
def test_disable_removes_enabled_and_legacy_disabled_entries(desktop_entry, flag):
    path = desktop_entry.AUTOSTART_FILE_PATH
    path.parent.mkdir(parents=True)
    path.write_text(f'[Desktop Entry]\nType=Application\nExec=gwe-nvml\n'
                    f'X-GNOME-Autostart-enabled={flag}\n')
    unrelated = path.with_name('other.desktop')
    unrelated.write_text('[Desktop Entry]\nExec=other\n')

    desktop_entry.set_autostart_entry(False)
    desktop_entry.set_autostart_entry(False)

    assert not path.exists()
    assert unrelated.read_text() == '[Desktop Entry]\nExec=other\n'


def test_disable_without_existing_directory_creates_nothing(desktop_entry):
    desktop_entry.set_autostart_entry(False)
    assert not desktop_entry.AUTOSTART_FILE_PATH.parent.exists()


def test_enable_and_reenable_restore_native_login_command(desktop_entry):
    path = desktop_entry.AUTOSTART_FILE_PATH
    assert path.name == 'io.github.alamios.gwe.desktop'
    for _ in range(2):
        desktop_entry.set_autostart_entry(True)
        parser = DesktopParser(str(path))
        assert parser.get('Type') == 'Application'
        assert parser.get('Exec') == 'gwe-nvml --hide-window --delay'
        assert parser.get('Icon') == desktop_entry.ENTRY_ICON
        assert parser.get('X-GNOME-Autostart-enabled') == 'true'
        desktop_entry.set_autostart_entry(False)
        assert not path.exists()


def test_disable_reports_permission_failure(desktop_entry, monkeypatch):
    desktop_entry.set_autostart_entry(True)

    def denied(self, missing_ok=False):
        raise PermissionError('Simulated read-only autostart directory')

    with monkeypatch.context() as patch:
        patch.setattr(Path, 'unlink', denied)
        with pytest.raises(PermissionError):
            desktop_entry.set_autostart_entry(False)
    assert desktop_entry.AUTOSTART_FILE_PATH.is_file()
