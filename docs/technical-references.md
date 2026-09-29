# Technical references

Initial review: 2026-09-29. These primary sources informed the setup assessment. Online documents can change;
recheck the version matching the driver/toolkit being tested before implementation or upgrades.

| Source | Why it matters | Limits of the evidence |
| --- | --- | --- |
| [Kubuntu 26.04 release notes](https://kubuntu.org/news/kubuntu-26-04-release-notes/) | Wayland default, optional unsupported X11 session, Python baseline | Does not establish GWE compatibility |
| [NVML device commands](https://docs.nvidia.com/deploy/nvml-api/latest/api/group__nvmlDeviceCommands.html) | Fan writes, automatic restoration, clock and power operations | Latest API documentation does not guarantee support or permissions on a particular GPU/driver |
| [NVML change log](https://docs.nvidia.com/deploy/nvml-api/change-log.html) | Introduction and evolution of capabilities | Match API availability to the installed driver and binding |
| [CUDA minor version compatibility](https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html) | Driver thresholds and PTX/new-feature limitations | Does not validate the owner's workload |
| [CUDA installation guide](https://docs.nvidia.com/cuda/cuda-installation-guide-linux/index.html) | Supported distributions and toolkit/driver packaging | Consulted version was 13.4; do not extrapolate to 12.9 or 13.2 |

## Python and UI environment reference

[PyGObject installation guidance](https://pygobject.gnome.org/getting_started.html) describes distribution
packages and virtual-environment builds with native prerequisites. Consulted on 2026-09-29. Its example
uses GTK4; GWE currently needs GTK3. Interpreter compatibility tests do not replace target-OS UI tests.

## Initial backend dependency candidates

Reviewed on 2026-09-30: [NVIDIA's nvidia-ml-py package](https://pypi.org/project/nvidia-ml-py/)
provides the `pynvml` import and wraps NVML errors as Python exceptions.
[pytest's getting started guide](https://docs.pytest.org/en/stable/getting-started.html) documents the proposed
test runner. nvidia-ml-py 13.615.71 and pytest 9.1.1 have now passed the standalone diagnostic checks
on both project interpreters; see the [validation record](nvml-diagnostics.md).
The binding version does not establish support for every API on the installed driver.

## API questions for implementation

- Use read-only enumeration and fan limit queries before enabling any setter.
- Check both `nvmlDeviceSetFanSpeed_v2` and `nvmlDeviceSetDefaultFanSpeed_v2` behavior and permissions.
- Specify handling for unsupported calls, permission errors, lost devices, missing sensors and partial writes.
- Verify the chosen Python binding exposes required APIs and matches their signatures and units.
- Keep clock offsets outside the first fan-control milestone; their units and support need separate validation.

## Repository evidence

| File | Relevant behavior |
| --- | --- |
| `gwe/interactor/has_nvidia_driver_interactor.py` | Mandatory NV-CONTROL startup gate |
| `gwe/repository/nvidia_repository.py` | Mixed X11/NVML telemetry, fan writes, power and clock operations |
| `gwe/presenter/main_presenter.py` | Curve execution, write-result handling, refresh errors and profile reapplication |
| `gwe/__main__.py` | Signal handling and automatic fan cleanup |
| `requirements.txt` | Existing Python dependency pins |
| `build.sh`, `meson.build`, `.gitmodules` | Build behavior and historical package integration |

The [assessment](setup-compatibility.md) distinguishes observed behavior from proposed changes;
the [maintenance plan](maintenance-plan.md) defines what remains to validate.
