# Personal setup assessment: Kubuntu 26.04, NVIDIA and CUDA

Assessment date: 2026-09-29. Scope: maintain GWE for this machine while preserving custom fan curves.
Evidence consists of source inspection and authorized read-only system queries. Personal profiles were not
read, packages were not installed, and GPU settings were not changed. Kubuntu 26.04 has not been tested.

## Observed baseline

| Component | Observation |
| --- | --- |
| System | Ubuntu 24.04.5 LTS base, KDE, X11 session |
| Kernel | 7.0.0-34-generic |
| GPU | NVIDIA GeForce RTX 3090 Ti |
| Active driver | 580.178.04; nvidia-smi and NVML respond |
| GWE | User Flatpak, Flathub, 0.15.9, marked unmaintained |
| Runtime | org.gnome.Platform 46 |
| NVIDIA Flatpak extension | nvidia-580-178-04 installed and matching |
| CUDA Toolkits | 12.9.2 and 13.2.2 installed |
| Compilers | Both nvcc binaries work by absolute path; neither is on this session's PATH |
| Secure Boot | Disabled |
| Fans | NVML enumerates two and reports a manual range of 30–100% |
| Queried control state | NV-CONTROL reports manual control and a 30% target for both fans |

NVML reads both fan speeds. The driver exports `nvmlDeviceSetFanSpeed_v2`,
`nvmlDeviceSetDefaultFanSpeed_v2` and `nvmlDeviceSetClockOffsets`; these setters were NOT called.
Symbol availability does not establish write permissions or successful recovery. The process currently
responsible for manual fan control was not identified.

## Kubuntu 26.04 and GWE architecture

Kubuntu 26.04 defaults to Wayland. Its optional `plasma-session-x11` package is unsupported by the Kubuntu
team. The base system includes Python 3.14. See the [official release notes](https://kubuntu.org/news/kubuntu-26-04-release-notes/).

`gwe/interactor/has_nvidia_driver_interactor.py` requires NV-CONTROL before checking NVML, and the presenter
quits if that extension is missing. `NvidiaRepository.get_status()` mixes X11 and NVML; fan control and
overclocking use NV-CONTROL. There is no NVML-only monitoring path. Xwayland must not be assumed to solve this.

An X11 session could provide a temporary migration path, subject to driver testing. The proposed Wayland
implementation replaces GPU access with NVML while retaining the GTK interface and fan profile model.
Flatpak isolates UI dependencies but does not remove NV-CONTROL or host-driver dependencies.

Native execution requires reviewing old pins in `requirements.txt`, including PyGObject, matplotlib,
peewee and py3nvml, and checking GTK3/Dazzle/Ayatana. Python 3.14 compatibility has not been tested.
The local Flatpak submodule is uninitialized. Historical system-wide pip commands are not a migration
procedure; development needs a reproducible environment and packaging workflow.

## System findings before upgrades

- `dkms status` reports `nvidia-fs/2.26.6: broken`, with missing sources or a missing link. `dpkg --audit`
  reported no errors, but does not validate DKMS. Establish whether the module is needed, then repair
  the installation or remove its orphaned registration before changing kernels/drivers. No rebuild was
  attempted, and an upgrade failure has not been demonstrated.
- APT selects driver and libraries from NVIDIA's Ubuntu 24.04 CUDA repository at priority 600, ahead of
  Ubuntu at priority 500. Both Ubuntu prebuilt modules and NVIDIA DKMS are present. Choose and document
  a coherent package source policy and review repositories when migrating to 26.04.
- `nvidia-settings`, `nvidia-modprobe` and `nvidia-persistenced` are version 615.71.09, while the active driver
  is 580.178.04. This does not prove incompatibility: queries work. It does require reviewing package ownership.
- The installed Flatpak is marked unmaintained. Both packaging and runtime maintenance need a plan.

## Fan curve reliability

Source findings:

- `NvidiaRepository.set_fan_speed()` returns an error flag. The presenter ignores that value and handles
  exceptions only, potentially failing to report some write failures.
- Normal exit attempts to restore automatic control, as does `_on_status_updated(None)`. Missing temperature
  inside an otherwise valid status can instead stop curve updates without restoring automatic control.
- A terminal error in the refresh stream is logged without explicit control recovery.
- Cleanup installs SIGINT handling but no equivalent SIGTERM handler. Crashes and hangs are not covered by
  normal exit cleanup either.
- Startup can reapply the previous profile. Capabilities and limits must be revalidated after driver changes.

Proposed changes: NVML monitoring independent of X11, stable GPU identity by UUID, runtime capability detection,
validation of limits and write results, and restoration of automatic control on recoverable failures.
Preserve interpolation, hysteresis and profiles; distinguish automatic/zero-RPM behavior from the 30% manual minimum.
Evaluate a small supervised service with narrowly scoped privileges, separate from the UI, to execute curves.
Complete driver failure can prevent even automatic restoration; an absolute recovery guarantee is not possible.
Never run two fan controllers concurrently during hardware validation.

NVML documents manual fan control and automatic restoration. Actual support and behavior need hardware tests.
See [NVML Device Commands](https://docs.nvidia.com/deploy/nvml-api/latest/api/group__nvmlDeviceCommands.html).

## CUDA and drivers

GWE does not use the CUDA Toolkit or execute CUDA kernels. It uses driver NVML and NV-CONTROL.
Validate the operating system/kernel, driver, GWE and CUDA workloads separately.

Driver 580 meets the CUDA 13.x minor compatibility threshold. This does not validate every CUDA 13.2 workload:
PTX/JIT and newer features can require a newer driver. The user's actual CUDA workload remains unidentified
and untested. See [CUDA compatibility](https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html).

The consulted CUDA 13.4 installation guide includes Ubuntu 26.04 and separates toolkit and driver installation.
Do not apply that support matrix to installed toolkits 12.9/13.2. Metapackage dependencies vary by version;
review the actual APT transaction before upgrading. See the [CUDA installation guide](https://docs.nvidia.com/cuda/cuda-installation-guide-linux/index.html).

## Proposed upgrade sequence

1. Resolve DKMS and package source policy, and record a known baseline.
2. Prepare a recoverable system backup and, with authorization to access those data, a GWE profile backup.
   Booting an older kernel alone does not revert libraries or an entire distribution upgrade.
3. Implement NVML monitoring, then fan curves and recovery for this GPU. Use simulated failures to check
   missing sensors, bounds, partial fan failures and permission errors.
4. Validate hardware under X11 and Wayland: reads, authorized writes, automatic restoration, normal exit,
   SIGTERM, process failure, suspend/resume and reboot. Begin without heavy load and with supervision.
5. Test 26.04 on a recoverable installation on the actual hardware, initially without profile reapplication.
6. Change one layer at a time where possible. After a driver upgrade, reboot and check NVML, kernel modules,
   fans and Flatpak extensions before enabling curves.
7. Validate a representative CUDA workload with its chosen toolkit/runtime and document package and
   configuration rollback. A working nvidia-smi alone is insufficient.

No write, load, failure recovery or migration tests have been performed. Read-only NVML results support the
feasibility of a personal adaptation; the current GWE is not validated for Wayland or arbitrary upgrades.
