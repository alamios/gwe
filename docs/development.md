# Development and testing

Develop on `main`. Preserve user changes, existing tags and original copyright/license notices.
Write documentation, comments and commits in English. See [CONTRIBUTING.md](../CONTRIBUTING.md)
and [AGENTS.md](../AGENTS.md).

## Environment

The current target-host baseline is system Python 3.14 with distribution GTK3, PyGObject, Cairo,
Matplotlib and the package's declared native dependencies. Backend interpreter tests alone do not
reproduce the desktop library stack. Missing dependencies require explicit setup; do not modify system
Python or install the requirements files blindly.

Use reviewed pure-Python dependency inputs with distribution metadata and licenses. The builder's
exact versions are in `scripts/build_debs.py`. Set `GWE_BUILD_INPUTS` to their standalone directory:

```bash
export GWE_BUILD_INPUTS="$PWD/.local-backups/build-dependencies-py314"
PYTHONPATH="$GWE_BUILD_INPUTS" /usr/bin/python3 -m pytest -q
```

This local preserved directory is not a published dependency download. A new checkout must prepare
the reviewed inputs as described in [packaging](packaging.md). Pytest is a development prerequisite.
The test suite uses simulated driver calls, local Unix sockets and real subprocess supervision;
a sandbox must allow these mechanisms. Permission failures are not hardware-test results.

## Read-only diagnostics

```bash
PYTHONPATH="$GWE_BUILD_INPUTS" /usr/bin/python3 -m gwe.nvml_probe
```

The JSON schema reports individual field statuses; unavailable values must not be treated as zero.
The CLI returns zero for a successful report and nonzero for a failed report. It does not initialize
GTK, read private profiles or write GPU settings. Avoid publishing identity-bearing internal snapshots.

## Separate graphical checks

```bash
PYTHONPATH="$GWE_BUILD_INPUTS" /usr/bin/python3 scripts/run_monitor.py --smoke-test
PYTHONPATH="$GWE_BUILD_INPUTS" /usr/bin/python3 scripts/run_service_gui.py --smoke-native
```

The monitor isolates configuration and blocks fan, power and clock writes, including cleanup writes.
The native graphical check uses synthetic profiles, settings and control, with real read-only NVML
telemetry. It exercises the editor, tray, Quit, GTK stalls, faults and simulated suspend/reacquisition.
A graphical session and resource/schema compilers are required for source checks. Extracted-package
checks must use the package's own dependencies and resources rather than the developer environment.

Do not substitute `python -m gwe` or a normal native launch for a read-only check: startup can reapply
saved fan and power settings. GUI checks and backend tests have separate acceptance scope.

## Hardware acceptance

Prepare a supervised procedure, fresh read-only baseline and recovery plan before writes. Never run
a development controller concurrently with another controller on the same GPU. Agree on idle/workload,
fan/power bounds and current baseline; do not reset to a value taken from a previous test report.

Installed lifecycle checks can apply the saved fan curve. Fault checks can stop the service and restore
cooling. Run only with the GPU available, GWE closed through Quit and explicit operator authorization:

```bash
/usr/bin/python3 scripts/check_installed_session.py --native
/usr/bin/python3 scripts/check_native_recovery.py
```

The second command requests sudo authentication and injects supervisor SIGKILL/SIGSTOP. It targets
`--kill-whom=main`, preserving systemd's independent recovery path. Never substitute a bulk cgroup kill.
The startup-only acceptance mode excludes saved-power restoration; the ordinary launches used by fault
checks can restore a saved power target, so first verify that it matches the current hardware limit.
No clocks or synthetic workload should be added to these checks.

Record revision, package checksum, GPU/driver/OS/session, scenario and independent recovery outcome.
A successful emergency cleanup does not convert a failed test into a pass. Acceptance of one revision
is not automatic acceptance of later runtime changes. See [validation](validation.md).
