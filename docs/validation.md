# Validation and remaining acceptance

This is the current evidence summary, not a guarantee for arbitrary GPUs or drivers. Detailed build
provenance belongs in each artifact's `BUILD_INFO` and `SHA256SUMS`; private diagnostic records are not
published. No new hardware checks were performed during the documentation consolidation.
The fork is intended exclusively for the maintainer's personal use; hardware and desktop evidence
comes only from that personal system. Broader compatibility is not a project goal.

## Current candidate

- Application: **1.0.0-rc1**.
- Latest prepared package: **1.0.0~rc1-11**, built from `df4690a` plus the external-fan changes before commit;
  exact source patch and build provenance retained with the local artifact.
- Build/test runtime: system Python **3.14.4**, reviewed standalone dependency inputs.
- Recorded target: RTX 3090 Ti, two fans, NVIDIA **615.71.09** (open kernel module), KDE,
  Kubuntu **26.04.1/Wayland**, AMD64.
- Latest complete source suite: **667 passing tests** (2026-11-07, under Xvfb).

Read-only inspection on 2026-10-11 confirms installed package **1.0.0~rc1-9** and active driver
**615.71.09**, matching both `nvidia-smi` and the loaded NVIDIA open kernel module. The maintainer
reports continued normal operation after updating the driver. No writes or fault injections were
performed during this inspection. Final installed KDE icon rendering remains unconfirmed; installation
does not establish publication or acceptance of every scenario.

## Evidence

| Scenario | Result and scope |
| --- | --- |
| Backend/control/package tests | 667 tests pass, including failure paths, subprocess supervision and isolated GTK |
| Native package build | Pass on Python 3.14 with preserved inputs, independent of an older interpreter environment |
| Extracted candidate GTK on Wayland | Pass with synthetic control and real telemetry reads; isolated protocol identity verified |
| Public and tray icon lookup | GTK loads native/original/symbolic assets; final installed KDE rendering pending |
| Installed startup/editor/tray/Quit | Hardware pass on the recorded target with controller runtime `8c6ad03` |
| Client loss/freeze and supervisor SIGKILL/watchdog | Hardware pass at that runtime; fans automatic, current power unchanged, prior cooling-service state restored |
| Power transactions and recovery | Supervised write/readback and guarded supervisor-failure recovery passed; CUDA-load use reported successful |
| Saved power restoration | Owner reports successful restoration; independent read-only check found saved and live targets matching |
| Driver update to 615.71.09 | Active driver/module and installed rc1-9 confirmed read-only; continued normal operation reported by the maintainer |
| Automatic curve resume | Clock/worker/GTK simulations pass; installed suspend/reacquisition acceptance pending |
| Video-engine telemetry | Controlled NVENC/NVDEC readings matched direct telemetry; playback alone does not establish hardware decoding |

The recorded installed lifecycle and supervisor-recovery checks used driver **580.178.04**; they have
not been repeated on **615.71.09**. Hardware evidence from an earlier runtime does not establish installed acceptance of every later
change. The latest isolated Wayland check proves the test window uses Wayland, not that every installed
launch has the same backend. Measured extended uninterrupted operation and driver/host-failure recovery
are not established.

## Autostart correction and acceptance (2026-11-06–07)

On system Python 3.14.4, the focused command
`/usr/bin/python3 -m pytest -q tests/test_desktop_entry.py tests/test_runtime_mode.py tests/test_native_launcher.py`
passes **12 tests**, including five new autostart cases. Temporary-directory tests cover removing both
enabled and legacy disabled entries, repeated removal, a missing directory, preservation of unrelated
entries, native command recreation and a simulated permission failure. No personal autostart files,
GTK sessions, services or GPU settings were changed. This is focused source validation, not a new full
suite result or installed Plasma acceptance. The prepared rc1-10 package contains this fix.

Package rc1-10 was built on 2026-11-06 with verified standalone dependency checksums. The focused
autostart, native packaging and native launcher tests pass **17 tests**. Extracted-package inspection
confirmed the fixed source, compiled resources and vendor metadata; an isolated enable/disable cycle
passed using the extracted code. No installation or real desktop launch was performed.

On 2026-11-07, the maintainer reported no login startup after manually removing the legacy disabled
entry, then confirmed successful startup after the enabled-case test was requested for rc1-10.
This is owner-reported functional acceptance on the personal Plasma system, not an independently
captured session trace. Automatic file removal and recreation are covered by the isolated tests above;
the report does not separately establish inspection of every file key or tray behavior.
Old disabled entries still require the cleanup described in the
[user guide](user-guide.md#startup-and-suspend).

## Remaining checks

### External fan control

On 2026-11-07, the complete suite passed **667 tests** on system Python 3.14.4 with reviewed standalone
inputs and Xvfb. One existing dependency deprecation warning was reported. External-mode coverage includes
strict/legacy handshake parsing, blocked fan operations, permitted power requests and identity rejection,
preference persistence and write failure, conflicting modes, pending recovery and stale overrides.
Simulated daemon startup/shutdown/failure and post-stop recovery reject any cooling-service command or
fan worker creation. An isolated GTK/ORM check verifies the preference, disabled fan actions, suppression
of a saved curve and continued power scheduling. No installed service, personal profiles or GPU setters
were used. Existing power tests cover stale/missing telemetry, bounds, permissions and verified rollback.

Package **1.0.0~rc1-11** was built with verified standalone dependency checksums. Its extracted helper
and desktop match the reviewed sources. The GTK/ORM integration check also passes using the extracted
package's vendor modules and compiled resource, with temporary configuration and no hardware access.

The owner reports successful ordinary use with CoolerControl on 2026-11-07. This is functional owner
feedback, not independent evidence for every power, suspend or failure scenario, or for other controllers.
The source now uses the generic label "Let another application manage fans"; rc1-11 retains the older
CoolerControl label with the same behavior.

For detailed installed acceptance, with CoolerControl configured and active, launch the updated
package with `gwe-nvml --external-fans`; verify CoolerControl remains active, fan actions are disabled and
power telemetry remains available. Save the preference and verify ordinary and login launches retain
the mode. Under a separately authorized hardware procedure, verify one power change/readback and the
chosen final target, plus Quit/reopen, suspend and service-failure recovery without disturbing external
cooling. Return to ordinary mode only with an explicit cooling handoff. Clock offsets are not implemented.

### Other hardware and desktop acceptance

1. Verify both the tray and window icons in the installed candidate on KDE.
2. With the applied curve active and the GPU available, suspend/resume once. Verify new service ownership
   and resume diagnostics, not just the selected profile label. Preserve the current power limit.
3. Record a controlled reboot/startup check for the saved power target. Verify matching GPU identity and
   independent live readback after GWE starts; distinguish application restoration from a boot-time setter.
4. Record an extended ordinary session and check control ownership, temperatures, diagnostics and final
   recovery. A report of "works so far" does not establish a measured soak duration.
5. Revalidate identity, limits, permissions, telemetry, writes and recovery after a relevant driver or
   hardware change. Do not extrapolate one driver/GPU result to all configurations.

Use the [development procedures](development.md) and update this summary with revision, scenario and
independent outcome. Fault checks need explicit operator authorization. Do not run bulk kill against
recovery processes or describe emergency cleanup as a passing acceptance result.
