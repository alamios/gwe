# Suspend/resume and fan curves

## Recorded rc1-6 behavior: 2026-10-10

The owner suspended the migrated KDE/Wayland host with Custom active in ordinary GWE.
The system journal records suspend at 01:14:39 and return at 01:14:57 (Europe/Madrid),
followed by thawing the user session at 01:14:59. Client diagnostics record a 20.372-second
tick gap, `worker_heartbeat_expired`, disconnect and a latched fault. The raw diagnostics
were preserved privately in Git-ignored `.local-backups/`; no profile or device identity is published.

Independent readback verified both fan policies automatic, 36 C and unchanged 250 W.
The service remained active while the GUI stayed open, with its session journal retained and
CoolerControl inactive. No fan-ownership or power-recovery journal remained. Fan restoration
therefore worked, but rc1-6 did not restore Custom and required Quit/relaunch. This is evidence
of one actual suspend cycle, not acceptance of automatic curve reapplication.

## Implemented correction: rc1-7

The continuous client compares elapsed CLOCK_BOOTTIME with elapsed CLOCK_MONOTONIC. The first
includes time asleep and the second excludes it. At least one second of additional BOOTTIME
is treated as a suspend interval; ordinary scheduling stalls advance both clocks and remain faults.
The service supervisor uses the same distinction to end the previous worker and verify automatic
recovery without misclassifying suspend as a worker hang. It never reacquires on its own and never
clears a driver fault already reported by the worker.
Only a starting/active continuous curve can enter resume. Idle, automatic, bounded-trial, stopping
and already faulted sessions never automatically acquire through this path.

The client disconnects the stale connection, then waits up to fifteen seconds for the service to
report idle and unowned after verified recovery. It checks the deadline after responses as well
as before requests. Socket errors, service faults, unexpected ownership and timeout latch failure;
they are not retried. Once idle is verified, the ordinary acquisition reapplies the exact previously
applied immutable curve, including hysteresis and zero-RPM policy. It does not choose a merely
selected or edited curve. The privileged worker revalidates pinned identity, current fan limits,
policies, fresh temperature and write results. Active status still requires service verification.

There is one acquisition per detected suspend, with no retry loop. Close, explicit release or deletion
of the applied native profile cancels pending resume. Genuine process freezes, stale telemetry,
driver/service failures and power transaction guards retain their existing failure behavior.
Resume neither changes power nor writes clock offsets. The GUI keeps ordinary status hidden;
controls wait during resume and the tooltip explains the transition. Failed resume uses the existing
persistent fault banner and notification. Private bounded logs record suspend detection, recovery
verification, acquisition and cancellation without profile fields or identity.

This depends on Linux clock behavior and the existing service recovery implementation. A second
suspension during the recovery deadline can time out conservatively. It does not guarantee recovery
from host/driver failure or justify retaining manual control without fresh temperature readings.

## Validation and installation

Tests simulate suspend with separate clocks, ordinary process stalls, existing faults, delayed/failed
recovery, slow responses, socket loss, changed backend prerequisites, competing ownership, bounded
trials, release/Quit and applied-profile deletion. The native GTK check uses a simulated service and
read-only hardware telemetry, exercises clock-based resume, then verifies the persistent fault UI.
The full suite passes 613 tests on system Python 3.14.4, including actual subprocess recovery with
shared simulated NVML state. Existing Reactivex datetime and Ayatana deprecation warnings are non-fatal.

The correction is staged in `build/resume-fix-rc1-7/gwe-nvml_1.0.0~rc1-7_all.deb`.
Exact build provenance and validation limits belong in its `BUILD_INFO`; checksums identify the bytes.
The builder used the existing reviewed pure-Python vendor files under system Python 3.14, without
installing dependencies. Earlier staging snapshots and the accepted rc1-6 package are retained.

Actual automatic resume on the installed rc1-7 package remains pending. Pause CUDA work, Quit GWE
and let recovery finish before installing the new package. Then launch normally with Custom active,
suspend once and resume. Verify a new active curve plus the resume events and service ownership;
a selected Custom label alone is insufficient. Preserve the current power limit during acceptance.
The previous rc1-6 lifecycle/supervisor checks remain dated evidence, not hardware acceptance of rc1-7.
