# Read-only NVML diagnostics

The standalone probe reads one telemetry snapshot without importing the GTK application, opening an X display,
loading profiles or changing GPU settings. It uses `nvidia-ml-py` and does not require the CUDA Toolkit.
It shares the collector with the [read-only backend](nvml-backend.md); the GUI has not yet been migrated.

## Run

From the repository root, with a prepared Python environment active:

```bash
python -m gwe.nvml_probe
```

To check without graphical-session variables:

```bash
env -u DISPLAY -u WAYLAND_DISPLAY python -m gwe.nvml_probe
```

Direct dependency versions are recorded in `requirements-diagnostics.txt`. This is a separate diagnostic/test
set, not the existing GTK application's requirements or a complete transitive dependency lock.

## Output and exit status

JSON includes the interpreter and binding versions, driver version, device count, model names, temperature
in Celsius, fan count, manual fan range, individual speeds in percent, memory in bytes, utilization in percent
and power in watts. Schema version 2 adds these metrics. The CLI does not query UUIDs, serial
numbers, process lists or personal profiles. Device indices only identify entries in that snapshot.

Each reading has a status: `ok`, `unsupported`, `unavailable` (missing binding/driver function), or `error`.
Unavailable readings have no numeric value; they are never silently represented as zero.
The top-level `errors` list records NVML failures, including shutdown failures. Per-field results locate
failed telemetry. Unexpected programming errors propagate after attempting NVML shutdown.

Exit code 0 means enumeration completed with at least one GPU and no NVML failures; optional unsupported
or unavailable queries are allowed. Exit code 1 means an NVML failure, inability to enumerate/access devices,
no devices, or a missing binding. Inspect individual fields even when the command succeeds.
Successful reads do not establish write permissions, fan control support or successful restoration of automatic policy.

## Automated tests

```bash
python -m pytest -q
```

Tests inject a simulated binding and never initialize the actual driver. Coverage includes successful reads,
missing/unsupported functions, permission errors, device loss, partial fan-read failure, no devices,
initialization/enumeration/shutdown failures, unexpected exceptions and CLI output/exit codes.

## Validation: 2026-09-30

| Check | Python 3.12.3 | Python 3.14.6 |
| --- | --- | --- |
| nvidia-ml-py 13.615.71, pytest 9.1.1 | Installed | Installed |
| Simulated tests | 16 passed | 16 passed |
| pip check | Passed | Passed |
| Real read-only probe without DISPLAY/WAYLAND_DISPLAY | Passed | Passed |

Both runs detected the RTX 3090 Ti with driver 580.178.04, two fans and a manual range of 30–100%.
The snapshot temperature was 34 °C and reported fan speeds were 31% and 32%; these are observations,
not control targets. No setters or policy resets were called.

The host was still the existing Ubuntu 24.04/KDE setup. Removing display variables is not a Wayland session
or Kubuntu 26.04 acceptance test. The GWE UI still uses its historical backend, and write/recovery tests remain pending.

## Backend follow-up

The shared collector and UUID-aware backend expand the suite to 26 passing tests on each interpreter.
Live reads of the added metrics and UUID selection also passed with display variables removed.
The CLI still omits UUIDs; only explicit backend use queries identity. See the [backend record](nvml-backend.md).
