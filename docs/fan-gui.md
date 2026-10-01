# Isolated fan-profile review and service client

An experimental GTK3 window reads existing fan curves and can explicitly submit a ten-second trial to
the installed supervised service. This is a separate preparation tool, not integration into the historical
main presenter or a replacement for the installed Flatpak. Its application ID ends in `.FanTrial`.
It does not import application database initialization or legacy GPU writers. A subsequent
[main-window integration](main-window-service.md) reuses this client while keeping its own state isolated.

## Preserve profiles before control

Choose an explicit verified SQLite backup. Follow [backup guidance](configuration-backup.md) when making
a fresh snapshot. The reader opens SQLite with `mode=ro` and `query_only`, checks integrity and reads one
transaction. There is no migration, profile edit, saved-selection update or preference write. Nothing is
copied into the source monitor database. Names and points appear in the local window; terminal inspection
prints only anonymous counts and manual limits.

Point insertion order, hysteresis and firmware silent mode are preserved. The reader never sorts, clamps,
drops low-duty points or converts them to automatic operation. Duplicate/descending temperatures,
decreasing duties, invalid values, unsupported types and curves exceeding 32 points are blocked. All points
must fit the live manual range, including points below the silent-mode threshold. A saved zero or 25% point
is blocked on a GPU with a 30% minimum. Such a profile needs explicit review and a separately named
proposal; this tool does not rewrite it. Silent mode means firmware automatic control below the first
temperature, not a manual zero-percent write. The graph plots duty points; the silent-mode flag is separate.

Saved hysteresis is read as an integer or decimal ASCII value; the historical two-degree default is used
only when absent. Invalid hysteresis refuses review. Automatic profiles are displayed but cannot be
submitted as curves. Current-profile and autoload preferences never activate control.

## Read-only preview

From the checkout, in the prepared Python 3.12 GTK environment, replace the input with a chosen backup:

```bash
python scripts/run_fan_gui.py --database "$BACKUP_DB"
python scripts/run_fan_gui.py --database "$BACKUP_DB" --inspect-only
```

Without `--allow-control`, both control buttons stay disabled and no service connection is made. The
preview reads NVML capabilities for exactly one RTX 3090 Ti with two fans, without GPU setters.
Unexpected hardware or missing capabilities refuse review. The window shows the saved points, curve,
hysteresis, silent-mode flag and incompatibility reason.

An entirely synthetic preview uses no database or GPU access:

```bash
python scripts/run_fan_gui.py --demo --smoke-test
```

The three-second smoke test checks a selected profile, disabled controls and no service connection.
Demo, smoke-test and inspect-only cannot be combined with control.

## Bounded supervised GUI trial

Keep GWE closed and avoid loads. The GUI does not run sudo or manage system services. With the prepared
Python environment active, use the existing installed trial service and this cleanup procedure:

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
    python scripts/run_fan_gui.py --database "$BACKUP_DB" --allow-control
)
```

Opening the window does not acquire control. Select a compatible curve and press **Run selected curve
for 10 seconds**. The window waits for verified service ownership, renews with fresh GTK ticks and releases
after ten seconds from acquisition. **Restore automatic** releases this client's own trial and cannot
reset another controller. Restoration is displayed only after the service reports verified idle. Closing
the window disconnects its owner socket and initiates independent service recovery. Check policies and
shutdown independently afterward, following [service validation](fan-service.md).

Socket calls run in a serialized I/O thread, with at most one pending task. Only the GTK event loop
schedules renewals, approximately once per second. A frozen UI stops scheduling; stale queued ticks or
a gap over 2.5 seconds close the connection and latch a fault. A background thread cannot keep renewing
indefinitely after a stalled window. The absolute trial deadline uses CLOCK_BOOTTIME, including suspended
time. The service's lease, watchdog, 60 C ceiling and sixty-second lifetime remain in force. This is not
suspend/resume integration or continuous operation.

Errors, lost ownership and timeouts close the socket and disable new trials until review/relaunch. Recovery
polling has a ten-second limit. A disconnected socket reports unverified recovery, not successful restoration.
No direct fan, power or clock writes occur in the GUI. Normal exit cannot guarantee recovery from an
unresponsive driver or host. Service code and installed packaging need no changes for this client.

## Validation: 2026-10-01

217 tests pass on both Python 3.12 and 3.14, with the existing Reactivex deprecation warning. New tests
cover unchanged database content, preserved points/settings, malformed profiles, manual limits, missing
sources, busy services, renewal, release, ten-second termination, stale UI ticks, lost ownership, bounded
recovery and redacted errors. A real local socket test connects the UI session to a simulated service backend
and checks acquisition and verified recovery; no hardware writes occur in automated tests.

The synthetic GTK preview and private-backup read-only GTK preview passed on Python 3.12/X11. Read-only
validation of that backup against current NVML limits also succeeded. Private contents are not recorded
here. The subsequent GUI hardware result is recorded below. Python 3.14 GUI, Wayland, continuous
operation, editing, profile migration and historical main-window integration remain pending.

## Saved-curve GUI hardware trial: 2026-10-01

The owner used the GTK client from `c2426a1` against the unchanged installed service bundle (`626c8ae`)
and selected the compatible saved curve from the private backup. The owner reported a failed first
attempt and a successful second attempt: fan acceleration was audible, followed by the window message
`Both fans restored to automatic; recovery verified by the service.` No duty trace, temperature trace
or elapsed timing was captured. The owner subsequently identified the first failure message as
`Trial stopped. Automatic recovery is not verified; check the service.` This identifies a failure in the
GUI control session rather than profile-reader startup; its cause and exact operation remain unknown.
The message does not prove restoration failed: the client had not verified it. This is a successful second
run with an unresolved first failure, not evidence of uniformly reliable GUI operation.

Independent read-only follow-up confirmed both NVML policies zero (automatic), temperature 54 C,
power limit 250 W, service inactive/static with `Result=success`, `ExecMainStatus=0`, `ControlPID=0`,
no ownership record and CoolerControl active again. Recent filtered service events showed two clean
shutdowns but no cause for the first GUI failure. Do not infer a temperature rejection, service-lifetime
expiry or UI stall without evidence. No private profile names/points are recorded here and no profiles
were edited or migrated.

## Diagnostic follow-up

The GUI now includes a bounded local diagnostic code and operation in failure messages. Known service
refusals, non-idle service state, socket absence/permissions/timeouts, stale GTK ticks, lost ownership,
backend fault and unverified recovery can be distinguished. Unknown protocol text and exception messages
are not shown. The controller still closes on failure, stops renewals and requires review/relaunch; this
change does not automatically retry or bypass recovery. Existing generic failure messages cannot be
retrospectively diagnosed from the second successful run.

Seven new simulated tests check connection-error redaction, allowed/refused protocol codes, UI-stall
classification and backend-fault classification. Full regression now passes 224 tests on both Python
versions, with the existing Reactivex warning. The synthetic GTK preview smoke check also passes.
The owner subsequently ran two successful GUI trials with these diagnostics available, as recorded
below. The installation bundle needs no update because only the unprivileged repository client changed.

## Provisional GUI acceptance and retained diagnostics: 2026-10-01

Following the diagnostic update, the owner reported two consecutive successful GUI trials and accepted
this bounded behavior provisionally. Independent read-only follow-up confirmed both fan policies
automatic, temperature 47 C, power limit 250 W, unit inactive/static with `Result=success`,
`ExecMainStatus=0`, `ControlPID=0`, no ownership record and CoolerControl active. This does not explain
the first generic failure or establish continuous-operation readiness. No further GPU-writing test was
requested to complete this acceptance record.

At the owner's request, future GUI launches now retain a local diagnostic log at
`build/fan-gui/trial.log`, with one rotated file `trial.log.1`. Each file is limited to approximately 64 KiB;
old rotated content is replaced. The directory is mode 0700 and files are mode 0600. The existing `build/`
Git exclusion covers them. This log is diagnostic retention, not a permanent audit archive; copy both
files to private backup storage before clearing build output or if preserving an old incident is needed.

JSON lines contain UTC time, event, state, operation and an allowlisted error code. They record opening,
acquisition, starting/active control, release, recovery verification, disconnect, failures and closure.
They contain no database/socket paths, profile identifiers/names/points, GPU UUIDs, raw exceptions or
arbitrary server messages. A disconnect event does not assert recovery; only service-verified idle emits
`recovery_verified`. GTK never autonomously renews control merely to keep a log running.

Read the current log locally after an incident:

```bash
tail -n 40 build/fan-gui/trial.log
```

An unavailable log at startup prevents opening the control window. A later write failure does not interrupt
release/disconnect or independent recovery; the window reports that logging is unavailable. No past
hardware run has been reconstructed as log events. The first unexplained failure remains in this record.

Seven new tests cover field redaction, permissions, bounded rotation, symlink refusal, state transitions,
verified recovery and disk-write failure during release. Full regression passes 231 tests per interpreter
on Python 3.12 and 3.14, with the existing Reactivex warning. A synthetic GTK preview also verifies local
log creation without any GPU reads/writes or service connection. Logging has not yet been exercised in
a further hardware-control trial. Wayland, suspend/resume, continuous operation, private-profile migration
and integration into the historical main window remain pending.
