# Validation and remaining acceptance

This is the current evidence summary, not a guarantee for arbitrary GPUs or drivers. Detailed build
provenance belongs in each artifact's `BUILD_INFO` and `SHA256SUMS`; private diagnostic records are not
published. No new hardware checks were performed during the documentation consolidation.

## Current candidate

- Application: **1.0.0-rc1**.
- Latest prepared package: **1.0.0~rc1-9**, runtime source `82f8087`.
- Build/test runtime: system Python **3.14.4**, reviewed standalone dependency inputs.
- Recorded target: RTX 3090 Ti, two fans, NVIDIA **580.178.04**, KDE, Kubuntu **26.04.1/Wayland**.
- Latest complete source suite: **632 passing tests** (2026-10-10).

No confirmation of installation or final KDE icon rendering for the latest prepared package has been
recorded. A prepared package is not a published release.

## Evidence

| Scenario | Result and scope |
| --- | --- |
| Backend/control/package tests | 632 simulated tests pass, including failure paths and subprocess supervision |
| Native package build | Pass on Python 3.14 with preserved inputs, independent of an older interpreter environment |
| Extracted candidate GTK on Wayland | Pass with synthetic control and real telemetry reads; isolated protocol identity verified |
| Public and tray icon lookup | GTK loads native/original/symbolic assets; final installed KDE rendering pending |
| Installed startup/editor/tray/Quit | Hardware pass on the recorded target with controller runtime `8c6ad03` |
| Client loss/freeze and supervisor SIGKILL/watchdog | Hardware pass at that runtime; fans automatic, current power unchanged, prior cooling-service state restored |
| Power transactions and recovery | Supervised write/readback and guarded supervisor-failure recovery passed; CUDA-load use reported successful |
| Saved power restoration | Owner reports successful restoration; independent read-only check found saved and live targets matching |
| Automatic curve resume | Clock/worker/GTK simulations pass; installed suspend/reacquisition acceptance pending |
| Video-engine telemetry | Controlled NVENC/NVDEC readings matched direct telemetry; playback alone does not establish hardware decoding |

Hardware evidence from an earlier runtime does not establish installed acceptance of every later
change. The latest isolated Wayland check proves the test window uses Wayland, not that every installed
launch has the same backend. Measured extended uninterrupted operation and driver/host-failure recovery
are not established.

## Remaining checks

1. Install the latest candidate after Quit/recovery and verify both the tray and window icons in KDE.
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
