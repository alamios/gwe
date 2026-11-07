# SPDX-License-Identifier: GPL-3.0-or-later
"""Isolated GTK/ORM integration, with no NVML session or installed service.

Run under xvfb-run for the real widget checks; no display means a skip.
"""
import os
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT = r'''
import json
import os
from pathlib import Path
from types import SimpleNamespace
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
if not Gtk.init_check()[0]:
    raise SystemExit(77)

from gwe.native_configuration import configuration_base, prepare, read_external_fans
base = configuration_base()
prepare(base)
from gwe.presenter.preferences_presenter import PreferencesPresenter
from gwe.view.preferences_view import PreferencesView
from gwe.interactor.settings_interactor import SettingsInteractor
from gwe.di import INJECTOR
from peewee import SqliteDatabase
from gwe.model.fan_profile import FanProfile
from gwe.model.current_fan_profile import CurrentFanProfile
from gwe.model.speed_step import SpeedStep
from gwe.model.setting import Setting
database = INJECTOR.get(SqliteDatabase)
database.create_tables([FanProfile, CurrentFanProfile, SpeedStep, Setting], safe=True)
builder = Gtk.Builder.new_from_file('data/ui/preferences.glade')
presenter = PreferencesPresenter(SettingsInteractor())
view = PreferencesView(presenter, builder)
errors = []
view.show_error = errors.append
presenter.show()
switch = builder.get_object('settings_external_fans_switch')
assert switch.get_visible() and not switch.get_active()
switch.set_active(True)
assert read_external_fans() is True
presenter.show()
assert switch.get_active() and not errors
assert Setting.get_or_none(key='settings_external_fans') is None

# Failed persistence must not change the widget or the previous disk preference.
import gwe.presenter.preferences_presenter as module
original = module.set_external_fans
def fail(value):
    raise PermissionError('simulated failure')
module.set_external_fans = fail
assert presenter.on_setting_changed(switch, False) is True
assert read_external_fans() is True and switch.get_active() and errors
module.set_external_fans = original
switch.set_active(False)
assert read_external_fans() is False
view.hide()

# A saved manual curve must never start in external mode, even with fresh telemetry.
profile = FanProfile.create(name='Saved curve')
SpeedStep.create(profile=profile, temperature=0, duty=40)
SpeedStep.create(profile=profile, temperature=80, duty=100)
CurrentFanProfile.create(profile=profile)
SettingsInteractor.set_bool('settings_load_last_profile', True)
from gwe.native_fan_controller import NativeFanController
from gwe.fan_gui_session import FanGuiSession
class View:
    def __init__(self):
        self.calls = {}
    def __getattr__(self, name):
        return lambda *args: self.calls.__setitem__(name, args)
def forbidden(*args):
    raise AssertionError('Fan socket opened')
screen = View()
session = FanGuiSession('unused', factory=forbidden, continuous=True)
power_events = []
power = SimpleNamespace(operation_id=None, busy=False, pulse=lambda: power_events.append('pulse'),
                        close=lambda: power_events.append('close'))
controller = NativeFanController(screen, database, (30, 100), session, power=power, allow_control=False)
try:
    controller.start()
    assert not controller.startup_pending
    controller.telemetry(True)
    controller.apply()
    controller.release()
    controller.edit(SimpleNamespace(show_edit=forbidden))
    for _ in range(3):
        controller.pulse()
    assert session.client is None and session.applied is None and session.resume_target is None
    assert not controller.power_fan_busy()
    assert screen.calls['set_apply_fan_profile_button_enabled'] == (False,)
    assert screen.calls['set_edit_fan_profile_button_enabled'] == (False,)
    assert screen.calls['set_service_selection_enabled'] == (False,)
    assert 'another application' in screen.calls['set_service_fan_hint'][0]
    controller.selected = next(p for p in controller.profiles if p.automatic)
    controller.apply()
    controller.pulse()
    assert CurrentFanProfile.get().profile_id == profile.id
finally:
    controller.close()
assert power_events == ['pulse'] * 4 + ['close']
assert session.client is None
database.close()
print('External cooling GTK preference, saved curve suppression, power scheduling and shutdown passed')
'''


def test_external_cooling_preferences_and_native_controller(tmp_path):
    environment = dict(os.environ, GWE_NATIVE_DESKTOP='1', GWE_SERVICE_TRIAL='1',
                       XDG_CONFIG_HOME=str(tmp_path / 'config'), XDG_DATA_HOME=str(tmp_path / 'data'),
                       XDG_CACHE_HOME=str(tmp_path / 'cache'))
    environment.pop('GWE_UI_SMOKE_TEST', None)
    result = subprocess.run([sys.executable, '-c', SCRIPT], env=environment, capture_output=True,
                            text=True, timeout=30, cwd=Path(__file__).resolve().parents[1])
    if result.returncode == 77:
        pytest.skip('GTK display unavailable; run this test under xvfb-run')
    assert result.returncode == 0, result.stdout + result.stderr
