# SPDX-License-Identifier: GPL-3.0-or-later
"""Last verified native power target, stored in the private desktop settings database."""
import json


class PowerPreference:
    KEY = 'settings_native_verified_power'

    def __init__(self, settings=None):
        if settings is None:
            from gwe.interactor.settings_interactor import SettingsInteractor
            settings = SettingsInteractor
        self.settings = settings

    def load(self):
        raw = self.settings.get_str(self.KEY, '')
        if not raw:
            return None
        value = json.loads(raw)
        if (not isinstance(value, dict) or type(value.get('version')) is not int or value['version'] != 1
                or not isinstance(value.get('gpu_uuid'), str) or not value['gpu_uuid']
                or type(value.get('limit_mw')) is not int or not 1 <= value['limit_mw'] <= 0xffffffff):
            raise ValueError('Invalid saved power preference')
        return value['gpu_uuid'], value['limit_mw']

    def save(self, uuid, limit_mw):
        self.settings.set_str(self.KEY, json.dumps(
            {'version': 1, 'gpu_uuid': uuid, 'limit_mw': limit_mw}, separators=(',', ':')))
