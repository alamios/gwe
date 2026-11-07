# This file is part of gwe.
#
# Copyright (c) 2018 Roberto Leinardi
#
# gwe is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# gwe is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with gwe.  If not, see <http://www.gnu.org/licenses/>.
import logging
import os
import re
from typing import Any, Dict

from gi.repository import Gtk
from injector import singleton, inject

from gwe.conf import SETTINGS_DEFAULTS
from gwe.interactor.settings_interactor import SettingsInteractor
from gwe.util.deployment import is_flatpak
from gwe.util.desktop_entry import set_autostart_entry, AUTOSTART_FILE_PATH
from gwe.runtime_mode import native_desktop
from gwe.native_configuration import read_external_fans, set_external_fans

_LOG = logging.getLogger(__name__)


class PreferencesViewInterface:
    def show(self) -> None:
        raise NotImplementedError()

    def hide(self) -> None:
        raise NotImplementedError()

    def refresh_settings(self, settings: Dict[str, Any]) -> None:
        raise NotImplementedError()

    def show_error(self, message: str) -> None:
        raise NotImplementedError()


@singleton
class PreferencesPresenter:
    @inject
    def __init__(self,
                 settings_interactor: SettingsInteractor,
                 ) -> None:
        _LOG.debug("init PreferencesPresenter ")
        self.view: PreferencesViewInterface = PreferencesViewInterface()
        self._settings_interactor = settings_interactor
        self._refreshing = False

    def show(self) -> None:
        self._init_settings()
        self.view.show()

    def _init_settings(self) -> None:
        settings: Dict[str, Any] = {}
        for key, default_value in SETTINGS_DEFAULTS.items():
            if isinstance(default_value, bool):
                if key == 'settings_launch_on_login' and not AUTOSTART_FILE_PATH.is_file():
                    self._settings_interactor.set_bool(key, False)
                settings[key] = self._settings_interactor.get_bool(key)
            elif isinstance(default_value, int):
                settings[key] = self._settings_interactor.get_int(key)
        if native_desktop() and os.environ.get('GWE_UI_SMOKE_TEST') != '1':
            try:
                settings['settings_external_fans'] = read_external_fans()
            except (OSError, ValueError):
                self.view.show_error('Could not read the fan-controller preference.')
        self._refreshing = True
        try:
            self.view.refresh_settings(settings)
        finally:
            self._refreshing = False

    def on_setting_changed(self, widget: Any, *args: Any) -> None:
        if self._refreshing:
            return
        if isinstance(widget, Gtk.Switch):
            value = args[0]
            key = re.sub('_switch$', '', widget.get_name())
            if key == 'settings_external_fans':
                if not native_desktop() or os.environ.get('GWE_UI_SMOKE_TEST') == '1':
                    return True
                try:
                    set_external_fans(value)
                except (OSError, ValueError):
                    self.view.show_error('Could not save the fan-controller preference. The previous setting is unchanged.')
                    return True
                return False
            self._settings_interactor.set_bool(key, value)
            if key == 'settings_launch_on_login' and not is_flatpak():
                set_autostart_entry(value)
        elif isinstance(widget, Gtk.SpinButton):
            key = re.sub('_spinbutton$', '', widget.get_name())
            value = widget.get_value_as_int()
            self._settings_interactor.set_int(key, value)
