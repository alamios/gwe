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

### Operator command for the next normal hardware trial

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
- The normal synthetic-curve hardware run and all hardware fault scenarios remain pending. The earlier
  successful fixed-40% trial must not be presented as validation of this new controller.

## Remaining production work

A privileged service needs an installed, administrator-owned executable/configuration, a restricted local
protocol, one UUID-bound owner, a renewable control lease, independent crash recovery and service-level
supervision of blocked native calls. The UI should remain unprivileged. Do not install a root daemon that
imports code from a user-writable development checkout. Those service properties are proposed, not implemented.

The current parent/child design does not guarantee recovery if both die, the driver is lost, recovery calls
hang or the host freezes. Parent death leaves the bounded worker to finish/restore while it remains
responsive. Suspend/resume, service restarts, session changes and actual Wayland/Kubuntu 26.04 must be tested
before continuous operation. Profile import/migration and UI curve activation remain separate work.
