# SPDX-License-Identifier: GPL-3.0-or-later
"""Persistent profile/editor integration over the supervised NVML service."""
from html import escape

from gwe.fan_main_controller import FanMainController
from gwe.fan_profiles import read_profiles


class NativeFanController(FanMainController):
    def __init__(self, view, database, limits, session, *, power=None, startup_profile_name=None):
        from gwe.model.fan_profile import FanProfile
        from gwe.model.current_fan_profile import CurrentFanProfile
        from gwe.interactor.settings_interactor import SettingsInteractor
        self.database = database
        self.desired = None
        self.last_fault = None
        self.applied_identifier = None
        if not FanProfile.select().where(FanProfile.type == 'auto').exists():
            FanProfile.create(type='auto', name='Automatic', read_only=True)
        profiles = read_profiles(database.database, allow_automatic=True)
        current = CurrentFanProfile.get_or_none()
        if not SettingsInteractor.get_bool('settings_native_startup_initialized', False):
            matches = [p for p in profiles if p.name == startup_profile_name] if startup_profile_name else []
            if len(matches) == 1 and not matches[0].problem:
                current = self._persist(matches[0].identifier)
            SettingsInteractor.set_bool('settings_native_startup_initialized', True)
        selected = next((p for p in profiles if current is not None and p.identifier == current.profile_id), profiles[0])
        restore = (selected.curve is not None and not selected.problem
                   and SettingsInteractor.get_bool('settings_load_last_profile', True))
        super().__init__(view, profiles, limits, session, allow_control=True, power=power,
                         startup_profile_name=None)
        self.selected = selected
        # The native database remembers an ID; duplicate editor names must not make restart ambiguous.
        self.startup_pending = restore

    @staticmethod
    def _persist(identifier):
        from gwe.model.current_fan_profile import CurrentFanProfile
        current = CurrentFanProfile.get_or_none()
        if current is None:
            return CurrentFanProfile.create(profile=identifier)
        current.profile = identifier
        current.save()
        return current

    def start(self):
        super().start()
        self.reload()

    def reload(self, identifier=None):
        if identifier is None:
            identifier = self.selected.identifier if self.selected else None
        self.profiles = read_profiles(self.database.database, allow_automatic=True)
        self.selected = next((p for p in self.profiles if p.identifier == identifier),
                             next((p for p in self.profiles if p.automatic), None))
        self.initializing = True
        try:
            self.view.refresh_fan_profile_combobox(
                [(p.identifier, escape(p.name)) for p in self.profiles] + [(-1, 'Add new profile…')],
                self.profiles.index(self.selected) if self.selected else None)
        finally:
            self.initializing = False
        self.view.refresh_service_curve(self.selected.curve if self.selected else None)
        if (self.session.state in ('active', 'starting') and self.applied_identifier is not None
                and self.applied_identifier not in {p.identifier for p in self.profiles}):
            self.desired = next((p for p in self.profiles if p.automatic), None)
            self.release()
        self.refresh()

    def select(self, identifier):
        if self.initializing or self.closed or self.desired is not None or self.pending_transition:
            return
        self.selected = next((p for p in self.profiles if p.identifier == identifier), None)
        self.startup_pending = False
        self.view.refresh_service_curve(self.selected.curve if self.selected else None)
        self.refresh()

    def problem(self):
        if self.selected is None:
            return 'Select a fan profile.'
        if self.selected and self.selected.automatic:
            return None
        return super().problem()

    def refresh(self):
        busy = (self.closed or self.pending_transition or self.desired is not None
                or self.session.state not in ('idle', 'active'))
        self.view.set_service_selection_enabled(not busy)
        self.view.set_apply_fan_profile_button_enabled(bool(
            self.telemetry_available and not busy and not self.problem()
            and not (self.power and self.power.operation_id is not None)))
        self.view.set_service_fan_hint(self.session.message if self.session.state == 'fault'
                                       else self.problem() or 'Apply the selected fan profile')
        self.view.show_service_control_fault(self.session.message if self.session.state == 'fault' else None)
        from gwe.model.fan_profile import FanProfile
        profile = FanProfile.get_or_none(id=self.selected.identifier) if self.selected else None
        self.view.set_edit_fan_profile_button_enabled(bool(profile and not profile.read_only and not self.closed))
        if self.session.state == 'fault' and self.last_fault != self.session.last_error:
            self.last_fault = self.session.last_error
            self.view.show_error_message_dialog('GPU control stopped', self.session.message)

    def apply(self):
        if (self.closed or not self.selected or not self.telemetry_available or self.problem()
                or self.session.state not in ('idle', 'active')
                or self.desired is not None or (self.power and self.power.busy)):
            return
        self.startup_pending = False
        self.desired = self.selected
        if self.session.state in ('active', 'starting'):
            self.release()
        self.refresh()

    def pulse(self):
        if self.closed:
            return False
        result = super().pulse()
        if (self.desired is not None and self.pending is None and self.session.state == 'idle'
                and not (self.power and self.power.busy)):
            selected, self.desired = self.desired, None
            self.selected = selected
            if selected.automatic:
                self._persist(selected.identifier)
                self.refresh()
            else:
                self.applied_identifier = selected.identifier
                super().apply()
        if self.session.state == 'active' and self.applied_identifier is not None:
            from gwe.model.current_fan_profile import CurrentFanProfile
            current = CurrentFanProfile.get_or_none()
            if current is None or current.profile_id != self.applied_identifier:
                self._persist(self.applied_identifier)
        return result

    def edit(self, presenter):
        from gwe.model.fan_profile import FanProfile
        profile = FanProfile.get_or_none(id=self.selected.identifier) if self.selected else None
        if profile and not profile.read_only:
            presenter.show_edit(profile)
