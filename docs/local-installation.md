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
`--installed`, without a root package update. By default select a curve and Apply explicitly; a named
startup curve requires the opt-in below. Closing restores fan ownership through the existing supervised recovery. Verified power
changes remain committed, including the owner's intentionally retained 320 W; close does not reset power.

The source installer now accepts `--startup-profile "Curve name"` to select a named startup curve in
private local configuration. It preserves that preference on subsequent updates; an empty string disables
it. With this opt-in, the continuous client selects exactly one compatible saved curve, waits for available
telemetry and requests normal service acquisition once. Missing/ambiguous/incompatible curves refuse
setup. Restore before acquisition cancels it; Restore after acquisition and faults never automatically
rearm it. Preview/monitor and bounded trials do not automatically apply curves. This does not enable
boot/login startup, power reapplication or profile database writes. Existing snapshots require an update
after the application is closed; the new behavior was not installed over the owner's running session.
Restore requests during an outstanding I/O renewal are now queued instead of silently dropped.

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
On 2026-10-03 the owner reported the installed application working and reported completing the
suspend/resume check. This is user-observed acceptance, without independently captured suspend/recovery
telemetry. Encoder/decoder readings stayed zero during reported accelerated playback, as they did in the
old application. This remains an inherited telemetry investigation, not a demonstrated new regression.
The named-startup GTK simulated check passed, including release and no automatic reacquisition. Smoke
windows now use a separate `.ServiceTrial.Smoke` identity/settings namespace so validation does not
activate the installed real control window. An earlier startup check failed; the subsequent diagnostic
check exposed a Restore click during pending I/O, which is covered by the queued-release correction.
The explicit existing backup was reopened read-only: integrity and the requested curve's current manual
limit compatibility passed. Real startup reapplication remains pending until the installed snapshot is updated.
Final validation passed with 489 tests on each interpreter. A workspace-only snapshot update, rollback
and reselect cycle also passed desktop validation without starting control; the active user installation
was left running unchanged.
After the owner closed it, the requested startup preference was installed and the actual installation
completed rollback/return without launching a controller. The later snapshot also includes the grouped
hardware-acceptance flag. Full simulated regression validation passed with 508 tests per interpreter;
real startup/close acceptance awaits user-terminal sudo authentication. See
[migration readiness](migration-readiness.md) for the one-command procedure and current system findings.
After the GPU became available, the video-counter lifecycle correction passed real-media/model and GTK
checks and was installed into the closed local snapshot. The requested startup preference was preserved.
The root service was not updated or started by this UI update; 330 W was retained. Real installed
startup/window-close acceptance still needs the user's sudo-authenticated command.
Target-OS/Wayland, suspend/resume and driver/host failure recovery remain pending.
