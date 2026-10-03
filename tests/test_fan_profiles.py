# SPDX-License-Identifier: GPL-3.0-or-later
import hashlib
import sqlite3

import pytest

from gwe.fan_profiles import read_profiles


@pytest.fixture
def database(tmp_path):
    path = tmp_path / 'profiles.db'
    with sqlite3.connect(path) as db:
        db.executescript('''
            CREATE TABLE fan_profile (id INTEGER PRIMARY KEY, name TEXT, type TEXT, vbios_silent_mode INTEGER);
            CREATE TABLE speed_step (id INTEGER PRIMARY KEY, profile_id INTEGER, temperature INTEGER, duty INTEGER);
            CREATE TABLE setting (key TEXT PRIMARY KEY, value BLOB);
            INSERT INTO fan_profile VALUES (1, 'Saved curve', 'fan_curve', 1);
            INSERT INTO speed_step VALUES (1, 1, 40, 30), (2, 1, 80, 100);
            INSERT INTO setting VALUES ('settings_hysteresis', '3');
        ''')
    return path


def test_preserves_points_silent_and_hysteresis_without_database_changes(database):
    digest = hashlib.sha256(database.read_bytes()).digest()
    profile, = read_profiles(database)
    assert profile.curve.points == ((40, 30), (80, 100))
    assert profile.curve.hysteresis == 3 and profile.curve.vbios_silent is True
    assert profile.problem is None
    assert hashlib.sha256(database.read_bytes()).digest() == digest


def test_missing_source_is_not_created(tmp_path):
    source = tmp_path / 'absent.db'
    with pytest.raises(FileNotFoundError):
        read_profiles(source)
    assert not source.exists()


@pytest.mark.parametrize('temperature,duty', [(40, 50), (20, 100), (80, 10), (80, 101)])
def test_invalid_or_ambiguous_saved_order_is_rejected(database, temperature, duty):
    with sqlite3.connect(database) as db:
        db.execute('UPDATE speed_step SET temperature=?, duty=? WHERE id=2', (temperature, duty))
    profile, = read_profiles(database)
    assert profile.curve is None and profile.problem


def test_below_manual_minimum_is_preserved_and_requires_review(database):
    with sqlite3.connect(database) as db:
        db.execute('UPDATE speed_step SET duty=0 WHERE id=1')
    profile, = read_profiles(database)
    assert profile.curve.points[0] == (40, 0)
    with pytest.raises(ValueError, match='explicit review'):
        profile.curve.validate_limits(30, 100)


def test_automatic_profile_is_never_a_curve_or_autoload(database):
    with sqlite3.connect(database) as db:
        db.execute("INSERT INTO fan_profile VALUES (2, 'Auto', 'auto', 0)")
        db.execute("INSERT INTO setting VALUES ('settings_load_last_profile', 1)")
        db.execute('CREATE TABLE current_fan_profile (profile_id INTEGER)')
        db.execute('INSERT INTO current_fan_profile VALUES (1)')
    profiles = read_profiles(database)
    assert profiles[0].curve is not None
    assert profiles[1].curve is None and profiles[1].problem


def test_native_editor_orders_points_by_temperature_and_exposes_automatic_mode(database):
    with sqlite3.connect(database) as db:
        db.execute("INSERT INTO fan_profile VALUES (2, 'Auto', 'auto', 0)")
        db.execute('INSERT INTO speed_step VALUES (3, 1, 60, 60)')
    curve, automatic = read_profiles(database, allow_automatic=True)
    assert curve.curve.points == ((40, 30), (60, 60), (80, 100))
    assert automatic.automatic and automatic.curve is None and automatic.problem is None
    assert read_profiles(database)[0].problem  # Explicit historical review retains its strict order guard.


@pytest.mark.parametrize('value', [b'4', 0])
def test_supported_hysteresis_encoding(database, value):
    with sqlite3.connect(database) as db:
        db.execute('UPDATE setting SET value=?', (value,))
    assert read_profiles(database)[0].curve.hysteresis == int(value)


@pytest.mark.parametrize('value', [b'private garbage', -1, 21, 2.5])
def test_invalid_hysteresis_cannot_silently_default(database, value):
    with sqlite3.connect(database) as db:
        db.execute('UPDATE setting SET value=?', (value,))
    with pytest.raises(ValueError, match='hysteresis'):
        read_profiles(database)


def test_missing_hysteresis_uses_historical_default(database):
    with sqlite3.connect(database) as db:
        db.execute('DELETE FROM setting')
    assert read_profiles(database)[0].curve.hysteresis == 2


def test_too_many_points_are_not_truncated(database):
    with sqlite3.connect(database) as db:
        db.executemany('INSERT INTO speed_step VALUES (?, 1, ?, 100)',
                       [(index, index + 80) for index in range(3, 34)])
    profile, = read_profiles(database)
    assert profile.curve is None and '32' in profile.problem
