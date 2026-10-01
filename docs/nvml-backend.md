# Read-only NVML backend

`gwe.nvml_backend.NvmlBackend` provides telemetry independently of GTK, X11, settings and profile databases.
The diagnostic CLI now shares its collector. The default GUI still uses the legacy `NvidiaRepository` path. The opt-in [monitor mode](monitor-mode.md)
now routes that repository to this backend and bypasses the NV-CONTROL startup gate; its Python 3.12 GTK launch has passed the current-host smoke check.

## Contract

```python
from gwe.nvml_backend import NvmlBackend

backend = NvmlBackend()
snapshot = backend.read_snapshot()
# Keep UUIDs in application memory; do not paste them into shared diagnostics.
uuid = snapshot["gpus"][0]["uuid"]["value"]  # Check status and device presence first.
selected_snapshot = backend.read_snapshot(gpu_uuid=uuid)
```

Check snapshot and field statuses before accessing values. Discovery queries UUIDs for stable identification.
Selection resolves the requested UUID on each call and checks the returned identity; missing or mismatched
identity never falls back to another device. Indices are current NVML indices, not persistent identifiers.
A device whose identity cannot be read is reported as an error and its telemetry is not collected.

Each call initializes NVML and attempts shutdown after successful initialization, including on unexpected
exceptions. Calls on one backend instance are serialized. Handles and readings are not cached between calls,
so transient failures cannot return a previous temperature as if it were fresh. Monotonic start/end timestamps
bound the collection interval; individual NVML calls do not form an atomic hardware snapshot.

Readings include temperature (Celsius), per-fan speed (percent and RPM), manual fan limits, memory (bytes), utilization
(percent), current/maximum clocks (MHz), and power draw/limits (watts, converted from NVML milliwatts). Each query reports its own availability/error.
Missing optional metrics do not suppress other readings. There is no inferred permission to write and no setter.
Consumers must treat failed temperature reads as unusable for future fan control.

The JSON-compatible collector uses schema version 2. The public diagnostic command omits identity queries;
the application backend includes UUIDs and must not be logged wholesale. See [diagnostics](nvml-diagnostics.md)
for status meanings. Neither this class nor the CLI monitors continuously or restores fan policies.

## Validation

On the existing RTX 3090 Ti / driver 580.178.04 setup, both Python 3.12.3 and 3.14.6 passed discovery and a
second read selected by UUID with DISPLAY and WAYLAND_DISPLAY removed. UUIDs were retained only in memory
and redacted from test output. Temperature, two fans, memory, utilization and power were readable.
This is not a Wayland session or Kubuntu 26.04 UI test.

The combined suite has 26 passing tests on each interpreter. Added scenarios cover index changes,
missing selected devices, identity mismatch/unavailability, invalid selection, unit conversion and recovery
across snapshots without stale readings. Driver calls remain simulated in automated tests.

## Extended telemetry: 2026-10-01

Schema 2 has additive optional fields: `power_limit_w`, `power_default_w`, `power_enforced_w`,
`power_constraints_w` (minimum/maximum), `clocks_mhz` (graphic/sm/memory/video, current/max), and
per-fan `speed_rpm`. Every query keeps an independent status. Missing constants or binding helpers
are unavailable; unsupported driver reads have no value. UI adaptation clears missing values and
preserves zero, while keeping all direct write capabilities disabled.

The installed binding's public RPM function fixes the fan index at zero. A narrow compatibility
adapter uses its existing versioned structure and private symbol/error helpers to call only
`nvmlDeviceGetFanSpeedRPM`, once per fan index. It does not patch the installed binding or copy fan-zero
readings to other fans. Missing helpers leave RPM unavailable. This private-helper dependency needs
revalidation when updating the binding. NVIDIA describes these fan readings as intended speed;
they are not an independent check that a physically obstructed fan is rotating.

Live read-only queries succeeded on Python 3.12 and 3.14 with driver 580.178.04. Observed power limit
and enforced limit were 250 W, default/maximum 480 W, minimum 100 W. All eight clock fields and both
RPM fields were readable (both fans reported 0% and 0 RPM in the recorded snapshot). No settings were
changed. The full simulated suite passed 251 tests on each interpreter; new cases cover unit conversion,
clock-domain isolation, indexed RPM, zero values, optional API absence, partial errors and stale-value
clearing. Python 3.12/X11 main-window preview also verified displayed values and disabled write controls.
See the [API references](technical-references.md) and [main-window guide](main-window-service.md).
