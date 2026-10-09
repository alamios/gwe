# Continuous fan-control loss: 2026-10-05

## Corrected service acceptance: 2026-10-10

The owner reran the grouped check with supervisor-only fault injection. Installed startup,
saved-curve ownership, editor, tray and Quit passed. Service supervisor SIGKILL passed with
Result=signal; supervisor SIGSTOP passed with a recorded ten-second watchdog timeout and
Result=watchdog. Both sessions verified automatic fans, unchanged power and restored cooling state.
The final command reported `Native installed startup, Quit, SIGKILL and watchdog recovery: PASS`.

The GUI showed `socket_timeout during status` during deliberate service freezing. This is an
expected client fault under that injection, not evidence of failed recovery. Recovery acceptance
comes from the independent checker, rather than from that GUI notice. Independent final readback
found both policies automatic, 44 C, unchanged 250 W, helper inactive/success, socket active,
CoolerControl active and no ownership, session or power journals.

Rc1-6 therefore passes installed lifecycle and supervisor fault-recovery acceptance on this
RTX 3090 Ti, driver 580.178.04, KDE/Wayland and Ubuntu 26.04.1 host. Together with the owner's
reported use without recurrence, this clears the acceptance hold for preparing a corrected
prerelease. The rc1-5 assets/tag remain historical and must not be published as the correction.
No push, tag replacement or publication was performed. Measured uninterrupted soak duration,
recorded suspend/resume, other hardware and driver/host failure guarantees remain unvalidated.
Bulk killing the recovery process remains outside these supervisor fault guarantees.

## Owner follow-up: 2026-10-10

The owner confirms rc1-6 is installed and reports no recurrence of the curve-loss symptoms,
including after migrating to Kubuntu 26.04. Read-only inspection confirms installed
`gwe-nvml 1.0.0~rc1-6`, `/etc/os-release` reporting Ubuntu 26.04.1 LTS, and the current session
environment reporting `XDG_SESSION_TYPE=wayland` and KDE. This establishes the desktop session type,
not whether the GWE window uses native Wayland or XWayland.

This is positive owner-reported real-use evidence. The installation time, uninterrupted session
length and workload coverage were not measured; do not describe the interval as a five-day soak.
No application was launched, stopped or fault-injected, and no GPU settings were changed during
the initial read-only follow-up. The later authorized checks are recorded below. A consolidated installed startup/Quit and fault-recovery check on the new host is
still pending, as is independently recorded suspend/resume. Publication remains on hold pending
that acceptance; the preserved rc1-5 artifacts must not be substituted for the correction.

## Post-migration installed checks: 2026-10-10

With the GPU available and GWE closed by the owner, read-only preflight found driver 580.178.04,
kernel 7.0.0-38-generic, system Python 3.14.4, intact rc1-6 package files, both fans automatic,
33–34 C and a current 250 W limit. KDE reported Wayland and a read-only GDK initialization selected
`GdkWaylandDisplay`. A compute context belonged to the desktop `code` process; no process was
stopped to remove it and no synthetic GPU load was generated.

The installed application passed saved-curve startup, six seconds of verified ownership, the native
editor, tray hide/show retaining ownership and explicit Quit. Both fans returned to automatic, the
250 W limit remained unchanged, CoolerControl returned to its original active state, and the helper
ended inactive/success with its activation socket active.

Two further installed sessions passed client SIGKILL and client SIGSTOP recovery. Signals targeted
only the application subprocess launched by the check, not the privileged service or unrelated
processes. With SIGSTOP, both fans were verified automatic while the application was still frozen;
only then was that child terminated to finish pidfd-driven session cleanup. Both sessions ended
with automatic fans, unchanged 250 W, restored CoolerControl and helper inactive/success.
The local check script is retained in ignored `build/wayland-acceptance-20261010/`.

An Ayatana indicator deprecation warning was non-fatal. No profiles, power limits, frequencies,
packages or drivers were modified. These results validate client failure recovery on the new host;
they do not replace service SIGKILL/watchdog injection. That remaining grouped check requires
interactive sudo authentication (`sudo -n true` reported authentication required), and has not been
run in this follow-up. Publication remains pending that service-level acceptance. Suspend/resume
and driver/host failure guarantees remain outside this evidence.

## Service fault-injection failure and manual recovery: 2026-10-10

The owner ran the grouped privileged check. Normal startup/editor/tray/Quit passed again, but
service SIGKILL recovery failed. Independent readback found both policies manual, 36 C, unchanged
250 W, service failed/signal and CoolerControl inactive. The ownership and session journals remained;
there were no pending power journals and no remaining service processes.

On systemd 259.5, the journal and ExecStopPost metadata show that the bulk
`systemctl kill --kill-whom=all --signal=SIGKILL` also killed the newly started recovery process
with SIGKILL. The failure is real and must not be counted as recovery acceptance. The indicator
warning is unrelated. Other historical shutdown errors in the journal are not attributed to this test.

The owner then ran the reviewed root-owned helper's `recover` action. Independent readback verified
both policies automatic, 35 C, unchanged 250 W, CoolerControl active, activation socket active and
all four recovery/session journals absent. The service retained its expected failed state from the
injected SIGKILL; this is distinct from pending GPU recovery.

The developer harness now targets `--kill-whom=main` for SIGKILL/SIGSTOP and cleanup SIGCONT.
This tests supervisor loss/hang and lets systemd manage teardown/ExecStopPost. It does not claim
survival of a bulk kill that also targets the recovery process. If final checks find incomplete
recovery, the harness invokes the installed helper only after the unit is inactive/failed and its
main/control PIDs are zero. Successful emergency cleanup never turns the failed test into a pass.
Sixteen simulated acceptance tests pass on system Python 3.14.4, including that failure path.
No packaged application/helper files were changed. Privileged hardware acceptance of the corrected
harness remains pending; the subsequent watchdog stage was not reached in the failed run.

## Release hold and evidence

Do not publish the prepared rc1-5 candidate as ready for continuous use. Its short installed
startup/exit and service fault-recovery checks passed, but did not establish reliability over hours.
The original tag and publication assets remain unchanged as evidence; corrected packages need their
own acceptance. No installed files or GPU settings were changed during this investigation.

The owner reported that the Custom curve stopped after hours, fan control reverted to the firmware,
temperatures rose, and profile selection/Apply were disabled. The installed package was
`1.0.0~rc1-5`. A private copy of the client log was preserved before implementation.

The log records acquisition on 2026-10-03 at 22:27 UTC, followed by `ui_heartbeat_expired` during
`ui_tick` on 2026-10-05 at 10:33:07 UTC (12:33 local), about 36 hours later. It records disconnect
and a latched fault, followed by window close at 18:22 UTC and a new session. The exact cause of the
UI scheduling delay and the peak temperature are unknown. The log alone does not independently
verify fan policies at the instant of failure. Subsequent read-only inspection found an active manual
session, so the investigation did not stop it or apply a competing controller.

The service has no continuous-session lifetime cap. The client instead required a GTK-scheduled
tick at least every 2.5 seconds, in addition to the service's five-second lease. An expired UI
heartbeat closes its connection and latches `fault`; native selection/Apply then stay disabled.
Nonblocking error dialogs in rc1-5 addressed one possible delay, not this underlying dependency.

## Source correction

Continuous sessions now use one dedicated in-process I/O thread. It serializes Apply/Release/Close
and renews the existing lease once per second without GTK callbacks or display telemetry refresh.
The service's fan worker already reads and validates its own temperature, identity, fan limits,
write results and timing. Losing UI telemetry still blocks new Apply; it no longer interrupts an
otherwise healthy continuous worker. Bounded ten-second development trials retain their UI heartbeat.

The safety boundaries are unchanged: a delayed I/O worker, full-process stop, suspend interval,
socket loss or service/thermal failure cannot silently reacquire. Process death still has socket EOF
and pidfd detection; the service and native workers retain lease expiry and independent watchdog
recovery. A Python extension holding the GIL or system-wide starvation can still stop the I/O thread;
this change does not promise survival of all host stalls. No thresholds were increased.

An unexpected service return to idle is now a fault rather than a quiet successful restoration.
Only an explicitly requested release reports normal verified recovery. A fault shows a persistent
error-only banner, an explanatory tooltip, the existing nonblocking dialog and a desktop notification
(subject to desktop notification settings). Healthy operation has no status band. Controls stay
disabled until recovery is reviewed and GWE is restarted; there is no automatic retry.
Fault display requires GTK to run again; the control thread itself never calls GTK.

The private diagnostic log now distinguishes UI and I/O-worker heartbeats and records bounded
numeric heartbeat age/tick gap on expiration. It still excludes profile data, device identity,
arbitrary exceptions and paths, with its existing size/rotation limits.

## Validation and next acceptance

- Python 3.12: 587 simulated/backend/package tests passed.
- Python 3.14: 577 passed; ten HTTP-update tests excluded because requests is absent there. They pass
  on 3.12. No dependencies were installed.
- A real threaded client and simulated lease remained active with no GTK pulses for over six seconds,
  beyond the service lease, and disconnected on Close. All requests used one I/O thread.
- A 48-hour accelerated-clock session retained ownership and released normally. This is simulated
  duration coverage, not 48 hours of hardware acceptance.
- Delayed worker, expired service lease, backend fault and socket loss latch failure without reacquisition.
  Existing missing/stale telemetry, partial writes, permissions and independent recovery tests still pass.
- The isolated native GTK check passed editor/profile/tray operations, ten seconds with an error notice,
  a six-second deliberate GTK block with uninterrupted simulated renewals, and persistent fault display.

The new package `build/curve-fix-rc1-6/gwe-nvml_1.0.0~rc1-6_all.deb` contains correction commit
`8c6ad03`. Its extracted system-Python payload passes the expanded GTK check, including a rendered
persistent error banner and clean Quit. Packaged Python modules match the source; the GUI launcher
has only the reviewed vendor-import insertion. New and original asset checksums verify. No private
profile databases or diagnostic logs are bundled. `BUILD_INFO` records these limits next to the package.

At package preparation, installation and real-use acceptance were pending; the dated follow-up above
records subsequent installed use on 26.04/Wayland. Measured extended CUDA coverage, post-migration
lifecycle/fault recovery and independently recorded suspend/resume remain pending. Preserve the current
power limit; historical trial wattages are not rollback targets.
