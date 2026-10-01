# Explicit NVML power-limit control

Implemented in source on 2026-10-01. This extends the manually started experimental service; it does
not enable boot startup, replace the installed Flatpak, enable overclocking or change drivers/packages.
The default X11 controller and isolated monitor remain unchanged. Real power writes are pending until
the reviewed service bundle is updated and the guarded hardware trial passes.

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
python scripts/stage_fan_service.py build/power-service-v1
```

The bundle's `update.sh` requires an inactive existing service, no unresolved journals and no existing
rollback-copy collision. It verifies hashes, prepares a root-owned replacement, validates the unchanged
configuration, keeps the previous code/unit at `/opt/gwe-fan-service.previous`, replaces code/unit and
reloads systemd. It does not start or enable the service. Failure during an ordinary update rolls back.
The installer/uninstaller refuse to remove unresolved recovery state. Abrupt host failure during an update
still needs manual review; no atomic whole-system upgrade claim is made.

With installed GWE and development windows closed, no heavy load and the service inactive:

```bash
bash scripts/validate_power_service.sh /path/to/prepared/python3.12 build/power-service-v1
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
The staged `build/power-service-v1` bundle has 18 verified hashes; all three shell scripts and its systemd
unit pass syntax validation. No updated service has been installed or real power setter invoked.

Automated tests use simulated NVML and processes. They cover strict protocol fields, peer boundary reuse,
UUID checks, stale values, limits/precision, permission errors, missing reads, exact verification, partial
writes, journals, corrupt/symlink records, worker crash/stall, bounded rollback, external-value refusal,
commit retention, GUI identity/ACK validation, no retry, stale telemetry and update rollback.

Python 3.12/X11 `--demo --smoke-power` exercises the actual Power slider/Apply signal against a simulated
socket service. It checks that the edited value survives several real read-only telemetry updates before
Apply, that the exact requested/previous milliwatts reach the service, and that overclock/fan writes remain
disabled. The existing simulated fan-service GTK smoke also passes. These checks do not write to the GPU.
The prepared privileged trial has not run: noninteractive sudo requires the owner's password.

References: [NVIDIA power-limit setter](https://docs.nvidia.com/deploy/nvml-api/latest/api/group__nvmlDeviceCommands.html)
and [main-window fan acceptance](main-window-service.md). API documentation establishes requirements,
not hardware acceptance on this host.
