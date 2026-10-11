# Architecture and control contracts

## Desktop and telemetry

The native entry point is `scripts/run_native.py`. It checks for competing GWE controllers, locks the
session, prepares private configuration and connects to the authorized socket before launching GTK.
The desktop is unprivileged and uses the application ID `io.github.alamios.gwe`.

`NvmlBackend` provides read-only telemetry without GTK or X11 control extensions. It resolves stable
UUID identity rather than relying on a persistent device index; missing or mismatched identity never
falls back to another GPU. Each field has an explicit availability/error status. Missing temperature
is unusable for control; missing optional sensors do not suppress other valid readings.

The GUI keeps an NVML session for sampling state, reacquires handles for reads and reinitializes after
errors. Snapshot intervals use monotonic timestamps; simultaneous queries are not an atomic hardware
snapshot. Percent, Celsius, watts, MHz, bytes and RPM are mapped to their respective UI fields.
The public `gwe.nvml_probe` diagnostic omits device identity; application snapshots must not be logged
wholesale. Fan telemetry does not independently prove physical rotation.

## Authenticated helper

The native package installs `/opt/gwe-fan-service/entry.py`, `gwe-fan-service.service` and its activation
socket. The root configuration pins one GPU and desktop UID. A mode-0600 Unix sequenced-packet socket
checks kernel peer credentials. Requests cannot choose an arbitrary GPU, executable or filesystem path.
The desktop PID is supervised so process death can end the session and restore cooling coordination.

The protocol provides `status`, `acquire`, `renew`, `release`, `power_status` and `power_apply`.
Malformed messages, unknown fields and unsupported versions are rejected. A fan lease belongs to its
specific connection; another connection from the same UID cannot renew or release it. Status does not
renew a lease. Acquisition acceptance is distinct from an `active` state verified by the worker;
release acceptance is distinct from verified `idle` recovery.

## Fan control and recovery

A dedicated desktop I/O worker renews the continuous lease independently of GTK. The privileged fan
worker uses its own fresh temperature readings and validates identity, limits, policies and writes.
Before manual control, the supervisor records ownership and acknowledges permission to write.
No fan setter runs before that handshake. The worker enforces its lease with CLOCK_BOOTTIME and the
continuous controller retains an 85 C cutoff; this is a control guard, not a cooling guarantee.

Lease loss, disconnection, release, worker failure or expired heartbeat stop the writer. Recovery
starts only after writer exit is confirmed, resets all recorded fans by UUID and verifies automatic
policies. A failed or stuck writer/recovery retains ownership evidence and blocks a new controller.
The native service has no fixed session-duration cap. Its ten-second systemd watchdog and independent
`ExecStopPost` recovery cover supervisor termination or hangs after writers stop.

The service records a competing CoolerControl service's state and coordinates its stop/restore.
This does not authorize arbitrary simultaneous GPU fan controllers. Control loss produces a persistent
notice and notification; it is not silently rearmed.

## Power transactions and persistence

Power uses a separate supervised worker, not a renewable fan lease. `power_apply` requires integer
milliwatts, the expected live limit and expected UUID. The helper checks the pinned identity, current
range and compare-and-set value, records the previous limit before writing and verifies exact readback.
Power alongside an active curve requires the service's explicit capability; fan transitions, faults
and unresolved transactions remain blocked.

Commit records completion before removing the pending journal. An interrupted or uncommitted operation
runs bounded rollback. If the live value is neither previous nor requested, recovery refuses to overwrite
a possible external change. Failed recovery retains evidence and blocks further control. A confirmed
commit is not rolled back on client disconnect; a lost response remains uncertain and is not retried.

The desktop saves only exactly verified successful targets in `settings_native_verified_power`, including
GPU identity and integer milliwatts. Normal startup restores once after fresh telemetry, identity/range
checks and stable control. Matching current values require no setter. Bad settings, identity changes,
changed constraints or service failures cannot trigger automatic retries. Saving failure is distinct from
hardware verification. Resume does not rearm power restoration.

## Suspend versus stalls

The continuous client and supervisor compare elapsed CLOCK_BOOTTIME with CLOCK_MONOTONIC. At least one
second of additional BOOTTIME identifies a suspend interval. Ordinary scheduling stalls advance both
clocks and retain fault handling.

Only starting/active continuous curves enter resume. The client disconnects stale ownership and waits
up to fifteen seconds for verified idle/unowned recovery. One normal acquisition then revalidates the
exact immutable applied curve and current hardware prerequisites. Socket failures, unexpected ownership
or deadline expiry latch a fault. Quit, release or applied-profile deletion cancels resume. Driver faults
are not cleared. No power or clock writes are performed through this path.

## Private recovery state

Runtime journals under `/run/gwe-fan-service/` include fan ownership, desktop session state and pending
power transactions. `power-last.json` records the last power outcome; guarded acceptance can add a
separate power-trial journal. These are private recovery inputs, not user-editable configuration.
Never delete them to bypass a failure. Desktop diagnostics use bounded, redacted records without
UUIDs or curve contents.

Recovery requires a responsive host/driver and a recovery process that can run. Killing the recovery
process too, host failure and driver failure are outside the verified supervisor-recovery guarantee.
See [validation](validation.md) and the [user recovery procedure](user-guide.md#control-failures-and-recovery).
