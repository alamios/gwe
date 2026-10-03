# SPDX-License-Identifier: GPL-3.0-or-later
"""Create private writable configuration and preserve an explicitly configured profile source."""
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile


def prepare(base, *, config_home=None):
    base = Path(base)
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = base / 'config.json'
    config = json.loads(path.read_text()) if path.exists() else {'version': 1, 'startup_profile': None}
    if config.get('version') != 1:
        raise ValueError('Unsupported user configuration')
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
    fd, temporary = tempfile.mkstemp(prefix='.config-', dir=base)
    try:
        with os.fdopen(fd, 'w') as output:
            json.dump(config, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return config
