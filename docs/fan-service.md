# Experimental supervised fan service

The local protocol is now connected to `ProcessBackend`, which executes the NVML controller and recovery
in separate processes. A root-owned installation bundle, a 60-second systemd trial unit and an unprivileged
test client are prepared. The owner has now installed the reviewed bundle; it remains inactive and has not controlled the real GPU. The default
GWE backend, installed Flatpak and private profiles remain unchanged. This is not an unattended service.

## Protocol and asynchronous states

Linux UNIX sequenced-packet sockets carry JSON requests of at most 4096 bytes. Kernel peer credentials
must match one configured desktop UID. The owner is a specific connection; another connection, including
one from the same UID, cannot renew or release it. Only these operations exist:

| Operation | Extra fields | Result |
| --- | --- | --- |
| status | None | Current state and whether this connection owns the lease |
| acquire | points, hysteresis, vbios_silent | Accept validated curve; state `starting` |
| renew | None | Extend this connection's lease by five seconds |
| release | None | Begin shutdown; normally state `stopping` |

`ok: true` on acquire/release means accepted, not completion of a hardware operation. Clients must poll
for `active` or `idle` respectively. `active` requires a verified worker tick. `idle` after control requires
verified automatic restoration and clearing the ownership record. While `starting`/`stopping`, another
acquisition is refused. `fault` and `recovery_failed` latch and prevent rearming until explicit service
restart/review. Errors never include raw NVML messages or private device identity.

Unknown/duplicate fields, unsupported versions, malformed curves and more than 32 points are rejected.
There are no client-selected UUIDs, paths, programs, imports, power operations or clock operations. The
trusted service configuration selects the GPU. Points are validated again against live manual limits.
Malformed owner traffic, disconnection and lease expiry initiate shutdown. Late renewal cannot revive an
expired lease. Status requests do not renew control. Nonblocking I/O and at most eight clients keep a slow
reader from blocking service supervision. The existing synthetic-curve tests cover protocol failures.

## Process lifecycle and recovery

The service process never imports/initializes NVML or invokes its native calls in its event loop. The
worker receives the configured UUID and curve, initializes NVML, validates identity/capabilities/temperature
and requires initial automatic policy. Before the first native setter it announces the known fan indices.
The service writes a private ownership record and only then acknowledges permission to proceed. This
prevents resetting another controller after a preflight rejection and permits recovery after service death.
No manual setter can run before that ownership handshake.

After each verified curve tick the worker sends a heartbeat. The service monitors a five-second heartbeat
deadline. Release, lost client, expiry, fault or stalled worker trigger kill/join of the writer; recovery
starts only after its exit is confirmed. A separate recovery process resets every recorded fan by UUID and
verifies automatic policies. Its deadline is five seconds. Failed/hung recovery becomes `recovery_failed`,
retains the record and blocks a new writer. A worker that cannot be killed also blocks recovery/new control.

The worker independently enforces the absolute lease deadline using CLOCK_BOOTTIME, including suspended
time. Losing the service socket or lease causes worker cleanup while native calls remain responsive.
It cannot revive a lease after expiry, even if delayed renewals arrive. Graceful worker expiry is distinct
from an unexpected crash; both go through independent parent verification before returning idle.
This does not restore automatic control while the host is asleep: suspend integration remains pending.

The trial systemd unit kills the complete service cgroup on teardown. Its `ExecStopPost` performs a separate
bounded recovery using the retained ownership record, after writers have stopped. With no record it makes
no NVML calls. A runtime lock excludes concurrent service/recovery instances. An unresolved record prevents
new control. The ten-second systemd watchdog covers a stuck main event loop; live systemd failure recovery
has not yet been validated. Worker EOF/lease recovery has been tested using a killed/frozen simulated service.

## Prepared installation

Build a fresh review bundle in the checkout using the prepared Python 3.12 environment:

```bash
python scripts/stage_fan_service.py build/fan-service-review-final
```

The staging tool refuses an existing destination. It copies only the required service modules, the verified
nvidia-ml-py 13.615.71 pure-Python binding (including its license notice), GWE's license, entry point, unit,
configuration template and install/uninstall scripts. `SHA256SUMS` covers the bundle. No database, screenshot,
real UUID or user environment path is included. No package download or system installation occurs.

After explicit approval, the reviewed installer would create only:

- `/opt/gwe-fan-service/`: root-owned service code and bundled binding.
- `/etc/gwe-fan-service.json`: private root-owned configuration, initially invalid placeholders.
- `/etc/systemd/system/gwe-fan-service.service`: manual trial unit, no boot enablement.

The installer verifies hashes, refuses existing artifacts (including symlinks), sets root ownership and
reloads systemd metadata. It does not start/enable anything or change system Python packages. Partial
installation errors trigger removal of the newly created artifacts. The daemon runs `/usr/bin/python3 -I -B`
and verifies root-owned, non-writable code before imports; it never imports a user venv or checkout.

The selected desktop UID owns only the mode-0600 socket, in a root-owned mode-0711 runtime directory.
The user can traverse that directory but cannot replace its entries or read the mode-0600 recovery record.
The root configuration contains `version: 1`, a non-root `allowed_uid` and the actual `gpu_uuid`. Set those
locally after installation; do not paste the completed configuration into Git or shared diagnostics.
Configuration validation is read-only and makes no NVML calls:

```bash
sudo /usr/bin/python3 -I -B /opt/gwe-fan-service/entry.py check
```

The trial is deliberately limited to 60 seconds, with a 60 C temperature ceiling, no restart loop and no
`[Install]` section. It refuses startup unless CoolerControl is confirmed inactive/failed and checks known
competing process names. Those guards cannot detect every custom controller; the operator must still
establish exclusive ownership and keep GWE closed. It never stops another service automatically.

## Prepared hardware procedure (not performed)

Only after installation/configuration approval and read-only baseline verification, use the prepared
Python 3.12 environment in the checkout. The client runs as the ordinary user:

```bash
sudo -v && (
    trap 'sudo systemctl stop gwe-fan-service.service; sudo systemctl start coolercontrold.service' EXIT
    sudo systemctl stop coolercontrold.service || exit
    sudo systemctl start gwe-fan-service.service || exit
    python -m gwe.fan_client_trial --scenario normal
)
```

The service does not replay a stored profile; this client supplies the synthetic 40–50% trial curve and
renews briefly before requesting release. Test `disconnect` and `expire` separately after a normal pass.
They close the owning socket or stop renewing, then wait for verified `idle`. Confirm policies independently
and check CoolerControl active afterward. The shell trap restores CoolerControl on ordinary exit, not
SIGKILL or host failure. Keep the previous standalone automatic recovery procedure available.

Service SIGKILL/watchdog tests, actual cross-UID access, hardening/NVML compatibility and `ExecStopPost`
recovery need their own live validation. Do not treat the previous standalone worker-fault trials as proof
of this service's behavior. GUI connection, continuous operation and profile migration remain later work.

## Removal and recovery

The reviewed bundle's `uninstall.sh` stops the unit first and refuses removal while an ownership record
remains unresolved. It removes the installed code/unit and reloads systemd, while preserving the private
configuration and runtime directory for review. It never changes the installed Flatpak or profile database.
If removal is refused, retain the installed code and resolve/verify recovery first; do not delete a record
to bypass the check. A failed or inaccessible driver may require separately authorized system recovery.

## Validation: 2026-09-30

The suite covers socket-to-worker operation, release/disconnect/expiry, ownership handshakes, denied writes,
worker kill/stall, failed/hung recovery, and killed/frozen service processes with shared simulated policies.
Bundle tests check isolated imports without hardware, hashes, license retention, placeholder configuration,
shell syntax and refusal to overwrite existing files. The unit passes `systemd-analyze verify` on this host.
171 tests pass on Python 3.12.3 and 3.14.6. The existing Reactivex deprecation warning remains.

All new service lifecycle tests used simulated devices without root. Systemd syntax verification is not an
installed service test. No real GPU setter, package installation or service activation was performed here.
The live hardware evidence in [curve trials](nvml-fan-curves.md) remains limited to those earlier experiments.

## References

- [Linux UNIX sockets](https://man7.org/linux/man-pages/man7/unix.7.html): packet semantics and peer credentials.
- [Python clock constants](https://docs.python.org/3/library/time.html#time.CLOCK_BOOTTIME): suspended time.
- [systemd service reference source](https://github.com/systemd/systemd/blob/main/man/systemd.service.xml): watchdog, cgroup lifecycle and post-stop execution.
- [systemd execution reference source](https://github.com/systemd/systemd/blob/main/man/systemd.exec.xml): runtime directories and hardening.

Reviewed 2026-09-30. Whole-host/kernel/driver failure and combined service/worker failure cannot be given an
absolute software recovery guarantee. The staged unit and package are experimental and await live review.

## Installation follow-up: 2026-09-30

The owner ran the installer from `build/fan-service-review-final` (service code at commit `626c8ae`).
All manifest checks passed. Independent inspection confirmed that installed modules, entry point, binding,
license and unit match the reviewed bundle, with root ownership and configuration mode 0600. Systemd
reports `inactive` and `static`; no service activation or GPU write occurred. This supersedes the earlier
pre-installation status above. System Python packages and the installed GWE Flatpak were not changed.

A repository helper now configures the placeholder without printing identity:

```bash
sudo /usr/bin/python3 -I -B scripts/configure_fan_service.py
```

Run it from the checkout as the intended desktop account using sudo. It reuses the installed entry point's
root-ownership/import checks, obtains the sudo caller's UID, requires exactly one RTX 3090 Ti with two fans,
and queries its UUID using read-only NVML calls. It refuses an already populated or changed configuration.
It atomically replaces only the placeholder, retains mode 0600 and validates the result. It never starts
services or invokes GPU setters. The UUID stays in the private system configuration, outside Git/output.

Four new simulated helper tests pass on Python 3.12 and 3.14, covering read-only discovery, refusal to replace
existing configuration, rejection of a root desktop account and cleanup after a mismatched GPU count.
The preceding 171-test suite remains the last full-suite run; the configuration helper has not yet been
executed with administrator privileges. No reinstallation is required for this repository-only helper.
