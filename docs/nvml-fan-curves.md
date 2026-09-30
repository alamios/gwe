# Experimental NVML curves and process recovery

Implemented on the maintenance branch, separate from the default application backend. No installed profile,
GTK setting, database or system service is changed. This is a controller core and bounded experiment, not
an enabled unattended fan service. The preceding [fixed-duty trial](nvml-fan-trial.md) established normal
manual writes and restoration with administrator privileges on the current GPU/driver.

## Curve contract

`gwe.fan_curve.FanCurve` takes an explicit immutable sequence of `(temperature, duty)` points, hysteresis
and the firmware-silent flag. It interpolates linearly, holds endpoint duties outside the point range and
uses Python rounding, matching the historical presenter. Heating updates immediately. Cooling keeps the
last successfully applied duty until temperature falls strictly beyond the hysteresis interval; equal duty
does not move the temperature anchor. Decisions use the last verified target, not the slowly settling
reported fan speed. No database models are imported.

Firmware-silent mode requests automatic policy strictly below the first point, before hysteresis, as in the
historical presenter. It never substitutes a manual zero-percent write. Returning above the boundary
reenters manual control. Points must have increasing temperatures and nondecreasing duties; invalid,
empty, duplicate or decreasing profiles are rejected for explicit review. These checks are stricter than
the historical presenter. No sorting, clamping, rewriting or automatic migration of existing profiles occurs.
Every duty must fit the current device's manual range, even in firmware-silent mode.

## Controller session

`gwe.nvml_fan_control.NvmlFanController` requires an explicitly supplied, initialized NVML binding, GPU UUID
and validated curve. It exposes `start()`, `tick()` and `stop()`. There is no implicit driver initialization,
privilege escalation, clock/power operation or integration into the read-only backend.

- Start validates identity, fan count/range, temperature and automatic policy before taking ownership.
  Existing manual control is refused without resetting the other owner's fans. A reset/verification gate
  must succeed before any manual write. Limits are revalidated at every tick.
- Every tick reads new temperature and verifies the expected policies and previous target on every fan.
  Changed capabilities, external target/policy changes, identity loss or mismatch stop the session.
  Selection always uses UUID; it never falls back to a current index or replacement device.
- Calls are serialized within the instance. This lock does not exclude another application; the operator
  must establish exclusive GPU ownership. A future service must enforce ownership across clients.
- Missing/nonfinite/out-of-range temperature, delayed telemetry (default two seconds), missed ticks
  (default five seconds), or a temperature at/above the configured ceiling stop manual updates. The core's
  default ceiling is 85 C; the bounded trial explicitly uses 60 C. These are conservative stop conditions,
  not claims about hardware thermal limits.
- Partial writes, permission failures, exceptions and interrupts trigger restoration of every known fan.
  Each reset and automatic policy is checked independently; a failed reset does not skip the other fans.
  A successful setter alone is insufficient: manual policy and target readback must also match.
- States are `new`, `automatic`, `manual`, `fault`, `recovery_failed` and `closed`. Faults latch: subsequent
  telemetry cannot silently reactivate a curve. A new explicit session is required. `stop()` may retry
  recovery after failure, and never rearms the old instance. Recovery errors remain visible.

The core's deadlines can only be checked when a native call returns. A frozen process or driver call
requires external supervision; invoking `tick()` in a GUI timer alone is not sufficient.

## Bounded supervisor and experiment

`gwe.fan_supervisor.supervise` starts a worker with the spawn multiprocessing context. The worker sends
one heartbeat after each verified control step, and sends completion only after its own cleanup. The
parent detects lost heartbeats (five seconds), unexpected process exits and the total experiment deadline
(20 seconds). Before parent recovery it kills and joins any surviving worker, preventing subsequent
manual writes from racing restoration. Signals during cleanup are temporarily ignored and then restored.
The caller must install raising SIGTERM/SIGINT handlers; the trial does so.

`python -m gwe.nvml_curve_trial` performs only the existing read-only preflight. Explicit `--run` and
`--controllers-stopped` are required to write. The trial requires the same single RTX 3090 Ti/two-fan setup,
automatic initial policy, reported speeds at most 40% and temperature below 60 C. It uses a synthetic curve:
40% through 50 C, increasing to 50% at 60 C (and 100% at 80 C, unreachable before the trial's thermal abort).
The curve is not taken from a private profile. It samples once per second for ten seconds, with 2 C
hysteresis, and restores automatic control. Identity stays in memory/IPC, never shared diagnostics.

The optional scenarios `term`, `kill` and `stall` inject SIGTERM, SIGKILL or SIGSTOP into the worker after
two verified ticks. A stalled worker must stop delivering heartbeats, then be killed before parent recovery.
A reported injected-termination outcome means the parent detected the fault; only successful automatic
restoration makes the command successful. These are deliberate hardware-fault experiments when `--run`
is used: perform them separately after a normal run and with current operator authorization.

### Operator command for a normal hardware trial

From the checkout in the prepared Python 3.12 environment, with GWE fully closed and no competing GPU
controller, authenticate in a terminal. CoolerControl is stopped temporarily and restarted on shell exit:

```bash
trial_python="$(command -v python)"
sudo -v && (
    trap 'sudo systemctl start coolercontrold.service' EXIT
    sudo systemctl stop coolercontrold.service || exit
    sudo "$trial_python" -m gwe.nvml_curve_trial --run --controllers-stopped --scenario normal
)
```

Keep the existing independent recovery command ready, using the same interpreter with sudo:
`python -m gwe.nvml_fan_trial --restore-only --controllers-stopped`.
After any run, independently check automatic policies and that CoolerControl is active. A return to zero
reported fan speed can be normal in automatic mode and is not a substitute for checking the policy.
The terminal command is not a system service; shell cleanup does not survive SIGKILL or host failure.
Do not launch the installed GWE as recovery without considering its saved profile autoload setting.

## Validation: 2026-09-30

- 118 tests pass under Python 3.12.3 and 3.14.6. The existing Reactivex datetime deprecation warning remains.
- Pure curve tests cover interpolation, endpoints, rounding, hysteresis boundaries, silent-mode precedence,
  malformed curves and refusal to clamp incompatible duties.
- Injected NVML tests cover both fans, partial writes, denied permissions, invalid/stale temperatures,
  changing limits/count, identity mismatch, changed ownership, failed verification, interrupts, failed
  recovery and explicit retry. They never initialize real NVML.
- Actual spawned child processes were terminated with SIGTERM/SIGKILL and suspended with SIGSTOP.
  Process-shared simulated fan policies were restored after the child stopped. This validates process
  mechanics and simulated device recovery, not real driver behavior during those faults.
- The new CLI's live read-only preflight passed on the current X11 host at 59 C with both fans automatic
  and reported speed zero. No new GPU write or service stop occurred during this implementation phase.
- The normal synthetic-curve, worker-SIGTERM, worker-SIGKILL and SIGSTOP-induced stalled-worker hardware
  runs subsequently passed as recorded below. The supervisor and driver remained responsive in each case.

## Remaining production work

A privileged service needs an installed, administrator-owned executable/configuration, a restricted local
protocol, one UUID-bound owner, a renewable control lease, independent crash recovery and service-level
supervision of blocked native calls. The UI should remain unprivileged. Do not install a root daemon that
imports code from a user-writable development checkout. Those service properties are proposed, not implemented.

The current parent/child design does not guarantee recovery if both die, the driver is lost, recovery calls
hang or the host freezes. Parent death leaves the bounded worker to finish/restore while it remains
responsive. Suspend/resume, service restarts, session changes and actual Wayland/Kubuntu 26.04 must be tested
before continuous operation. Profile import/migration and UI curve activation remain separate work.

## Normal curve hardware trial: 2026-09-30

The owner ran the supplied normal scenario with sudo from commit `34e7688` on the current X11 host.
The manual interval is evidenced by the supplied terminal output; the maintenance agent independently
checked the resulting hardware/service state afterward.

- Preflight: 55 C, both policies automatic, both reported speeds zero.
- Ten verified control ticks: target 45% on both fans; nine temperature samples at 55 C, then one at 54 C.
  The retained 45% target on cooling is consistent with the configured 2 C hysteresis. The controller
  checks both policies and target readbacks before emitting each successful tick; this output does not
  independently measure fan RPM or validate the entire curve across its temperature range.
- Supervisor result: `completed`, ten ticks, no injected fault; automatic policies verified on completion.
- Independent follow-up: driver 580.178.04, 54 C, both NVML policies zero, reported speeds zero,
  X11 `GPUFanControlState` zero, CoolerControl active and power limit unchanged at 250 W.
- No new automated test run was needed for this documentation-only update; the 118-test baseline stands.

The next trial used `--scenario term` separately with the same command and exclusive-controller procedure.
It sends SIGTERM only to the curve worker after two verified ticks, while the supervisor remains alive.
The worker's interrupt handler may print an expected traceback; assess the supervisor's final result:
`terminated_worker_detected`, `injected: True`, followed by verified automatic policies. Any recovery
failure is a failed test regardless of the injected signal. Independently check policy and CoolerControl
again before proceeding to SIGKILL or a stalled-worker scenario. Subsequent results are recorded below.

## Worker SIGTERM hardware trial: 2026-09-30

The owner ran `--scenario term` with sudo from commit `3699e90`. The supplied terminal output shows
preflight at 57 C with both fans automatic/reported speed zero, followed by two verified manual ticks
at 57 C and a 47% target. SIGTERM interrupted the worker during its sleep; the expected traceback ended
with `TrialError: Interrupted by signal 15`. The supervisor reported `terminated_worker_detected`,
two ticks and `injected: True`, then verified automatic policies on both fans.

Independent read-only follow-up confirmed driver 580.178.04, both NVML policies zero, reported speeds
zero, X11 `GPUFanControlState` zero, CoolerControl active, temperature 58 C and power limit still 250 W.
This establishes successful end-to-end recovery after this worker SIGTERM. The output does not isolate
whether the worker or parent performed the effective reset: both attempt restoration. It does not prove
recovery when worker cleanup cannot run.

The next trial used `--scenario kill` separately under the same exclusive-controller procedure. SIGKILL prevents
worker cleanup, leaving the living supervisor responsible for stopping/joining the child and restoring
automatic control. The expected final result is `terminated_worker_detected`, `injected: True` and verified
automatic policies; independently recheck the state afterward. A stalled worker remains a separate test.
No code changed in this record update; the 118-test software baseline remains unchanged.

## Worker SIGKILL hardware trial: 2026-09-30

The owner ran `--scenario kill` with sudo from commit `54799af`. Supplied output shows preflight at 57 C,
both fans automatic and reported speeds zero. The first verified tick requested 47% at 57 C; the second
requested 48% at 58 C, demonstrating an immediate upward curve adjustment. The supervisor then killed
the worker and reported `terminated_worker_detected`, two ticks and `injected: True`, followed by
`Both fan policies verified automatic`.

SIGKILL prevents worker cleanup, so this run validates restoration by the surviving supervisor for this
specific worker-termination case. Independent follow-up confirmed both NVML policies zero, reported
speeds zero, X11 `GPUFanControlState` zero, CoolerControl active, driver 580.178.04, temperature 58 C and
power limit unchanged at 250 W. No code changed; the 118-test software baseline remains unchanged.

The next trial used `--scenario stall` separately. It suspends only the worker with SIGSTOP after two verified
ticks; the living supervisor should detect the five-second heartbeat expiry, kill/join the stalled worker
and restore both fans. Expect `stalled_worker_detected`, `injected: True` and verified automatic policies.
While suspended, the worker cannot monitor temperature; this remains a brief supervised desktop-idle
experiment, with no load generation. It does not simulate a stuck kernel/driver call or whole-host freeze.
The resulting hardware trial and independent follow-up are recorded below.

## Stalled-worker hardware trial: 2026-09-30

The owner ran `--scenario stall` with sudo from commit `2ef5f34`. Supplied output shows preflight at 43 C,
both fans automatic and reported speeds zero, followed by two verified manual ticks at 43 C with a 40%
target. The supervisor reported `stalled_worker_detected`, two ticks and `injected: True`, then verified
both fan policies automatic. In this code path the supervisor detects heartbeat expiry, kills and joins
the SIGSTOP-suspended worker, and performs recovery without worker cleanup. The output does not include
elapsed timestamps; the configured heartbeat deadline is five seconds.

Independent follow-up confirmed driver 580.178.04, both NVML policies zero, reported speeds zero,
X11 `GPUFanControlState` zero, CoolerControl active, temperature 50 C and power limit still 250 W.
The follow-up temperature was measured later, not during the suspended interval. No power/clock setter,
profile migration, load test or package change was performed. No code changed in this documentation-only
update; the 118-test software baseline remains unchanged.

### Completed bounded hardware matrix

| Scenario | Worker observations | Supervisor result | Final policy independently checked |
| --- | --- | --- | --- |
| Normal synthetic curve | Ten ticks, 45%, 54–55 C | completed | Both automatic |
| SIGTERM | Two ticks, 47%, 57 C | terminated_worker_detected | Both automatic |
| SIGKILL | Two ticks, 47–48%, 57–58 C | terminated_worker_detected | Both automatic |
| SIGSTOP-induced stall | Two ticks, 40%, 43 C | stalled_worker_detected | Both automatic |

This completes the initial bounded worker-fault matrix on this GPU/driver/X11 setup. It does not establish
unattended continuous operation, survival of supervisor death, blocked kernel/driver recovery, whole-host
failure recovery, suspend/resume or Wayland compatibility. The next implementation stage is the privileged
service and unprivileged client boundary described above, with explicit ownership and profile review before
any deployment or migration. The default GWE backend and the installed Flatpak remain unchanged.

## Service-boundary follow-up

The local protocol, client and lease state machine now have simulated-backend socket tests. See
[implemented boundary and pending supervised NVML integration](fan-service.md). No privileged daemon
was installed, and the hardware evidence above does not extend to this new transport.
