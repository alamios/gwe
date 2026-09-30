# Supervised NVML fan experiment

This standalone maintenance experiment is deliberately separate from the application and profile database.
It does not implement continuous fan curves, change the default X11 backend, or alter clocks/power limits.
No GPU write is enabled by importing the module or running its default read-only preflight.

## Preconditions and procedure

1. Obtain authorization for the hardware experiment. Close GWE completely, including its tray process.
   Inspect Flatpak processes, other fan tools and system/user services. CoolerControl can detect this GPU;
   an empty saved configuration alone does not rule out temporary control. Establish exclusive ownership
   before writing. Do not stop cooling services for other devices without owner approval.
2. Verify OS, session, kernel, driver, model, two fans, manual limits and fresh temperature. Keep the GPU
   under normal desktop use, with no load test. Inspect the binding signatures and driver symbols for
   `nvmlDeviceSetFanSpeed_v2`, `nvmlDeviceSetDefaultFanSpeed_v2`,
   `nvmlDeviceGetFanControlPolicy_v2` and `nvmlDeviceGetTargetFanSpeed`.
3. Run `python -m gwe.nvml_fan_trial` with the prepared Python 3.12 environment. This only reads.
   The experiment requires one RTX 3090 Ti, two automatic fan policies, temperature below 60 C,
   current fan speeds at most 40%, and a reported manual range containing 40%.
4. Prepare the recovery command below in a separate terminal. Once no other controller owns the GPU,
   run `python -m gwe.nvml_fan_trial --run --controllers-stopped`. The flag is an operator assertion,
   not automatic discovery or a lock respected by other applications.
5. The supervisor first resets both fans to automatic and verifies their policies. Failure stops the
   experiment before manual control. A separate worker then sets both fans to 40%, samples once per
   second for ten seconds, checks manual policy and target readback, and restores both in `finally`.
   Each telemetry collection must finish within two seconds; invalid/missing telemetry or temperature
   at least 60 C aborts. Reported speed must settle between 30% and 50% by the final sample.
6. The supervisor gives the worker 20 seconds. On timeout or interruption it kills and joins the worker
   before independently restoring both fans. Restoration attempts every fan even after a partial error,
   and verifies automatic policy individually. Any failed reset or verification is an explicit failure.
7. Independently read both policies after completion, and NV-CONTROL state on X11 if available. Record
   observed speeds rather than inferring success from them: automatic mode can stop fans at low load.
   Re-enable any temporarily stopped service after recovery, and check whether it changes the policies.

No privilege escalation is built into the module. If a call reports insufficient permissions, stop and
review that exact operation before a privileged retry. Do not run the full GWE GUI as root.

## Recovery prepared before manual control

With competing controllers still stopped, from the same checkout/environment:

```bash
python -m gwe.nvml_fan_trial --restore-only --controllers-stopped
```

This selects the single matching GPU, attempts `nvmlDeviceSetDefaultFanSpeed_v2` for each fan and verifies
policy zero (temperature-driven automatic). It does not require cool/fresh temperature or an already
automatic policy, so a thermal abort does not block recovery. Identity stays in memory/IPC and is never
written to diagnostic output or committed. Restarting the normal GUI is not the first recovery step:
its saved preferences may immediately reapply a custom profile.

The worker's cleanup and its supervisor cover complementary single-process failures while the other process
and driver remain responsive. They do not guarantee recovery if both processes die, the host freezes, an
NVML recovery call hangs, or the driver is lost. A killed supervisor leaves the worker to finish its bounded
sequence and cleanup; a stuck worker is handled by the living supervisor. If recovery fails, stop workloads,
keep supervision and use an authorized system recovery/reboot; never report automatic control as restored
without verification. This is not a production watchdog or a validated suspend/resume solution.

## Read-only evidence: 2026-09-30

- Repository continuation baseline: `0f8e183`, branch `maintenance/nvml-revival`.
- Reconfirmed Ubuntu 24.04.5, X11, kernel 7.0.0-34-generic, driver 580.178.04 and RTX 3090 Ti.
- Two fans, manual range 30–100%; snapshot 50 C, both reported 0%, power draw 34.7 W.
- Both NVML policies were zero (automatic), and X11 `GPUFanControlState` was zero.
  `nvmlDeviceGetTargetFanSpeed` reported 100 for each despite actual speed zero in automatic mode;
  this field must not be interpreted as measured speed or a currently applied manual target.
- Required Python functions and native symbols resolve with nvidia-ml-py 13.615.71. This does not prove
  write permission or restoration support. The existing power limit was read as 250 W and was not changed.
- GWE was absent from Flatpak/process inspection. CoolerControl was running and detected this GPU.
  Its saved `device-settings` map was empty; its live device API required authentication. Temporary
  control could not be excluded, so hardware writes remain pending exclusive ownership.
- Private screenshots were inspected and preserved outside Git; profile autoload and minimize-to-tray
  explain why closing a window or restarting GWE is insufficient as a safety procedure.
- 62 simulated tests pass on Python 3.12.3 and 3.14.6, including partial writes, permission failures,
  bad limits, missing/stale telemetry, reset failure, policy verification and supervisor timeout ordering.
  Reactivex's pre-existing datetime deprecation warning remains.

Manual writes, successful hardware restoration, recovery under real process failures, Wayland and
Kubuntu 26.04 remain untested. See the permission check below.

## API reference

NVIDIA documents that the manual setter changes the fan policy and that the default-speed setter restores
it: [NVML device commands](https://docs.nvidia.com/deploy/nvml-api/latest/api/group__nvmlDeviceCommands.html)
(rechecked 2026-09-30). Local symbol/read validation complements this documentation; it does not establish
hardware write support.

## Authorized live attempt: 2026-09-30

The owner authorized temporarily stopping CoolerControl. The service was stopped and confirmed inactive;
Flatpak/process inspection found no competing fan controller. Driver 580.178.04, automatic policies on both
fans and the unchanged 250 W power limit were verified immediately before the attempt.

At 56 C, the unprivileged preflight passed. Both initial default-policy setters returned
`NVMLError_NoPermission`. The supervisor aborted before starting the manual worker and retried automatic
restoration during cleanup; it did not call the manual speed setter. Subsequent NVML reads still showed
both policies automatic and speeds zero; X11 `GPUFanControlState` was also zero. These readings establish
the retained state, not successful restoration writes.

A privileged retry was prepared as a transient systemd service with a 40-second runtime limit and an
`ExecStopPost` automatic-reset command. Systemd rejected service creation with
`Interactive authentication required`; that attempt did not execute the Python trial. A subsequent stop
request for that unit timed out. CoolerControl was successfully restarted after both attempts, and the
final read showed 58 C, both policies automatic, both reported speeds zero and power limit 250 W.
No power or clock setter, profile change, package change or load test was performed.

An operator terminal with sudo authentication is now required for the hardware trial. From the checkout,
with the prepared Python 3.12 environment active, and after repeating exclusive-controller inspection:

```bash
trial_python="$(command -v python)"
sudo -v && (
    trap 'sudo systemctl start coolercontrold.service' EXIT
    sudo systemctl stop coolercontrold.service || exit
    sudo "$trial_python" -m gwe.nvml_fan_trial --run --controllers-stopped
)
```

The parent/worker recovery remains active inside this invocation. The shell trap restarts CoolerControl
on ordinary exit, including failed preflight; it cannot survive SIGKILL or host failure. Keep the separate
`--restore-only --controllers-stopped` recovery command ready with the same interpreter and privileges.
Recheck fan policy and the service state after the run. Do not infer root-level NVML support from the
permission failure; successful setters and recovery are still pending.
