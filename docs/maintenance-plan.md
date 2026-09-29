# Maintenance plan

Working branch: `maintenance/nvml-revival`.
Initial target: NVIDIA GeForce RTX 3090 Ti, preserving custom fan curves during migration from Kubuntu 24.04/X11
and preparation for Kubuntu 26.04/Wayland. See the [observed baseline](setup-compatibility.md).

## Status and decisions

- Completed: read-only baseline, source assessment, working branch and English documentation.
- Completed: interpreter checks for the two owner-provided environments (2026-09-30): Python 3.12.3 and 3.14.6.
- Completed: standalone read-only NVML probe, 26 simulated tests on each interpreter, live GPU reads without
  display variables, and dependency checks. See [diagnostic validation](nvml-diagnostics.md).
- Implemented: opt-in monitor-only repository/UI wiring, isolated settings and blocked GPU writes.
  All 41 tests and live repository/interactor reads pass in both environments; the GTK launch is unvalidated.
- Completed: consistent online backup of the installed GWE database, with integrity check and private Git-ignored storage.
- Pending: full application dependency validation, reproducible UI build and graphical integration tests.
- Pending: GPU write tests, Wayland validation, fault recovery tests and distribution upgrade.
- Keep GTK and the existing profile model initially; prioritize the NVIDIA access layer and recovery.
- Completed: reusable NVML backend with UUID selection, per-reading availability/errors, memory, utilization
  and power, validated in both environments. See [backend contract](nvml-backend.md).
- NVML is the proposed application interface, not an integrated replacement yet. The standalone probe uses
  nvidia-ml-py 13.615.71; live read compatibility is verified on the current driver.
- A separate privileged service is under evaluation; its protocol, permissions and supervision need design.
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
The suite has grown to 41 tests per interpreter. An explicit monitor-only integration now adapts
data to UI models and bypasses the X11 gate; live repository reads pass. Next: prepare the full GTK
environment (system Dazzle/Ayatana typelibs are missing) and validate graphical behavior.

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

For each future run, record date, commit, GPU model, driver, kernel, OS, X11/Wayland session, packaging/runtime,
scenario, expected behavior, observed result and recovery outcome. Avoid personal paths, GPU UUIDs and profile
contents in shared reports. Mark unperformed scenarios as untested, not passed.

## GUI preparation follow-up

GTK3, Notify and the system GI/Cairo bindings are present. The Python 3.12 venv needs system package
visibility; Dazzle, Ayatana and the GLib resource compiler require owner installation. The initial Python UI
dependency set is in `requirements-ui312.txt`. See [GUI preparation](gui-development.md). No package was
installed by the agent, no GUI was launched, and Python 3.14 remains isolated for backend tests.
