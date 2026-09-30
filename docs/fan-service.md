# Experimental local fan-service boundary

`gwe.fan_service` implements the client/transport and lease state machine for the next service stage.
It is tested with simulated backends only. There is no runnable privileged daemon, systemd installation,
root-to-desktop socket provisioning, GTK integration or live NVML adapter in this module. Do not connect
blocking NVML methods directly to its event loop. The default GWE backend and private profiles are unchanged.

## Implemented protocol

Linux UNIX sequenced-packet sockets carry one JSON request/response per packet. The service checks kernel
peer credentials against one configured allowed UID. Identity supplied in a message is never accepted.
The endpoint is created in a service-owned mode-0700 directory and has mode 0600; an existing endpoint is
never replaced. These development permissions support same-user tests, not yet root-to-desktop access.

Requests have protocol `version: 1` and one of four operations:

| Operation | Fields beyond version/op | Behavior |
| --- | --- | --- |
| status | None | Return state and whether this connection owns the lease |
| acquire | points, hysteresis, vbios_silent | Validate a curve and start one backend session |
| renew | None | Extend this connection's active lease by five seconds |
| release | None | Stop the owned backend session and require restoration |

Curve points are explicit numeric pairs, at most 32. The existing `FanCurve` validation applies; device
limits must additionally be checked by the eventual supervised backend. Requests are limited to 4096 bytes;
unknown/duplicate fields, unsupported versions/operations and invalid data are rejected. No client-selected
UUID, path, program, import, power operation or clock operation exists in this protocol. Device identity and
backend policy must come from trusted service configuration. Responses omit internal exception messages.

The owner is a particular persistent connection, not just a UID. Other connections cannot replace, renew
or release its session. Disconnect and malformed owner requests stop its session. Expiry is checked before
processing requests, so a late renewal cannot revive an expired lease. A new explicit acquisition is needed.
CLOCK_BOOTTIME includes suspended time; this prevents resuming an expired lease on a future service, but is
not itself a suspend hook or proof of recovery while the host is asleep.

Backend startup faults latch after attempting cleanup. Failed cleanup becomes `recovery_failed` and blocks
new acquisition. Successful release/expiry returns to idle. The service uses nonblocking socket I/O, accepts
at most eight clients and caps event-loop waits at 100 ms. A client that cannot receive its response is
disconnected rather than allowed to block lease processing. The backend contract must also remain bounded.

## Backend contract and remaining integration

The injected backend currently has `start(curve)` and `stop()` operations. `stop()` must return only after
verified automatic restoration, or raise. Startup cleanup must never reset an unrelated controller. All
backend calls must be bounded and must not execute native NVML in this event-loop process. The tests use
an in-memory backend to validate protocol state transitions separately from previously tested NVML logic.

Next implementation work must connect this boundary to an independently supervised worker with trusted
UUID selection and device revalidation. It must expose asynchronous worker faults, serialize recovery,
ensure connection expiry cannot race another manual write, and propagate recovery failure into service
status. The existing bounded trial supervisor does not yet provide that persistent backend interface.

Before deployment, prepare a reviewed administrator-owned installation, controlled socket access for the
selected desktop user, process/watchdog lifecycle, independent recovery on daemon failure, suspend hooks,
and explicit coexistence rules for CoolerControl/GWE. No root daemon may import the development checkout.
Installation, enablement and private-profile migration are separate steps, not performed here.

## Validation: 2026-09-30

136 tests pass on Python 3.12.3 and 3.14.6. New tests use actual local sockets and kernel peer credentials
without administrator privileges or GPU calls. They cover client requests, rejection of the wrong UID,
connection ownership, renewal/expiry, malformed input, startup/recovery failures, redacted errors,
disconnect cleanup and preservation of existing endpoint files. The existing Reactivex warning remains.
The previously recorded hardware results belong to the standalone curve trial; they do not validate this
new protocol/service boundary on hardware. No system service or GPU setting changed in this stage.

## References

- [Linux UNIX sockets](https://man7.org/linux/man-pages/man7/unix.7.html): local packet semantics and peer credentials.
- [Python time constants](https://docs.python.org/3/library/time.html#time.CLOCK_BOOTTIME): clock including suspended time.

Reviewed 2026-09-30; local socket tests establish behavior in both current development interpreters.
