# Maintenance plan

Working branch: `main`. The completed `maintenance/nvml-revival` phase is merged without squash;
`upstream-baseline` preserves the inherited original code.
Initial target: NVIDIA GeForce RTX 3090 Ti, preserving custom fan curves during migration from Kubuntu 24.04/X11
and preparation for Kubuntu 26.04/Wayland. See the [observed baseline](setup-compatibility.md).

## Status and decisions

- Release preparation on 2026-10-03: the 1.0.0-rc1 source now contains one native package, authenticated
  socket activation, writable profile import/editor, startup persistence and original tray/automatic
  controls. The extracted package passes its isolated GTK check using system Python. The unified rc1-3 package is now installed and the owner reports successful ordinary use;
  recorded recovery and target OS acceptance remain pending.
  See [native desktop](native-desktop.md) and [current packaging](packaging-plan.md).
- Firefox/YouTube zero video readings were reproduced by direct NVML, the installed backend and nvidia-smi.
  Firefox reported hardware decoding blocklisted after a failed decoding test. This is distinct from the
  successful controlled video-engine telemetry checks and is not a GWE release blocker.

- Corrected on 2026-10-03: the monitor/service UI retains its read-only NVML session so video counters
  can accumulate. Available-GPU 1080p60 checks produced matching raw/backend/UI-model nonzero readings;
  nvidia-smi independently confirmed the earlier held-session result. Device-loss reinitialization,
  balanced probes and cleanup are covered by 514 passing tests per interpreter. Old-app playback causes
  and target-driver/Wayland behavior are not inferred from this result.

- Owner follow-up on 2026-10-03: installed menu client works; suspend/resume was reported tested,
  without an independently captured recovery trace. Named startup curve reapplication is now opt-in
  in source with once-per-launch acquisition, fresh-telemetry gating and no fault/release rearming.
  Encoder/decoder zeros during reported accelerated playback remain an inherited unresolved observation.
  Native/Flatpak packaging is still proposed; see [architecture and prerequisites](packaging-plan.md).
  Restore requests during pending renewal are now queued. The startup GTK simulated check passed using
  a separate smoke identity; real automatic startup acceptance requires updating the inactive local client.
  The owner subsequently closed the client; installation with the startup preference and actual rollback/
  return completed. The grouped real acceptance command needs user-terminal sudo authentication.
  Native client/service candidates now build without installing packages; reviewed native dependencies,
  unmanaged-helper migration and target-OS acceptance remain pending. Read-only system/video observations
  and the fresh private backup are recorded in [migration readiness](migration-readiness.md).

- Implemented: separate user-owned desktop snapshots, update/rollback and pre-session competing-GWE
  checks. The existing root service and explicit read-only backup are reused without profile migration or
  automatic startup. Full simulated validation passes with 478 tests on both interpreters; see
  [local installation](local-installation.md). The owner retains 320 W during current CUDA work.

- Completed: read-only baseline, source assessment, working branch and English documentation.
- Completed: interpreter checks for the two owner-provided environments (2026-09-30): Python 3.12.3 and 3.14.6.
- Completed: standalone read-only NVML probe, 26 simulated tests on each interpreter, live GPU reads without
  display variables, and dependency checks. See [diagnostic validation](nvml-diagnostics.md).
- Implemented: opt-in monitor-only repository/UI wiring, isolated settings and blocked GPU writes.
  All 42 simulated tests and live repository/interactor reads pass in both environments. The isolated Python
  3.12 GTK source monitor also passes its live X11 smoke check; Python 3.14 GUI/Wayland remain untested.
- Completed: consistent online backup of the installed GWE database, with integrity check and private Git-ignored storage.
- Completed: current-host Python 3.12 UI imports, local resource launcher and focused live graphical smoke test.
- Pending: broader UI interaction testing, target-OS/Wayland validation and production fan-control integration.
- Validated: standalone supervised NVML fan trial on the current host with administrator privileges.
  Both fans accepted a 40% target for ten seconds at 55–56 C and returned to automatic. Independent
  follow-up confirmed automatic policy and CoolerControl running again. Unprivileged resets were denied.
  The simulated suite remains at 62 passing tests per interpreter; see [procedure and results](nvml-fan-trial.md).
- Implemented: independent curve engine, NVML session with latched faults and bounded heartbeat supervisor.
  118 tests pass per interpreter, including real process faults with simulated devices. The new read-only
  preflight and normal ten-tick curve hardware trial passed, including 45% target readback and automatic
  restoration. Hardware worker-SIGTERM, SIGKILL and SIGSTOP-induced stall trials also passed with final
  automatic policies. The latter two validate parent recovery without worker cleanup while the supervisor
  and driver remain responsive. See the [hardware validation record](nvml-fan-curves.md).
- Pending: production continuous fan control, Wayland validation, remaining live fault recovery tests and distribution upgrade.
- Keep GTK and the existing profile model initially; prioritize the NVIDIA access layer and recovery.
- Completed: reusable NVML backend with UUID selection, per-reading availability/errors, memory, utilization
  and power, validated in both environments. See [backend contract](nvml-backend.md).
- NVML is the proposed application interface, not an integrated replacement yet. The standalone probe uses
  nvidia-ml-py 13.615.71; live read compatibility is verified on the current driver.
- Implemented: local client/protocol connected to a nonblocking NVML process adapter with independent
  recovery, ownership recording and lease expiry in both service and worker. 244 tests pass per interpreter,
  including real socket/process failures with simulated devices. See [service implementation](fan-service.md).
- Prepared: isolated root-owned installation bundle, desktop socket provisioning and a 60-second systemd
  trial unit with watchdog/post-stop recovery. The owner installed the reviewed bundle; hashes, root
  ownership and inactive/static service state were independently verified. The owner completed private
  user/GPU configuration on 2026-10-01. The normal installed-service/unprivileged-client hardware trial
  client-disconnection and lease-expiry scenarios passed with automatic recovery, clean shutdown and
  CoolerControl restarted. The complete-service SIGKILL hardware trial also passed: systemd post-stop
  recovery restored both fans to automatic, removed the ownership record and left the expected signal
  failure result. A complete-service SIGSTOP trial also passed with `Result=watchdog`, verified
  post-stop recovery and CoolerControl restarted. No boot enablement has occurred; suspend/resume,
  extended operation and driver/host failure hardware tests remain pending.
- Prepared: isolated GTK3 profile-review/service-client window and read-only SQLite loader. It preserves
  curves and settings without autoload, editing or migration. Preview passed on Python 3.12/X11; explicit
  ten-second GUI trial succeeded on the second attempt with automatic recovery. The first failure is
  unexplained; improved redacted diagnostics and a bounded private local log are implemented. Two later
  consecutive successful GUI trials were accepted provisionally by the owner. See
  [GUI service-client preparation](fan-gui.md).
- Implemented: opt-in service integration in the historical main window, with separate state, in-memory
  backup profiles, explicit Apply/Restore actions, no autoload and direct-write rejection. Read-only
  private-backup and simulated-service GTK checks passed, including explicit release, timed release and
  close during ownership. Main-window ten-second hardware trials now have logged verified release and independent follow-up
  automatic-policy reads. A connection loss near the service lifetime was reported without a false
  recovery claim; its exact instantaneous policy was not captured. Explicit early release subsequently passed with logged verified recovery and independent automatic/zero-speed
  readings. Closing during active ownership with the documented shell cleanup also passed: both fans
  automatic and zero RPM, service inactive, ownership marker absent and CoolerControl restarted.
  This combined procedure does not isolate disconnect recovery from service-stop recovery. See
  [main-window service validation](main-window-service.md).
- Implemented: explicit power-limit service transactions and isolated GUI Apply, with live bounds/UUID
  validation, compare-and-set, exact readback and interrupted-operation recovery. Simulated core, process,
  protocol, GUI and package-update tests pass. The updated bundle is installed; the guarded real
  250→240→250 W trial passed with independent readback, committed-limit retention after disconnect,
  automatic fan policies and clean shutdown. Real Power Apply interaction in the main window remains pending. Continuous service/autostart remain unimplemented. See [power control](power-control.md).
- Public hosting, application rename, distribution format and release version are undecided.
- Preserve upstream authorship and history. No publication or system modification is part of repository preparation.

## Python environment strategy

Use two separate environments during the migration, with different purposes:

| Environment | Purpose | Initial priority |
| --- | --- | --- |
| Python 3.12 | Current Ubuntu 24.04 baseline, backend development and eventual GTK integration | Required to start |
| Python 3.14 | Target interpreter compatibility, dependency resolution and backend tests | Add before migration validation |

Python 3.14 is the target interpreter listed in the [Kubuntu 26.04 release notes](https://kubuntu.org/news/kubuntu-26-04-release-notes/).
Use ordinary CPython builds initially; free-threaded builds are outside this migration scope.
These are planned validation targets, not a claim that the existing dependency pins work on either interpreter.

Start with a dedicated Python 3.12 environment based on the host interpreter. For GTK integration, assess
using system PyGObject/Pycairo through `--system-site-packages`; record the native package versions if used.
This option exposes system packages and is not a fully isolated dependency lock. Alternatively, building
PyGObject in the environment requires compatible native development libraries.
See [PyGObject installation guidance](https://pygobject.gnome.org/getting_started.html); its GTK4 example
must not be copied as GWE's GTK3 dependency list.

Keep Python 3.14 backend checks isolated from the host's Python 3.12 extension modules. A 3.14 environment
on Ubuntu 24.04 is useful for interpreter checks but does not reproduce Kubuntu 26.04's GTK/GLib stack.
Full UI and hardware acceptance still requires the target OS and session. No CUDA Toolkit is needed for
GWE backend development; live NVML queries require the NVIDIA driver library.

## Environment check: 2026-09-30

Both supplied interpreters start successfully. The owner installed nvidia-ml-py 13.615.71 and pytest 9.1.1
in both environments. Dependency checks, initially 16 simulated tests per interpreter and live read-only diagnostics
passed. See [commands, output semantics and results](nvml-diagnostics.md).

The remaining GTK application dependencies have not been installed or validated. GWE was not started.
The reusable telemetry backend now provides stable GPU identity and explicit per-reading availability/errors.
The suite has grown to 42 tests per interpreter. An explicit monitor-only integration now adapts
data to UI models and bypasses the X11 gate; live repository reads pass. The Python 3.12 GTK
source launcher and live smoke check now pass; see [GUI development](gui-development.md).

## Phase 1: reproducible development

Inspect available virtual environments and determine how system GTK introspection will be made available.
Check imports and package metadata before running the application. Review dependencies for the target Python
version, and choose a supported NVML binding using the [references](technical-references.md).
Record exact working dependencies and build commands once tested; do not upgrade every pin without evidence.
Review Flatpak packaging before deciding whether it remains suitable for a possible host-side control service.

Acceptance: a documented isolated build/import check, with no live GPU writes or automatic profile restoration.
Do not install project dependencies into system Python.

## Phase 2: NVML monitoring

Separate telemetry from control and remove the mandatory NV-CONTROL gate for the NVML path.
Enumerate the target GPU by stable identity, probe supported capabilities and allow missing optional metrics.
Keep sensor failures distinct from unsupported metrics and permissions failures.

Acceptance: useful telemetry with no X display; unsupported fields do not close the application; simulated
NVML initialization and device-loss failures are reported clearly. Confirm read-only behavior on the real GPU.

## Phase 3: fan curves and recovery

Preserve interpolation and hysteresis, address the ignored boolean write errors and define stale-temperature behavior.
Detect fan count and limits, distinguish automatic control from manual duty, and handle partial writes.
Design one owner for GPU control, minimal permissions and supervision before enabling continuous manual control.
Define recovery for UI exit, service failure, telemetry loss, suspension and driver loss; report restoration failure.
An in-process cleanup handler alone cannot recover from SIGKILL or a frozen process.

Acceptance: simulated failure coverage followed by separately authorized hardware tests for both fans and
restoration of automatic policy. Profiles must not be reapplied before capabilities and limits are validated.
No automatic claim of safety follows from a setter symbol being present.

## Phase 4: operating system and driver migration

Resolve the broken nvidia-fs DKMS registration and choose a coherent package source policy through separate
system maintenance work. Prepare a recoverable system image and an authorized profile backup.
Validate X11 and Wayland on the actual GPU, starting without saved profile reapplication.
Record reboot, suspend/resume, driver upgrade and matching Flatpak extension results where applicable.

Acceptance: a tested upgrade and rollback procedure, with an explicit known-good combination of versions.
Do not treat an older kernel entry as a complete distribution rollback.

## Phase 5: CUDA workload validation

Identify the owner's workload and its actual runtime/toolkit requirements. Check driver requirements,
PTX/JIT use and distribution support for that toolkit version. Select toolkit versions explicitly.

Acceptance: a representative workload succeeds after upgrade; rollback instructions cover its environment.
This can be planned alongside GPU work, but GWE compatibility does not establish CUDA workload compatibility.

## Validation record

Prepared on 2026-10-02: an explicit manual continuous session without GUI/service trial deadlines,
retaining lease expiry, watchdog and independent recovery. Source and simulated GTK checks pass;
the initial 60 C ceiling has since been replaced by an 85 C continuous ceiling (brief trials remain at
60 C). The follow-up adds graceful shutdown and root supervision of launcher exit/cleanup. A real
client session lasted about 104 seconds but reported a service shutdown error, followed by verified
automatic recovery. The revised private bundle is staged; hardware acceptance remains pending. See
[continuous session](continuous-session.md).
Prepared: changing power alongside a stable continuous fan curve, with explicit service capability
gating and unchanged renewal/release recovery. Combined simulated GTK and 465 automated tests per
interpreter pass. The owner's requested 320 W CUDA-load check remains pending; its baseline is recorded
in [power control](power-control.md).

Follow-up acceptance on 2026-10-02: the owner reported successful extended use. The real session logged
about 2 hours 33 minutes of active curve control and a verified power operation. Read-only follow-up
after reopening old GWE found 320 W retained, 63 C, 94% GPU use, clean experimental-service shutdown
and no pending records. The earlier pending CUDA-use entry is superseded by this observed result;
no peak temperature or workload completion is established. Next: local packaging and a desktop launcher
with exclusivity/rollback, followed by target-OS/Wayland and suspend/resume validation.

Guarded power acceptance on 2026-10-01 now includes the terminal 250→240→250 W trial and a real
main-window session with two verified transactions and an owner-confirmed visible result. Independent
follow-up found 250 W, automatic fan policies and clean service shutdown. Earlier GUI failures remain
unexplained. Real power-worker fault recovery and continuous operation remain pending; see
[power-control validation](power-control.md).
The single-command service-level power recovery check combines SIGKILL and SIGSTOP/watchdog,
with guarded 250 W restoration. Both hardware scenarios passed on 2026-10-02, with independent
readback and no pending records. Interrupted power-worker recovery after an actual simulated setter is also
tested with real spawned-process SIGKILL and SIGSTOP, without changing the installed service.

For each future run, record date, commit, GPU model, driver, kernel, OS, X11/Wayland session, packaging/runtime,
scenario, expected behavior, observed result and recovery outcome. Avoid personal paths, GPU UUIDs and profile
contents in shared reports. Mark unperformed scenarios as untested, not passed.

## GUI preparation follow-up

The owner installed the GUI prerequisites and enabled system package visibility in the Python 3.12 venv.
The source monitor now compiles local resources and passes its ten-second live check without replacing the
installed Flatpak. See [GUI development](gui-development.md). Python 3.14 remains isolated for backend tests.
