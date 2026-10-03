# Native desktop candidate

The unified development package uses the original GTK window with NVML monitoring and supervised
fan/power control. Normal launch uses `gwe-nvml`, without a terminal or sudo. Only installation/setup
authorizes the root helper. Installed socket activation still requires hardware acceptance; the older
split v5 packages do not implement this desktop lifecycle.

## Configuration and import

The launcher creates private user configuration in `$XDG_DATA_HOME/gwe-nvml/config.json`
(`~/.local/share` by default). The writable profile/settings database is
`$XDG_CONFIG_HOME/gwe-native/gwe.db` (`~/.config` by default). A fresh installation initializes the
ordinary profile schema and editor; it needs no manually authored fan-curve JSON. Root authorization
contains only the desktop UID and pinned GPU identity, not editable curves.

When upgrading an existing development installation with an explicitly configured `database` source,
the first native launch performs an online SQLite copy and checks its integrity. It preserves the source,
archives the previous launcher JSON and a database copy in `gwe-nvml/native-import-backup`, and records
the new writable database. An existing destination or archive aborts import rather than overwriting it.
The source backup is never the runtime database. No owner's profiles have been imported during source
validation; synthetic fixtures verified this procedure and source preservation.

For rollback, quit the native application and wait for verified helper recovery first. Preserve the
native database separately before removing anything. Restore the earlier reviewed package/snapshot and
its archived launcher JSON; retain the original profile source. Do not copy an active database with an
ordinary filesystem copy or overwrite the historical source with the native database.

## Ordinary controls

- The original fan button opens the editor. Creation, edits and deletion update the profile list/plot.
  Apply validates the curve against the current hardware range; invalid legacy curves are not clamped.
- Applying an automatic profile releases the service lease and restores automatic fan control.
- The last successfully applied curve is stored in the database and reapplied once after fresh startup
  telemetry, subject to the existing "load last profile" preference. Choosing another curve without
  applying it does not change the applied/startup profile. Faults never rearm startup application.
  The saved profile ID is used at startup; duplicate names do not make native restoration ambiguous.
- Closing follows the minimize-to-tray preference. Hiding retains the curve and lease; explicit Quit
  releases them. The native login entry has its own `io.github.alamios.gwe.desktop` filename and launches
  `gwe-nvml --hide-window --delay`; it does not overwrite the historical GWE login entry.
  Enable login launch through native preferences and disable any historical GWE login entry first.
- Routine lease renewal and read-only power-status polling do not disable the controls. Actual writes,
  stale telemetry, transitions and faults retain their guards. Clock-offset control remains unsupported.
- Trial titles/status band and temporary Apply/Restore labels are absent. Actionable failures use ordinary
  dialogs; bounded private diagnostic logs remain in the launcher state directory.

## Appearance and credits

The desktop uses the host GTK theme and icon theme rather than forcing a Flatpak/runtime appearance.
An application-scoped stylesheet makes title controls inherit the normal foreground, gives them a
24-pixel minimum target with 16-pixel icons, and adds readable, underlined links. It does not change
the desktop theme or other applications. All three title buttons use the same light circular hover
and a slightly darker pressed state. These scoped rules take precedence over desktop-provided user
styles, which can otherwise reintroduce Breeze's red square on close. About retains Roberto Leinardi and Gabriele Musco as authors;
`alamios (since 1.0.0)` appears in a separate **Maintainer** section.

Standalone GTK checks passed under Breeze and Adwaita light/dark: opaque title icons at least 16 pixels
wide, link contrast above 4.5:1 against the theme background, and separate maintainer credits.
The revision `1.0.0~rc1-2` extracted package passed the native editor/tray/automatic graphical check
with system Python, isolated settings and synthetic control. These checks do not validate Wayland.

## Hung-interface follow-up

On 2026-10-04 the owner reported the installed rc1-3 interface unresponsive. Its log recorded
`ui_heartbeat_expired`; both fans were already automatic before intervention. SIGTERM did not exit
the GUI. Terminating only that GUI with SIGKILL allowed pidfd supervision to stop the helper with
Result=success, keep both fans automatic, preserve the observed 340 W and restore CoolerControl.
This is client-loss evidence while fans were already automatic, not a service-fault trial under control.
The next real startup/editor/tray/Quit check passed with the installed package and system Python,
including active Custom control, automatic recovery and unchanged power.

Review found a separate reproducible control-loop hazard: synchronous `Gtk.Dialog.run()` from a pulse
callback waits for acknowledgement and prevents that callback from renewing control. Native errors
now use visible, nonblocking notices that can be acknowledged or destroyed with the parent. The
expanded isolated GTK check holds a notice open for ten seconds, verifies continued simulated fan
renewals, then quits with the notice still open. This passed; the original hang's exact cause remains
unconfirmed because stack attachment was not permitted. Diagnostic logs are retained privately.

## Source validation

`python scripts/run_service_gui.py --smoke-native` uses a separate settings identity and a synthetic
service. The Python 3.12/X11 grouped check passed startup acquisition, editor opening/live plot changes,
tray hide/show retaining control, automatic-profile Apply and persisted automatic selection, profile
creation/deletion (including deleting the active profile) and closing with tray minimization disabled. Its only
real GPU operations are telemetry reads. Configuration tests verify private creation, online import,
edit persistence, repeated preparation and refusal to overwrite existing data.

The extracted native package also passed the earlier editor/tray/automatic check with system Python,
without a venv or user-installed modules. The expanded graphical check is rerun for the final candidate.

Final acceptance must use the actual unified installed package and system Python, including reopening,
socket activation and post-stop recovery. A grouped real check is prepared:

```bash
/usr/bin/python3 scripts/check_installed_session.py --native
```

Run it only after installing the reviewed candidate and closing other GWE applications. It requires an
applied custom profile and automatic policies before startup, opens the original editor without editing
data, checks tray hide/show retains the lease, and explicitly quits. It then independently verifies
automatic fans, unchanged power, restored CoolerControl state and an available activation socket.
The check does not save preference changes or change the profile selection. This startup/Quit check
passed on installed rc1-3. Privileged service fault trials and rc1-5 installed acceptance remain pending.
Wayland and Kubuntu 26.04 remain untested.
