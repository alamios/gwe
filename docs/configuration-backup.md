# Configuration backup and restore

GWE stores preferences and fan/overclock profiles in `gwe.db`. The current installed user Flatpak uses
`~/.var/app/com.leinardi.gwe/config/gwe/gwe.db`. Native builds normally use `$XDG_CONFIG_HOME/gwe/gwe.db`
(or `~/.config/gwe/gwe.db`). The development monitor uses the separate `gwe-monitor` directory.

## Backup performed

A consistent SQLite online backup of the installed Flatpak database was created in the private, Git-ignored
`.local-backups/` directory in this checkout. Its timestamped directory contains `gwe.db` and a manifest with
source path, method, SHA-256 and the successful `PRAGMA integrity_check` result. No profile values were printed.
The original was opened with SQLite `mode=ro`; the running GWE instance did not need to stop.
Only the GWE database was found in the inspected GWE configuration/data locations. This backup does not cover
system drivers, Xorg settings, Flatpak overrides or other application data.

The directory permissions are owner-only and the files are private. This is a local recovery copy on the
same disk, not protection against disk failure; copy it to the owner's normal backup storage before a system upgrade.
Do not commit databases or manifests containing personal paths.
On 2026-10-03, the explicitly supplied existing backup was checked again using a read-only SQLite
connection. `integrity_check` passed, and the requested startup curve passed the current manual-limit
validation. No database was overwritten or migrated. This does not include subsequent edits in old GWE.
A subsequent authorized online backup of the old Flatpak database was created in another private
timestamped directory on 2026-10-03 and passed integrity validation. The original backup and extra owner
copy remain untouched. The fresh copy is still on the same disk; place it on independent storage before
changing the distribution. The local startup profile source was not silently switched to the new backup.

## Make another online database backup

Set `source` and a new `target` path explicitly, then run with Python's standard library:

```python
import sqlite3
from pathlib import Path

source = Path.home() / '.var/app/com.leinardi.gwe/config/gwe/gwe.db'
target = Path('gwe-backup.db').resolve()  # Choose a private, persistent backup location.
with target.open('xb'):
    pass  # Refuse to overwrite an existing backup.
target.chmod(0o600)
with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as original:
    with sqlite3.connect(target) as backup:
        original.backup(backup)
        assert backup.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
```

Use SQLite's backup API while GWE is running rather than copying only the main file, which can miss
transactions held in a WAL file. The online backup represents a consistent database snapshot; subsequent
changes made in GWE are not included.

## Restore procedure (not performed)

1. Quit the GWE instance using this configuration before restoring. Confirm no instance is still using the database.
2. Verify the backup checksum against its manifest and run SQLite `PRAGMA integrity_check` on the backup.
3. Make a new backup of the current database. Move the stopped application's `gwe.db` and any associated
   `gwe.db-wal` / `gwe.db-shm` / `gwe.db-journal` files together into a separate recovery directory.
   Never mix old sidecar files with the restored database.
4. Copy the verified backup to the original `gwe.db` location and preserve owner-only write access.
5. Review the saved profile/autoload policy before running GWE: restoring the database also restores preferences,
   and startup may apply a saved profile. Only start it when the intended driver/GPU combination is ready.

Changing driver or GPU capability is not undone by restoring this database. Validate profiles separately after upgrades.

## Read-only fan-profile review

The [isolated profile-review window](fan-gui.md) accepts an explicit backup and reads it without application
initialization, migrations or database writes. It preserves saved points, hysteresis and silent mode,
reports incompatibilities and ignores autoload/current-profile preferences. Reading a backup is not
restoring or migrating it. Prefer a fresh verified online snapshot if profiles have changed since the
recorded backup. Review low-duty points against the live manual minimum before enabling a trial.

The [main-window service mode](main-window-service.md) also keeps backup profiles in memory. Its local
application preference database is separate and does not receive those private profiles. Startup ignores
saved selection/autoload and never acquires a fan lease.
