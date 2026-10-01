# Main-window NVML service trials

The existing GWE main window now has an opt-in fan-service integration. It reuses the read-only NVML
telemetry repository, backup reader, bounded `FanGuiSession` and private diagnostic logger. The normal
X11 application and installed Flatpak retain their previous entry points. This is a source trial, not a
production release or continuous controller.

## Isolation and profile preservation

Use `scripts/run_service_gui.py`; it sets up local resources and configuration before application/DI imports.
Runtime state lives under `build/service-gui/`, configuration uses `gwe-service-trial`, and the GTK identity
ends in `.ServiceTrial`. The application's local preference/database initialization only touches that
separate namespace. An explicitly selected backup is read with the existing read-only reader; its curves
stay in memory and are not copied into the application's database. See [backup guidance](configuration-backup.md).

Startup never selects or applies a profile. Saved autoload/current-profile settings are ignored. The
selector contains the saved profiles, with no add/edit action; invalid/manual-limit-incompatible curves
remain blocked. Names are escaped for GTK markup. Curve points, saved hysteresis and firmware silent mode
are preserved. The main plot uses the saved hysteresis and endpoint duty rather than the historical
chart's forced 100% endpoint; firmware automatic operation below a silent threshold is not plotted as
a manual duty. The selected curve's hysteresis/silent flag are also shown in the Apply tooltip.

The service mode always forces the repository's direct-write guard, even if `GWE_MONITOR_ONLY` is unset.
Its telemetry status remains `read_only`: fan writes belong to the independent service, never the
repository. Power and overclock controls are disabled, and presenter action handlers also reject them.
Historical fan updates, autoload, profile persistence and settings actions are bypassed. The regular
monitor launcher explicitly clears an inherited service flag and continues to block all control.

## Preview

With the prepared Python 3.12 GTK environment active and a chosen backup path:

```bash
python scripts/run_service_gui.py --database "$BACKUP_DB"
```

Select a curve in the existing fan-profile selector. The chart and current NVML telemetry are visible;
control buttons remain disabled in preview. There is no service connection or GPU write on startup.

The telemetry adapter populates these fields when NVML returns a reading:

| Panel | Read-only fields |
| --- | --- |
| Info | VBIOS, PCIe current/maximum links, CUDA core count, memory bus width, memory/GPU and encoder/decoder utilization |
| Temp | Current temperature and critical, slowdown and shutdown thresholds |
| Power | Draw, limit, default, enforced, minimum and maximum (watts) |
| Clocks | Current and maximum graphics, SM, memory and video clocks (MHz) |
| Fan | Each fan's speed percentage and RPM |

An empty, insensitive field means that the adapter has no reading for it; it is not a control permission
indicator. Power/overclock setters remain disabled independently of telemetry availability. Preview also
disables curve Apply/Restore, while the profile selector and chart remain usable. Do not enable control
merely to populate missing telemetry fields.

## Prepared hardware procedure (main-window writes pending)

Keep installed GWE closed and avoid loads. Use the already installed bounded unit and the same recovery
procedure as the separate GUI trial:

```bash
(
    cleanup() {
        if sudo systemctl stop gwe-fan-service.service &&
           sudo test ! -e /run/gwe-fan-service/owned.json; then
            sudo systemctl start coolercontrold.service
        else
            echo 'Recovery pending; CoolerControl remains stopped'
        fi
    }
    trap cleanup EXIT
    sudo systemctl stop coolercontrold.service || exit
    sudo systemctl start gwe-fan-service.service || exit
    python scripts/run_service_gui.py --database "$BACKUP_DB" --allow-control
)
```

Select a compatible curve and press **Run curve for 10 seconds**. The existing Edit button becomes
**Restore automatic**, which releases only this client's trial. The information bar distinguishes starting,
active service ownership, restoration in progress, verified automatic recovery and faults. Selection is
locked while a request/trial is pending. No success is inferred merely from an accepted acquisition.

Ten seconds from acquisition trigger release; the installed unit still has a sixty-second total lifetime
and its existing temperature ceiling. UI work and socket I/O are separate. Only fresh GTK ticks schedule
renewals; stale UI ticks cannot resurrect a lease. Missing/erroring UI telemetry disables new acquisitions
and releases an existing trial. The service also validates its own fresh GPU telemetry independently.

Closing the main window quits this trial instead of minimizing to the tray. Window deletion, application
shutdown and SIGINT/SIGTERM close the serialized client connection; service-side recovery remains
independent. Socket disconnect is not displayed as verified restoration. See the
[service recovery evidence](fan-service.md) for live daemon/worker fault tests and remaining limits.

The private bounded log is `build/service-gui/logs/trial.log` with one rotated `.1` file. It uses the same
allowlisted fields, UTC timestamps and 0600 permissions as the [separate GUI log](fan-gui.md). No source
profile contents, UUIDs or raw exceptions are persisted. No service reinstall is required.

## Validation: 2026-10-01

244 automated tests pass on both Python 3.12 and 3.14, with the existing Reactivex warning. New tests cover
startup without selection/acquisition, profile preservation, markup escaping, explicit preview gating,
missing/lost telemetry, incompatible limits, locked selection, verified release, stale UI ticks, idempotent
close, isolated identities and direct-write rejection even without the monitor environment flag.

Python 3.12/X11 graphical checks passed:

```bash
python scripts/run_service_gui.py --database "$BACKUP_DB" --smoke-test
python scripts/run_service_gui.py --demo --smoke-service
python scripts/run_monitor.py --smoke-test
```

The private-backup check selected a saved curve with control disabled and no socket connection. The
simulated-service check exercised the actual main-window buttons through a temporary local socket:
apply/release, another acquisition with automatic ten-second completion, then closing while a third lease
was active. All three simulated ownerships were released. Its fan backend has no NVML calls; main-window
telemetry still performs real read-only NVML queries. A test assertion initially checked GTK close before
its asynchronous delete event; the check was corrected to inspect shutdown after the main loop exits.
The original monitor smoke check also passed. No GPU writes were performed for this integration.

The main-window-to-installed-service hardware trial is pending. The earlier separate GTK trial successes
do not substitute for it. Wayland, Python 3.14 GTK, suspend/resume, continuous operation and private-profile
migration remain unvalidated. The prior unexplained standalone GUI failure remains documented.

## Telemetry presentation check: 2026-10-01

Following an owner report of disabled Power/Clocks/Fan panels, read-only inspection confirmed that NVML
still supplies power draw and both fan percentages. The GTK smoke check was extended to compare those
fields' displayed text and sensitivity directly with the backend model. It passed using the private
backup in main-window preview, without a service connection or GPU writes. At that point clock readings, power-limit
metadata and fan RPM were unimplemented, not proven unsupported by the hardware.
No production behavior changed for this verification; that verification followed the 244-test suite.


The subsequent telemetry extension connects all fields listed above. On the current RTX 3090 Ti,
read-only queries succeeded in both Python environments. The full suite now passes 251 tests per
interpreter. A Python 3.12/X11 `--demo --smoke-test` also passed: it compares all six power fields,
eight clock fields and each fan's percentage/RPM text and sensitivity against the current model,
while checking that power and overclock controls remain disabled. Synthetic profiles were used;
no service connection, profile migration or GPU write was needed. Reopen the source window to load
the updated adapter; no installed-service or Flatpak update is required. Missing readings still appear
blank and insensitive, while valid zero readings remain visible. Main-window hardware control acceptance
and Wayland validation remain pending.


## Remaining screenshot differences: 2026-10-01

Comparison of the owner's original and updated private screenshots identified missing VBIOS, PCIe,
CUDA core count, memory bus width, encoder/decoder utilization and thermal thresholds. These now use
independent optional NVML reads and populate the existing UI models. The insensitive power slider also
reflects the reported range and current limit; displaying it does not enable writes. Preview curve actions
and overclock controls remain intentionally disabled. The original screenshots are preserved outside Git.

Live reads succeeded in Python 3.12 and 3.14 on driver 580.178.04: 10,752 CUDA cores, 384-bit memory bus,
maximum PCIe x16 Gen4, encoder/decoder 0%, and thermal thresholds 92/94/97 C. Current PCIe generation
was Gen1 in the recorded snapshot; current link state can differ between snapshots. Values are queried,
not copied from the reference image. The historical Critical label uses GPU_MAX, not shutdown temperature.

All 254 tests pass in each environment (the existing Reactivex deprecation warning remains). The Python
3.12/X11 GTK preview smoke check compares the added information, PCIe and thermal fields with the model
and verifies the power slider remains insensitive at the reported limit. No service connection or GPU
write occurred. Reopen the source window to load the changes; installed Flatpak/service updates are not needed.


## Main-window hardware follow-up: 2026-10-01

The owner ran the installed-service procedure with a saved curve, then reported fans remaining near 30%
after the service lifetime and reopening the UI. The redacted client log contains four ten-second
acquisitions followed by `recovery_verified`. Another acquisition near the end of the first service
lifetime lost its status connection and correctly reported `service_connection_unavailable`, without
claiming recovery for that attempt. Exact fan policy at that instant was not independently captured.

Two subsequent independent, read-only NVML snapshots showed automatic policy (0) on both fans, speeds
31%/32%, and temperatures 44 C then 43 C. The power limit was still 250 W. The trial service was inactive
with success result, its ownership marker was absent, and CoolerControl was active. These observations
do not support a currently retained manual curve. They do not identify why firmware continued spinning
the fans or exclude an earlier transient. No fan reset, service change or load was performed during this
investigation. Screenshots and raw private logs remain excluded from Git.

Automatic policy is not a promise of zero RPM: verify policy and ownership separately from fan speed.
A selected curve/chart also does not establish active service ownership. After the 60-second service
lifetime expires, close the window and rerun the full procedure before another acquisition. Main-window
normal timed release now has hardware evidence; explicit early release and closing during active ownership
still require separately identified hardware results. Wayland and continuous operation remain pending.


## Read-only zero-RPM investigation: 2026-10-01

Following the owner's report that the original automatic behavior was zero RPM at similar GPU
temperatures, CoolerControl configuration was inspected with authorization. Its `device-settings`
map was empty; no saved modes or active mode were present. `apply_on_boot` was enabled but no saved
channel settings were found to apply. Profiles existing in the file are not evidence of assignment.
The recent service journal contained a saved-settings application event but no setting-error events.
This disk inspection is not proof that no transient runtime control ever occurred.

A subsequent 60-second NVML observation (13 samples, five seconds apart) found both fans continuously
at 0% and 0 RPM, both policies automatic, and GPU temperature 50 C. Observed power draw was about
31–34 W. X11 GPUFanControlState was also zero. CoolerControl remained running. No setter, reset,
service restart, load or reboot was performed by the assistant during this investigation. No current
retained manual curve was observed. The transition back to zero was not captured; whether the owner
intervened between observations was asked separately. The cause and duration of the prior spinning
interval remain undetermined; do not present hysteresis or CoolerControl interference as established.


## Early-release hardware result: 2026-10-01

The owner confirmed no intervention between the earlier near-30% observation and the later zero-RPM
observation. A spontaneous return to zero is therefore supported, but its internal cause is still unknown.

The owner subsequently reported successful explicit Restore automatic and an immediate return to zero.
The latest log corroborates a release request about seven seconds after acquisition, before the ten-second
deadline, followed by `recovery_verified` and window close in idle state. Independent read-only follow-up
found both policies automatic, both reported speeds zero, the trial service inactive with success result,
CoolerControl active, and power limit still 250 W. No settings were changed during follow-up.
Closing the main window while ownership is active remains the next hardware acceptance check.


## Close-during-control hardware result: 2026-10-01

The owner performed the prepared procedure and closed the main window during active ownership.
The redacted log shows `active`, then `disconnected` and `window_closed` about 3.8 seconds later,
without an explicit release request or a client-side `recovery_verified` claim after closure.
Independent follow-up found both NVML policies automatic, both fans at 0% and 0 RPM, temperature
56 C and unchanged 250 W power limit. The service was inactive with success result, its ownership
marker absent, and CoolerControl active again. No settings were changed during verification.

This passes the complete documented window-close procedure, including its shell cleanup. It does not
isolate socket-disconnect recovery from the shell's service-stop/post-stop recovery path or measure
restoration latency. Earlier service client-disconnection tests provide separate evidence for that path.
Normal timed release, explicit early release and window close with cleanup now have current-host hardware
evidence. Continuous operation, suspend/resume and target Wayland/OS validation remain pending.
