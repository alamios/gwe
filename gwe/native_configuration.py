# SPDX-License-Identifier: GPL-3.0-or-later
"""Create private writable configuration and preserve an explicitly configured profile source."""
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile


def configuration_base():
    return Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'gwe-nvml'


def external_fans(config):
    value = config.get('external_fans', False)
    if type(value) is not bool:
        raise ValueError('Invalid external fan preference')
    return value


def read_external_fans(base=None):
    path = (Path(base) if base is not None else configuration_base()) / 'config.json'
    config = json.loads(path.read_text())
    if config.get('version') != 1 or config.get('native') is not True:
        raise ValueError('Native configuration is not initialized')
    return external_fans(config)


def write_config(base, config):
    fd, temporary = tempfile.mkstemp(prefix='.config-', dir=base)
    try:
        with os.fdopen(fd, 'w') as output:
            json.dump(config, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, Path(base) / 'config.json')
    finally:
        Path(temporary).unlink(missing_ok=True)


def set_external_fans(enabled, base=None):
    """Persist next-launch intent only; never touch services or hardware here."""
    if type(enabled) is not bool:
        raise ValueError('Invalid external fan preference')
    base = Path(base) if base is not None else configuration_base()
    config = json.loads((base / 'config.json').read_text())
    if config.get('version') != 1 or config.get('native') is not True:
        raise ValueError('Native configuration is not initialized')
    external_fans(config)
    write_config(base, {**config, 'external_fans': enabled})


def prepare(base, *, config_home=None):
    base = Path(base)
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = base / 'config.json'
    config = json.loads(path.read_text()) if path.exists() else {'version': 1, 'startup_profile': None}
    if config.get('version') != 1:
        raise ValueError('Unsupported user configuration')
    external_fans(config)
    if config.get('native') is True:
        return config
    config_home = Path(config_home) if config_home is not None else Path(
        os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config')))
    target = config_home / 'gwe-native/gwe.db'
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if target.exists() or target.is_symlink():
        raise ValueError('Existing native database requires explicit review before importing')
    source = config.get('database')
    if source is not None:
        source = Path(source).resolve(strict=True)
        archive = base / 'native-import-backup'
        archive.mkdir(mode=0o700, exist_ok=False)
        shutil.copy2(path, archive / 'config-before.json')
        (archive / 'config-before.json').chmod(0o600)
        fd, temporary = tempfile.mkstemp(prefix='.import-', dir=target.parent)
        os.close(fd)
        try:
            with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as origin:
                with closing(sqlite3.connect(temporary)) as destination:
                    origin.backup(destination)
                    if destination.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                        raise ValueError('Imported configuration failed integrity validation')
            shutil.copy2(temporary, archive / 'profiles-before.db')
            os.link(temporary, target)  # Never overwrite a destination created concurrently.
        finally:
            Path(temporary).unlink(missing_ok=True)
    config = {**config, 'native': True, 'database': str(target), 'python': '/usr/bin/python3'}
    write_config(base, config)
    return config
