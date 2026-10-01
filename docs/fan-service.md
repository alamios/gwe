# Experimental supervised fan service

The local protocol is now connected to `ProcessBackend`, which executes the NVML controller and recovery
in separate processes. A root-owned installation bundle, a 60-second systemd trial unit and an unprivileged
test client are prepared. The owner has installed the reviewed bundle and passed normal-release, client-disconnection and lease-expiry hardware
trials with an unprivileged client. Complete-service SIGKILL post-stop recovery also passed on hardware.
Complete-service SIGSTOP/watchdog recovery also passed. It is stopped after testing; suspend/resume,
extended operation and driver/host failure validation remain pending. The default
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
new control. The ten-second systemd watchdog covers a stuck main event loop. Complete-service SIGKILL
and SIGSTOP/watchdog post-stop recovery passed the hardware trials recorded below. Worker EOF/lease recovery has been tested using a killed/frozen simulated service.

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

## Hardware procedure (normal/disconnect/expire validated)

Only after installation/configuration approval and read-only baseline verification, use the prepared
Python 3.12 environment in the checkout. The client runs as the ordinary user:

```bash
sudo -v && (
    cleanup() {
        sudo systemctl stop gwe-fan-service.service
        if sudo test ! -e /run/gwe-fan-service/owned.json; then
            sudo systemctl start coolercontrold.service
        else
            echo 'Recovery pending; CoolerControl remains stopped'
        fi
    }
    trap cleanup EXIT
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

## Configuration follow-up: 2026-10-01

The owner ran the isolated helper from commit `82b34be` and supplied its successful configuration-validation
output. Identity was not displayed. The configuration is now populated; the earlier placeholder status
is historical. The helper did not start the service or write GPU settings.

Independent read-only preflight confirmed the service inactive/static, CoolerControl active and GWE absent
from Flatpak process enumeration. The host remains X11, kernel 7.0.0-34-generic, driver 580.178.04 and RTX
3090 Ti. Both fan policies were automatic, reported speeds zero, temperature 51 C and power limit 250 W.
At this preflight stage the first installed-service/client hardware run had not yet occurred; its result follows.

## Normal installed-service hardware trial: 2026-10-01

The owner ran the normal client from repository commit `4eacd8a`, against the installed service bundle
from `626c8ae`. The client ran without sudo and reported an active curve followed by
`Service reports idle after verified automatic recovery`. This exercises socket peer authorization,
acquisition, the ownership handshake, supervised NVML control, renewal, release and verified recovery.
The client output does not include per-tick telemetry, so no duty/temperature trace is inferred here.

Independent follow-up confirmed:

- Service inactive/static, `Result=success`, `ExecMainStatus=0`.
- No pending `/run/gwe-fan-service/owned.json` record; CoolerControl active again.
- Both NVML fan policies zero (automatic), reported speeds zero, X11 `GPUFanControlState` zero.
- Driver 580.178.04, temperature 51 C, power limit unchanged at 250 W.

The subsequent `disconnect` scenario closes the owning socket without requesting release and observes
recovery through another unprivileged connection. Its result and the subsequent lease-expiry result are recorded below;
service-failure scenarios remain pending. No new code or automated test execution was needed for this result record.

## Client-disconnection hardware trial: 2026-10-01

The owner ran `--scenario disconnect` from repository commit `124ba39` against the unchanged installed
service bundle (`626c8ae`). The client reported an active curve, then idle after verified automatic
recovery. In this scenario it closes the owning connection without sending `release`; a separate
unprivileged observer connection waits for idle. This validates disconnect-triggered recovery on this host,
not merely normal explicit release. The terminal output contains no per-tick duty or temperature trace.

Independent follow-up confirmed service inactive/static with `Result=success` and `ExecMainStatus=0`,
no pending ownership record, CoolerControl active, both NVML policies automatic, reported speeds zero,
X11 `GPUFanControlState` zero, driver 580.178.04, temperature 53 C and power limit unchanged at 250 W.

The subsequent trial used `--scenario expire` separately: the client keeps its connection open and queries status but stops
renewing its five-second lease. Successful recovery must occur despite that open connection. Service-failure
hardware scenarios remain separate pending checks. This update only records results; no code changed or
additional automated tests ran.

## Lease-expiry hardware trial: 2026-10-01

The owner ran `--scenario expire` from repository commit `696ae7e` against the unchanged installed service
bundle (`626c8ae`). The client reported an active curve and then idle after verified automatic recovery.
Unlike disconnect, it retained the owning connection and continued status queries, but stopped renewing
its five-second lease. This validates recovery despite an open client connection; status traffic does not
extend ownership. The output does not contain elapsed timestamps or a per-tick telemetry trace.

Independent follow-up confirmed service inactive/static, `Result=success`, `ExecMainStatus=0`, no pending
ownership record and CoolerControl active. Both NVML policies and X11 `GPUFanControlState` were zero,
reported speeds were zero, driver remained 580.178.04, temperature was 56 C and power limit remained 250 W.

| Installed-service scenario | Client behavior | Independently checked final result |
| --- | --- | --- |
| Normal | Explicit release | Both fans automatic, clean shutdown |
| Disconnect | Close owner socket without release | Both fans automatic, clean shutdown |
| Expire | Keep socket open without renewal | Both fans automatic, clean shutdown |

This completes the initial client-lifecycle hardware matrix. Installed-service crash/watchdog/post-stop
recovery, suspend/resume, extended operation and Wayland remain unvalidated. The earlier standalone worker
fault tests do not replace service-level hardware tests. No code changed or automated tests were rerun
for this documentation-only result update. GWE integration and private-profile migration remain separate.

## Prepared complete-service SIGKILL trial: 2026-10-01

The repository client now accepts `--scenario service-kill`. It needs no service reinstallation: installed
service code remains `626c8ae`. After active control and brief renewal, the client requires an active unit
and an existing ownership record, then runs this fixed command using the operator's cached sudo credentials:

```bash
sudo -n systemctl kill --kill-whom=all --signal=SIGKILL gwe-fan-service.service
```

The local systemctl help confirms `--kill-whom` support. The signal targets the complete service cgroup,
including the controller, preventing ordinary worker/service cleanup. Systemd should then execute the
installed post-stop recovery. The client waits at most 20 seconds for a terminal unit state and no remaining
control process, requires `Result=signal`/`ExecMainStatus=9`, verifies that the ownership record is gone, and
independently reads both NVML policies as automatic. It also reports temperature/power limit without UUIDs.
The service is expected to be marked failed due to the deliberate signal; that alone is not a recovery
failure. No recovery command is sent through the dead client socket.

Run with the same stop/start/cleanup shell block above, changing only the client scenario to `service-kill`.
Keep GWE closed and avoid loads. The cleanup block stops the unit and restarts CoolerControl only if no
unresolved ownership record remains. A privilege error, unexpected unit result, timeout, remaining record
or nonautomatic policy is a failed test. Paste the result before proceeding to a watchdog/stall scenario.

Six new orchestration tests pass on both Python versions using simulated subprocesses and telemetry. They
cover fixed-unit targeting, stale ownership records, unexpected failure results, inactive-unit refusal,
privilege failure and timeout. The subsequent hardware result is recorded below.

The full regression suite now passes on both Python 3.12 and 3.14: 181 tests per interpreter,
with the existing Reactivex deprecation warning. This includes the configuration-helper tests.

## Complete-service SIGKILL hardware trial: 2026-10-01

The owner ran `--scenario service-kill` from repository commit `c525ef3` against the unchanged installed
service bundle (`626c8ae`). The client confirmed active control before sending SIGKILL to the service and
its control processes. It then verified completed systemd post-stop recovery, no pending ownership record,
and both NVML policies zero (automatic), at 57 C with a 250 W power limit. The unit reported the expected
`Result=signal` and `ExecMainStatus=9`; its failed state records the deliberate termination.

Independent read-only follow-up confirmed:

- Unit failed/static, `Result=signal`, `ExecMainStatus=9`, `ControlPID=0`.
- Ownership record absent and CoolerControl active again.
- Both NVML policies automatic, temperature 57 C and power limit still 250 W.

This validates post-stop recovery after killing the complete service while the driver and systemd remain
responsive. It does not establish recovery from a stalled service, watchdog expiry, suspend/resume or
an unresponsive driver/host. Those scenarios, extended operation, Wayland and GUI/profile integration
remain pending. The installed service remains a bounded trial and is not enabled at boot.
This update records hardware results only; no code changed and no automated tests were rerun.

## Prepared complete-service watchdog trial: 2026-10-01

The repository client accepts `--scenario service-watchdog`, without changing or reinstalling the
installed bundle (`626c8ae`). It waits for active control, briefly renews ownership, and checks the installed
unit is active with an ownership record, `WatchdogUSec=10s`, `WatchdogSignal=9`,
`KillMode=control-group`, `TimeoutStopUSec=15s` and `SendSIGKILL=yes`. Unexpected configuration refuses
fault injection. It then sends this fixed command using cached sudo credentials:

```bash
sudo -n systemctl kill --kill-whom=all --signal=SIGSTOP gwe-fan-service.service
```

Freezing the complete service also freezes the controller: its own lease expiry cannot restore automatic
control while stopped. The intended recovery is watchdog termination followed by systemd post-stop
recovery. The client makes no further socket requests or renewals after injection, waits at most 40 seconds
for a terminal unit state with `ControlPID=0`, and requires `Result=watchdog` and `ExecMainStatus=9`.
An unrelated SIGKILL (`Result=signal`) is not accepted as a watchdog pass. Success also requires no
ownership record and independent automatic NVML policies on both fans; temperature and power limit are
reported without private identity.

Systemd's [kill documentation](https://github.com/systemd/systemd/blob/main/man/systemd.kill.xml)
describes watchdog signals and bounded control-group shutdown; its
[service documentation](https://github.com/systemd/systemd/blob/main/man/systemd.service.xml)
describes watchdog failure and post-stop commands. Actual timing and recovery still need this hardware
trial. The wait budget allows the ten-second watchdog, fifteen-second shutdown timeout and bounded
post-stop recovery; it does not guarantee recovery from an unresponsive driver or host.

Use the preceding stop/start/cleanup shell procedure with scenario `service-watchdog`, keeping GWE closed
and avoiding loads. Strengthen its cleanup condition to restart CoolerControl only after
`sudo systemctl stop gwe-fan-service.service` succeeds **and** no ownership record remains. If the client
fails or is interrupted, that stop operation terminates the experimental unit and runs its post-stop
recovery. If stopping fails or the record remains, keep CoolerControl stopped and investigate recovery.
Expected final output is `Expected service result: watchdog / SIGKILL; recovery completed`; failed unit
state is expected after this deliberate stall.

Five additional simulated tests cover complete-unit SIGSTOP, refusal of unexpected watchdog configuration,
rejection of an ordinary signal result, retained recovery records and the bounded extended wait.
The subsequent hardware result is recorded below.

Full regression: 186 tests pass per interpreter on Python 3.12 and 3.14, with the existing
Reactivex deprecation warning. No real fault signals or GPU writes occurred during these automated tests.

## Complete-service SIGSTOP/watchdog hardware trial: 2026-10-01

The owner ran `--scenario service-watchdog` from repository commit `79802cb` against the unchanged
installed service bundle (`626c8ae`). After confirming active control, the client sent SIGSTOP to the
complete service and its control processes. It observed the required watchdog failure followed by
completed post-stop recovery: both fan policies zero (automatic), no ownership record, temperature
56 C and power limit 250 W. The client accepted `Result=watchdog` and `ExecMainStatus=9`; an ordinary
signal failure would have failed this scenario. The output contains no elapsed timestamps, so an exact
recovery duration is not claimed.

Independent read-only follow-up confirmed:

- Unit failed/static, `Result=watchdog`, `ExecMainStatus=9`, `ControlPID=0`.
- Ownership record absent and CoolerControl active again.
- Both NVML policies automatic, temperature 55 C and power limit unchanged at 250 W.

| Installed-service scenario | Fault or client behavior | Verified final recovery |
| --- | --- | --- |
| Normal | Explicit release | Automatic policies, clean shutdown |
| Disconnect | Owner socket closes without release | Automatic policies, clean shutdown |
| Expire | Open owner connection stops renewing | Automatic policies, clean shutdown |
| Service kill | SIGKILL to complete service | Automatic policies, post-stop recovery, signal result |
| Service watchdog | SIGSTOP to complete service | Automatic policies, post-stop recovery, watchdog result |

This completes the initial bounded client-lifecycle and service-failure hardware matrix on the current
X11 host. It establishes recovery while systemd and the NVIDIA driver remain responsive. Suspend/resume,
extended continuous operation, driver/host failures, Wayland and GUI/private-profile integration remain
pending. The installed unit is still a sixty-second manual trial, is not enabled at boot and does not
replace the installed GWE application. No private profiles were migrated.
This update records results only; no code changed and no automated tests were rerun. The last full
regression remains 186 passing tests per interpreter on Python 3.12 and 3.14.
