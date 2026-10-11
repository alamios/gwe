# Configuration backup and restore

## Stored data

| Location | Purpose |
| --- | --- |
| `$XDG_CONFIG_HOME/gwe-native/gwe.db` | Private profiles and preferences, including the verified power target |
| `$XDG_DATA_HOME/gwe-nvml/config.json` | Desktop launcher configuration |
| `$XDG_DATA_HOME/gwe-nvml/state/` | Session lock and bounded private diagnostics |
| `/etc/gwe-fan-service.json` | Privileged authorization: desktop UID and pinned GPU identity |
| `/run/gwe-fan-service/` | Runtime ownership and recovery journals |

XDG defaults are `~/.config` and `~/.local/share`. A fresh installation creates private configuration
and initializes the profile editor without a manually authored curve file. Root configuration does not
contain editable curves. Do not share databases, authorization files, GPU UUIDs or raw private logs.

An explicitly configured profile source is imported through an online SQLite backup with an integrity
check. Import preserves the source and archives the previous launcher configuration and database under
`gwe-nvml/native-import-backup/`. It refuses to overwrite an existing destination or recovery archive.
The writable native database is separate from the import source.

## Consistent database backup

Use SQLite's backup API, which includes committed data held in WAL files. Copying only a running
`gwe.db` file can omit transactions. Choose a new private target on persistent storage:

```python
from contextlib import closing
import os
from pathlib import Path
import sqlite3

config_home = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config')))
source = config_home / 'gwe-native/gwe.db'
target = Path('gwe-backup.db').resolve()
with target.open('xb'):
    pass  # Never overwrite an existing backup.
target.chmod(0o600)
with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as original:
    with closing(sqlite3.connect(target)) as backup:
        original.backup(backup)
        assert backup.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
```

Verify and retain a checksum alongside the backup. Preserve `config.json` and any import backups too.
An online backup is a consistent snapshot, not a copy of subsequent edits. Keep an additional copy on
independent storage; a Git-ignored directory on the same disk does not protect against disk failure.

## Restore

1. Quit GWE and confirm no process is using the database. Finish GPU recovery first.
2. Verify the backup checksum and SQLite `PRAGMA integrity_check` result.
3. Back up the current database. Move its main file and any `-wal`, `-shm` or `-journal` sidecars together
   into a separate recovery directory. Never combine old sidecars with the restored database.
4. Restore the verified backup with owner-only read/write permissions.
5. Review saved startup preferences before launching: restoring settings can also restore automatic
   application of a curve and power target. Validate them against the intended GPU and current limits.

A profile backup does not undo driver, kernel, distribution or GPU changes. Do not overwrite the import
source with the working database. The restore procedure requires its own verification before acceptance.
