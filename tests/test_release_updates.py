# SPDX-License-Identifier: GPL-3.0-or-later
from types import SimpleNamespace
import pytest
import requests
from gwe.interactor.check_new_version_interactor import CheckNewVersionInteractor


@pytest.mark.parametrize('payload,status,expected', [
    ({'tag_name': 'v1.0.0'}, 200, '1.0.0'),
    ({'tag_name': 'v0.15.9'}, 200, None),
    ({'tag_name': 'invalid'}, 200, None),
    ({'tag_name': 'v2.0.0', 'draft': True}, 200, None),
    ({'tag_name': 'v2.0.0-rc1', 'prerelease': True}, 200, None),
    ({'tag_name': None}, 200, None),
    ([], 200, None),
    ({}, 404, None),
    ({}, 403, None),
])
def test_release_check_uses_only_new_repository_and_stable_releases(monkeypatch, payload, status, expected):
    calls = []
    def get(url, **kwargs):
        calls.append((url, kwargs))
        return SimpleNamespace(status_code=status, json=lambda: payload)
    monkeypatch.setattr(requests, 'get', get)
    result = CheckNewVersionInteractor()._check_new_version()
    assert (str(result) if result else None) == expected
    assert calls == [('https://api.github.com/repos/alamios/gwe/releases/latest',
                      {'timeout': 5, 'headers': {'Accept': 'application/vnd.github+json'}})]


def test_release_check_network_failure_does_not_interrupt_startup(monkeypatch):
    def get(*args, **kwargs):
        raise requests.Timeout()
    monkeypatch.setattr(requests, 'get', get)
    assert CheckNewVersionInteractor()._check_new_version() is None
