# SPDX-License-Identifier: GPL-3.0-or-later
import json
from pathlib import Path
import sqlite3

import pytest
from gwe.native_configuration import prepare as prepare_configuration


def prepare(base):
    return prepare_configuration(base, config_home=base / 'config')


def test_fresh_configuration_creates_private_runtime_path(tmp_path):
    config = prepare(tmp_path / 'new')
    assert config['native'] is True and config['startup_profile'] is None
    assert not Path(config['database']).exists()  # Normal ORM initialization owns schema creation.
    assert (tmp_path / 'new/config.json').stat().st_mode & 0o777 == 0o600
    assert prepare(tmp_path / 'new') == config


def test_online_profile_copy_keeps_source_and_recovery_copy(tmp_path):
    source = tmp_path / 'source.db'
    with sqlite3.connect(source) as connection:
        connection.execute('CREATE TABLE curve (name TEXT)')
        connection.execute('INSERT INTO curve VALUES (?)', ('Synthetic profile',))
    before = source.read_bytes()
    base = tmp_path / 'new'
    base.mkdir()
    config_path = base / 'config.json'
    previous = {'version': 1, 'database': str(source), 'startup_profile': 'Synthetic profile'}
    config_path.write_text(json.dumps(previous))
    config = prepare(base)
    assert source.read_bytes() == before
    with sqlite3.connect(config['database']) as connection:
        assert connection.execute('SELECT name FROM curve').fetchall() == [('Synthetic profile',)]
    assert (base / 'native-import-backup/profiles-before.db').read_bytes() == Path(config['database']).read_bytes()
    assert json.loads((base / 'native-import-backup/config-before.json').read_text()) == previous
    assert Path(config['database']).stat().st_mode & 0o777 == 0o600
    with sqlite3.connect(config['database']) as connection:
        connection.execute('INSERT INTO curve VALUES (?)', ('Edited profile',))
    assert prepare(base) == config
    assert source.read_bytes() == before


def test_import_refuses_existing_native_database(tmp_path):
    path = tmp_path / 'config/gwe-native/gwe.db'
    path.parent.mkdir(parents=True)
    path.write_bytes(b'preserve me')
    with pytest.raises(ValueError):
        prepare(tmp_path)
    assert path.read_bytes() == b'preserve me'


def test_invalid_source_never_replaces_configuration(tmp_path):
    source = tmp_path / 'bad.db'
    source.write_bytes(b'not SQLite')
    base = tmp_path / 'new'
    base.mkdir()
    original = json.dumps({'version': 1, 'database': str(source)})
    (base / 'config.json').write_text(original)
    with pytest.raises(sqlite3.DatabaseError):
        prepare(base)
    assert (base / 'config.json').read_text() == original
    assert not (base / 'config/gwe-native/gwe.db').exists()
