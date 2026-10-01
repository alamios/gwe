# Explicit NVML power-limit control

Implemented in source on 2026-10-01. This extends the manually started experimental service; it does
not enable boot startup, replace the installed Flatpak, enable overclocking or change drivers/packages.
The default X11 controller and isolated monitor remain unchanged. The reviewed service bundle is installed and the guarded 250→240→250 W hardware trial passed.
Visible main-window Power Apply verification has also passed on the current host.

## Semantics and boundary

Launch the isolated main window with an explicit backup and `--allow-power-control`. The existing
Power slider and Apply button become available only after a matching-GPU service status response,
fresh usable telemetry, and absence of fan/power work. `--allow-control` separately enables bounded
fan trials; neither flag implies the other. Preview and monitor-only launchers never enable power writes.
No power setting is applied at startup or imported from a profile. Overclock remains disabled.

Power is a one-shot operation, not a renewable fan lease. A verified successful limit is retained on
client disconnection, window close and normal service shutdown. It is not reset to the factory default.
The UI reports the previous value so the user can explicitly apply it again. No reboot persistence is
configured; NVIDIA documents that these limits are not persistent across reboot or driver unload.

The authenticated SOCK_SEQPACKET protocol adds `power_status` and `power_apply` to version 1. Apply
requires exact fields `limit_mw`, `expected_mw` and `expected_uuid` in addition to version/op. Milliwatts
must be integers (not booleans), positive and within uint32 range. The expected identity is compared to
the root-owned configured UUID, never used to select another device. The current limit must still match
the caller's expected value. Older installed services reject the new operation and leave controls disabled.

Only an isolated worker invokes `nvmlDeviceSetPowerManagementLimit`. It re-resolves/checks UUID,
queries current min/max and current limit, validates both previous/requested values, journals the previous
limit before the setter, and requires exact readback after it. No fan or clock setters exist in this worker.
Fan acquisitions and power operations exclude one another server-side; UI gating is additional protection.
The main service loop remains responsive to its watchdog while power NVML calls execute separately.

## Recovery and private records

Root-owned mode-0600 records live in the preserved `/run/gwe-fan-service/` directory:

- `power-pending.json`: written and synced before a setter; prevents another transaction until resolved.
- `power-last.json`: last completed operation's previous/requested values and outcome, including UUID.
  This is private recovery/audit state, not a shareable diagnostic log.
- `power-trial.json`: independent 250 W baseline guard used only by the fixed acceptance trial below.
- `power-trial-last.json`: private outcome of that trial guard's recovery.

Commit writes the completion record before removing and syncing the pending record. A crash before
pending removal is treated as uncommitted. Ordinary exceptions, worker death or a three-second timeout
start a separate bounded rollback worker. Rollback revalidates identity/range and checks the old value.
If the current value is neither previous nor requested, it refuses to overwrite a possible external
controller's change and retains the journal for review. Driver quantization/partial writes can also make
this conservative check fail; no recovery success is then claimed. A worker that cannot be killed latches
a fault. Failed recovery blocks further control and stops the daemon. Systemd ExecStopPost independently
attempts fan, power and trial recovery after the service cgroup has stopped, even if another recovery fails.

A lost response after commit remains an uncertain client result: no automatic retry or false verification.
Check live telemetry and private service state. A confirmed commit without a pending record is never
rolled back merely because the client disconnected. Power GUI events use the bounded redacted local log;
raw exceptions, UUIDs and profile data are not written there.

## Reviewable update and guarded hardware acceptance

Stage a fresh bundle with the prepared environment; staging installs nothing:

```bash
python scripts/stage_fan_service.py build/power-service-v2
```

The bundle's `update.sh` requires an inactive existing service, no unresolved journals and no existing
rollback-copy collision. It verifies hashes, prepares a root-owned replacement, validates the unchanged
configuration, keeps the previous code/unit at `/opt/gwe-fan-service.previous`, replaces code/unit and
reloads systemd. It does not start or enable the service. Failure during an ordinary update rolls back.
The installer/uninstaller refuse to remove unresolved recovery state. Abrupt host failure during an update
still needs manual review; no atomic whole-system upgrade claim is made.

With installed GWE and development windows closed, no heavy load and the service inactive:

```bash
bash scripts/validate_power_service.sh /path/to/prepared/python3.12 build/power-service-v2
```

This single wrapper authenticates sudo, updates the bundle, remembers CoolerControl's original active
state and stops it temporarily. It prepares a root-owned trial guard, starts the bounded service and runs
the unprivileged client trial. Preparation verifies the configured RTX 3090 Ti, two automatic fans,
temperature below 65 C, current limit exactly 250 W and support for both 240 W and 250 W. It writes no GPU
settings. The trial applies 240 W, independently reads it back, checks retention after client disconnect,
and explicitly returns to 250 W. While the guard exists, the service rejects power requests outside
that pair and blocks fan acquisitions. It does not add load. The shell cleanup stops the service, runs independent
recovery, requires all ownership/pending/trial records gone, and restores CoolerControl only if it was
previously active and recovery succeeded. The trial guard also restores 250 W at the service lifetime or
post-stop recovery if the client dies after a successful 240 W commit. It does not protect against total
host/driver failure. Keep records and leave CoolerControl stopped if recovery is reported pending.

After hardware acceptance, an explicit GUI launch uses:

```bash
python scripts/run_service_gui.py --database "$BACKUP_DB" --allow-power-control
```

The updated service must be running with the documented controller exclusivity. It still has a 60-second
lifetime; this is not continuous operation. Repeat updates must review the existing rollback copy rather
than silently deleting it. To roll back code, stop/recover the updated service first, preserve its journals,
and restore the saved code/unit; never deploy the old fan-only recovery while power recovery is pending.

## Validation

The complete suite passes **379 tests on Python 3.12 and 3.14**, with the existing Reactivex datetime
deprecation warning. Monitor, simulated fan-service and simulated power GTK checks pass on Python 3.12/X11.
The staged `build/power-service-v2` bundle has 18 verified hashes; all three shell scripts and its systemd
unit pass syntax validation. These source/package checks preceded the installed-service hardware acceptance below.

Automated tests use simulated NVML and processes. They cover strict protocol fields, peer boundary reuse,
UUID checks, stale values, limits/precision, permission errors, missing reads, exact verification, partial
writes, journals, corrupt/symlink records, worker crash/stall, bounded rollback, external-value refusal,
commit retention, GUI identity/ACK validation, no retry, stale telemetry and update rollback.

Python 3.12/X11 `--demo --smoke-power` exercises the actual Power slider/Apply signal against a simulated
socket service. It checks that the edited value survives several real read-only telemetry updates before
Apply, that the exact requested/previous milliwatts reach the service, and that overclock/fan writes remain
disabled. The existing simulated fan-service GTK smoke also passes. These checks do not write to the GPU.
The owner subsequently ran the privileged trial after the preparation corrections below.

References: [NVIDIA power-limit setter](https://docs.nvidia.com/deploy/nvml-api/latest/api/group__nvmlDeviceCommands.html)
and [main-window fan acceptance](main-window-service.md). API documentation establishes requirements,
not hardware acceptance on this host.


## Updater preflight correction: 2026-10-01

The owner's first privileged attempt passed every bundle checksum but stopped with the entry-point
installation-path guard. The updater called `entry.py check` from `.next`; the strict entry point only
accepts `/opt/gwe-fan-service`. No power trial ran. Read-only follow-up found the original installation
still present, no `.next`/`.previous` residue, the service inactive, CoolerControl active and power at 250 W.
Fan policies were manual at that later observation, so competing controllers must be closed before retry.

The updater now swaps the prepared code into the final path before checking configuration, while its
rollback trap remains active. The entry-point trust guard is unchanged. Regression fixtures now exercise
the final-path requirement, and both configuration-check and unit-install failures verify rollback.
The focused updater/bundle/trial-client suite passes 26 tests on each Python version. A fresh corrected
bundle is staged at `build/power-service-v2`, with checksums verified. Privileged retry remains pending.


## Trial runtime correction: 2026-10-01

The second owner attempt installed the corrected bundle successfully, preserving the configuration and
previous code/unit, but `prepare-power-trial` failed with FileNotFoundError. The runtime directory did not
exist: systemd normally creates it when the service starts, whereas preparation must create the recovery
guard before starting the service. No power writes ran. Follow-up found service inactive, CoolerControl
active, both fans automatic and the power limit unchanged at 250 W.

The wrapper now creates a missing runtime directory as root with mode 0711, without replacing or changing
an existing path. It also accepts `--installed` to check and use the already updated installation, preserving
the rollback copy instead of attempting another update:

```bash
bash scripts/validate_power_service.sh /path/to/prepared/python3.12 --installed
```

Close installed GWE and development controllers before running. The focused wrapper/updater suite passes
20 tests in each Python environment, including the formerly missing-directory case, ordering of guard
preparation before startup, cleanup and the absence of an update in installed mode. Hardware retry is pending.


## Successful installed-service power trial: 2026-10-01

The owner ran installed mode successfully. The service and independent readback verified 250→240 W,
retention of the committed 240 W value after client disconnection, and 240→250 W. The wrapper then
stopped the service and performed guarded recovery/cleanup.

Independent read-only follow-up found the service inactive with success result, CoolerControl active,
no fan ownership, power-pending or power-trial record, both fan policies automatic and both fan speeds
zero at 54 C. The power limit was 250 W. No load was added or hardware settings changed during follow-up.

This validates real one-shot power writes, readback, disconnect semantics and normal guarded cleanup
on the current driver/X11 host. It does not establish real power-worker crash/stall recovery, main-window
Power Apply interaction, reboot persistence, continuous service or Wayland/target-OS acceptance.


## Guarded main-window acceptance command

The same wrapper can open the real window instead of running the terminal trial:

```bash
bash scripts/validate_power_service.sh /path/to/prepared/python3.12 --installed --gui "$BACKUP_DB"
```

It uses the explicit backup read-only and enables only power controls. The independent trial guard still
limits requests to 240/250 W and restores 250 W at shutdown; this is acceptance behavior, not the normal
committed-power retention policy. Select 240 W, press Apply, wait for the verified message, then apply
250 W and close the window. Complete within the unit's 60-second lifetime; if it expires, close and rerun.
The wrapper's simulated tests verify argument routing, guard-before-window ordering, and cleanup after
window exit.

## Main-window result visibility: 2026-10-01

The owner's real GUI session logged a `power_verified` event, but the owner saw only the initial notice.
The power result was appended after long fan-preview instructions in an unwrapped label. This establishes
one verified GUI transaction, not completion of both requested limits or visible acceptance. Later status
requests failed near the service lifetime; that timing is consistent with expiry, but is not a proven cause.

Idle power status now starts the notice, and power-only launches omit unrelated fan-preview instructions.
Service notices wrap within a bounded label width. Active fan/recovery messages retain priority.
The focused controller tests pass (45 on each interpreter), and the Python 3.12 simulated GTK power check
passes while checking the actual mapped, revealed label and its `Power verified:` prefix. No real GPU
writes occurred during these checks. Independent read-only follow-up found 250 W, both fan policies
automatic, the service inactive with a success result and CoolerControl active at 56 C.

Repeat the guarded GUI command above to confirm both messages visibly. These are source UI changes;
the installed service does not need an update. The private diagnostic log is retained.

## Rejected GUI attempt and diagnostic coverage

The owner's next attempt reported the generic unavailable/rejected message. The local log recorded two
`power_failed` events without operation or error codes, so the cause cannot be reconstructed. Independent
read-only follow-up confirmed 250 W, both fan policies automatic, the service inactive with success and
CoolerControl active. This is not a successful GUI acceptance result.

Power diagnostics now preserve allowlisted operation/error codes in the private bounded log and show
actionable messages without raw exceptions, identities or paths. In particular, `trial_guard_active`
explains that the guarded trial accepts exactly 240 W or 250 W; `stale_power` asks for fresh telemetry;
transport errors distinguish timeout, unavailable connection and denied permission. These are possible
diagnoses, not an established cause of the owner's failure. A recovered initial connection clears its
obsolete connection warning; rejected Apply instructions remain visible through subsequent idle reads.
No power request is retried automatically.

61 focused tests pass on each interpreter. The Python 3.12 GTK smoke check now injects a guarded
rejection, verifies its visible explanation, explicitly retries through the button and verifies the visible
success message. All write requests in that check go to the simulated backend. Real GUI acceptance
remains pending and requires no installed-service update for these source UI changes.

## Visible guarded GUI acceptance: 2026-10-01

After the diagnostic change, the owner confirmed seeing the verified result. The final real GUI session
logged two `power_verified` events from status polling, followed by normal window closure, with no
failure events in that session. Requests were constrained by the 240/250 W trial guard. The redacted
log does not retain numeric transaction values, so it cannot independently establish their order.

Independent read-only follow-up found 250 W, both fan policies automatic, temperature 57 C, the service
inactive with success and CoolerControl active. No GPU settings were changed during follow-up. This
validates visible main-window power verification and the complete guarded shutdown procedure on the
current Python 3.12/X11 host. The earlier unexplained failures remain historical limitations; the injected
`trial_guard_active` event from the simulated GTK check is not evidence of their cause.

Real power-worker crash/stall recovery, continuous operation, suspend/resume, reboot persistence and
target-OS/Wayland acceptance remain unvalidated. Keep the bounded diagnostic log for future failures.

## Single-command service recovery check

With GWE and development windows closed and no heavy load, run from the repository:

```bash
bash scripts/validate_power_service.sh /path/to/prepared/python3.12 --installed --recovery
```

No service update or GUI interaction is needed. The wrapper checks the installed configuration, arranges
controller exclusivity and prepares the same independent 250 W recovery guard. The runner commits and
independently verifies 240 W, kills the complete service with SIGKILL and checks its post-stop recovery.
Only after verifying 250 W, the same GPU, both automatic fan policies and absence of pending records
does it prepare the second guard, restart the service and repeat with SIGSTOP/watchdog termination.
Each stop has a 25-second polling deadline and subprocess calls are bounded. Unexpected results abort
the sequence. The wrapper always attempts cleanup and restores CoolerControl's previous state only
after successful recovery. Both scenarios print PASS or the command fails; no load or clock writes occur.

This checks systemd recovery of the acceptance guard after a committed reduction. It does not force a
real NVML worker to fail between its setter and journal commit. That interrupted-transaction boundary
is tested automatically with spawned simulated NVML workers: SIGKILL and SIGSTOP after the simulated
hardware change both restore the previous value through the independent recovery worker. No privileged
fault hook has been added to the installed service. The combined command passed on real hardware as
recorded below.

Validation on 2026-10-02: the complete automated suite passes with 420 tests on each of Python 3.12 and
3.14, including both worker signals, recovery-runner failure/deadline/identity checks and shell cleanup
after successful or failed recovery runs. The existing Reactivex datetime deprecation warning remains.

### Hardware result: 2026-10-02

The owner ran the combined command successfully. Each scenario committed and independently read
250→240 W, verified retention after client disconnection and reported PASS after service termination:
SIGKILL with signal result, then SIGSTOP with watchdog result. Both post-stop checks verified restoration
to 250 W and both automatic fan policies. The overall recovery check reported PASS.

Independent read-only follow-up found 250 W, both fan policies automatic, temperature 57 C and no fan,
power-transaction or trial pending record. CoolerControl was active again. The experimental unit remained
`ActiveState=failed`, `Result=watchdog`, which is the expected record of the injected second fault, not
an indication of failed recovery. The wrapper requires an inactive unit before another trial; preserve
this fault result until reviewed and reset the failed unit before a future run.

This validates the installed systemd post-stop trial-guard recovery after complete-service death and
watchdog termination. It does not establish hardware interruption inside an uncommitted NVML power
transaction. That boundary remains covered by simulated tests. Continuous operation, suspend/resume,
driver/host failure and target-OS/Wayland acceptance remain pending. No new hardware tests are needed
to repeat this accepted service-level result.
