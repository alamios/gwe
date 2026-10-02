# Local desktop installation

The optional user installation provides **GreenWithEnvy (NVML)** in the desktop menu, separate from
the installed Flatpak. It snapshots application sources and resources; moving or editing the repository
does not change an installed snapshot. It uses the existing prepared Python environment and reviewed
root-owned service. It installs no dependencies, starts no service, changes no GPU setting and adds no
boot/login startup. Python/native dependencies are not bundled; this is not a portable distribution package.

## Install or update

From the repository, with the prepared Python 3.12 interpreter and explicitly chosen backup:

```bash
python scripts/install_local.py --python /path/to/prepared/python3.12 --database "$BACKUP_DB"
```

The installer uses `$XDG_DATA_HOME` (default `~/.local/share`) for `gwe-nvml/` and
`applications/gwe-nvml-local.desktop`. The private mode-0600 configuration stores interpreter and backup
paths, without a GPU UUID or copied profiles. The backup remains the explicit read-only profile source;
this does not migrate or overwrite the Flatpak database. The interpreter path retains its virtual-environment
location instead of resolving its Python symlink into the system interpreter.

Open **GreenWithEnvy (NVML)** after closing the old GWE. A terminal opens for existing sudo authentication
and session diagnostics; keep it open for the session. The launcher reuses the reviewed service with
`--installed`, without a root package update. Select a curve and Apply explicitly; launch never applies a
saved curve. Closing restores fan ownership through the existing supervised recovery. Verified power
changes remain committed, including the owner's intentionally retained 320 W; close does not reset power.

Before sudo/recovery/service changes, a desktop-bus and Flatpak-process inspection refuses another
historical GWE or service-control window. Inspection failure also refuses launch. A lock prevents overlapping
local sessions sharing the same state directory. The session still temporarily stops CoolerControl and
restores its original state after verified recovery. These checks do not prevent starting another controller
later: do not reopen old GWE while this session owns the fans. Unregistered third-party controllers remain
outside the desktop application check; the service's existing process checks still apply.

## Retained versions and rollback

Run the same install command to update. Content-addressed snapshots include `SHA256SUMS`; existing
snapshot contents are checked before reuse. `current` is switched atomically and `previous` retains the
prior selected snapshot. Application settings/cache and private bounded logs live in `gwe-nvml/state/`,
outside snapshots, and survive update/rollback. Existing development logs in the repository are retained;
they are not copied into the installed state. The backup is not included in snapshots.

Close the local application before updating or rolling back. To select the previous snapshot:

```bash
python scripts/install_local.py --rollback
```

Rollback verifies both selected snapshots and swaps them; it does not alter the root service, its
configuration, power limits, profiles or state/logs. Repeated rollback toggles the two versions. Retained
release directories are not automatically deleted. Configuration and desktop-launcher replacement are
individual atomic file operations, not a transaction spanning all files; an interrupted installation can
require inspection before retry. An unknown existing installation directory or desktop entry is refused.

For removal, close the local session, remove only its desktop entry and `gwe-nvml/` directory after preserving
any wanted logs. Root service removal is a separate operation with its own recovery prerequisites.

## Current-host validation

On 2026-10-02, the complete simulated suite passed on Python 3.12 and 3.14 (478 tests each).
After adding corrupt-rollback refusal, all 25 focused installation/launcher/isolation tests passed on
both interpreters.
Tests cover snapshot independence, private configuration, preserved backup/logs, update/rollback,
modified-snapshot rejection and refusal before service operations when another controller is reported.
The live read-only desktop check detected the reopened old Flatpak and refused a new control session.
Desktop entry validation and shell syntax checks passed. Snapshot GUI validation uses simulated fan/power
control with real read-only telemetry and passed from the independent snapshot. Installation is not
additional hardware acceptance.
The separate user installation was prepared without launch. Its installed snapshot hashes and desktop
entry passed validation; the installed controller check refused the reopened old GWE. The experimental
root service remained inactive with a successful result. A real launch from the menu remains pending.
Target-OS/Wayland, suspend/resume and driver/host failure recovery remain pending.
