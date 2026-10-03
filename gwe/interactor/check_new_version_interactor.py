# This file is part of gwe.
#
# Copyright (c) 2020 Roberto Leinardi
#
# gst is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# gst is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with gst.  If not, see <http://www.gnu.org/licenses/>.
import logging
from typing import Optional
from packaging.version import Version, InvalidVersion

import requests
import reactivex
from injector import singleton, inject
from reactivex import Observable

from gwe.conf import APP_VERSION

_LOG = logging.getLogger(__name__)


@singleton
class CheckNewVersionInteractor:
    URL = 'https://api.github.com/repos/alamios/gwe/releases/latest'

    @inject
    def __init__(self) -> None:
        pass

    def execute(self) -> Observable:
        _LOG.debug("CheckNewVersionInteractor.execute()")
        return reactivex.defer(lambda _: reactivex.just(self._check_new_version()))

    def _check_new_version(self) -> Optional[Version]:
        try:
            response = requests.get(self.URL, timeout=5, headers={'Accept': 'application/vnd.github+json'})
            if response.status_code != requests.codes.ok:
                return None
            release = response.json()
            if not isinstance(release, dict) or release.get('draft') or release.get('prerelease'):
                return None
            tag = release.get('tag_name')
            if not isinstance(tag, str):
                return None
            version = Version(tag.removeprefix('v'))
            return version if version > Version(APP_VERSION) else None
        except (requests.RequestException, ValueError, InvalidVersion):
            _LOG.debug('GitHub release check unavailable')
            return None
