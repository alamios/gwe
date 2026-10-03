# Migration readiness: current-host follow-up

Observed on 2026-10-03. Readiness for the current host is distinct from acceptance on Kubuntu 26.04/Wayland.
No driver, kernel, CUDA, DKMS registration or repository configuration was changed during this follow-up.

Follow-up: the owner still observes zero decoder utilization during ordinary video playback. Controlled
NVDEC telemetry success does not resolve that workload-specific report. Native candidate installation is
prepared through `scripts/install_native.sh`, including dependency guards and manual-helper recovery;
v4 package installation completed but its GTK check found missing bundled `playhouse` modules. The v5
correction passes the extracted-package GTK startup/Restore check with system Python and simulated
control; upgrading the installed pair and real native-session acceptance remain pending.

## Current system and remaining maintenance

Read-only checks reported kernel 7.0.0-38-generic and driver 580.178.04. NVIDIA DKMS reports this driver
installed for the running kernel. The previous kernel 7.0.0-34 baseline is historical. Both fan policies
were automatic, the experimental service inactive with success and CoolerControl active. The observed
power limit was 330 W; it was preserved rather than resetting the earlier 320 W or 250 W baseline.

`nvidia-fs/2.26.6` remains a broken DKMS registration: its source link points to an absent source directory.
This is the GPUDirect Storage filesystem module, not the display driver. Its relevance depends on actual
GDS/cuFile use; normal CUDA use alone does not establish that requirement. Before kernel/driver changes,
review whether to repair its matching sources or remove the orphaned registration after preserving state.
Neither action has been performed or silently authorized by GUI/package work.

APT still prefers the Ubuntu 24.04 CUDA repository at priority 600 over Ubuntu's priority 500 for the
queried NVIDIA driver/utilities. Driver, compute library and versioned `nvidia-utils-580` are 580.178.04;
unversioned `nvidia-modprobe`, `nvidia-persistenced` and `nvidia-settings` are 615.71.09. This documents a
mixed package set, not proof that every utility is incompatible. Review the complete intended package
transaction and target-distribution repositories before an upgrade; do not carry a 24.04 repository
configuration into 26.04 without checking its supported target. Supporting future drivers is the goal;
a system rollback path is recovery planning, not an indefinite old-driver support commitment.

Primary references:
[NVIDIA nvidia-fs scope](https://docs.nvidia.com/gpudirect-storage/nvidia_fs/index.html),
[CUDA installation guidance](https://docs.nvidia.com/cuda/cuda-installation-guide-linux/index.html).

## Profiles and local application

The existing explicit backup passed read-only integrity and requested startup-curve/manual-limit checks.
A new private SQLite online backup of the old Flatpak database also passed integrity validation. Its
manifest/checksum and database remain Git-ignored; the previous backup was preserved. Copy the fresh
backup to independent storage before changing the distribution. This backup is not a system image.

The owner closed GWE, then the local snapshot was updated with the requested named startup curve.
Actual installed rollback and return to the new selection completed without launching a controller.
The original Flatpak/database remain intact. Named startup waits for telemetry, uses supervised service
acquisition and never rearms after Restore or a fault. Normal verified power changes remain committed.

The owner reported working menu use and suspend/resume on 2026-10-03. That report does not provide an
independently captured sleep/recovery trace. A grouped installed-startup/window-close acceptance is prepared:

```bash
/path/to/prepared/python3.12 scripts/check_installed_session.py
```

It reads the private installed configuration, requires automatic fan policies and a temperature below
80 C, then runs the actual installed continuous wrapper. It waits for verified startup control, holds it
for six seconds and closes the actual window. Wrapper cleanup and independent readback must leave both
fans automatic, the current power unchanged, service inactive/success and CoolerControl at its original
state. The command needs sudo authentication in the user's terminal; it changes no power/clock setting
and generates no workload. The agent's noninteractive sudo check lacked authentication, so hardware
startup/close acceptance is still pending rather than reported as passed.

## Encoder/decoder investigation

The owner observed zeros during reported accelerated playback, including in old GWE. The NVML calls
and frontend/backend mapping already distinguish encoder and decoder and retain unavailable status.
A bounded six-second-per-engine synthetic 640x360/24fps H.264 FFmpeg check completed explicit NVENC and
CUVID decoding; raw NVML and the backend both reported zero, with a 100000 microsecond sampling period.
This does not establish physical engine inactivity or a frontend defect. A light workload may round to
zero; that explanation is not proven.

The follow-up 1080p60 check failed opening NVENC with an out-of-memory error. Independent follow-up found
99% GPU use, about 415 MiB free VRAM and 77 C during ongoing work. No existing process was interrupted.
Higher-resolution media validation must wait for memory/headroom; the diagnostic has an 80 C thermal
stop, bounded process lifetime and termination on errors. New runs retain private timestamped logs in
`build/video-diagnostic/`. Optional rerun when the GPU is available:

```bash
/path/to/prepared/python3.12 scripts/check_video_engines.py --exercise
```

No fan/power/clock setter is called. It creates a synthetic clip, performs six seconds per engine and
compares raw NVML with backend counters. Ordinary playback does not require encoder activity.
The inherited zero-reading cause remains unresolved; do not invent nonzero values or claim it fixed.

### Available-GPU follow-up and telemetry correction

Later on 2026-10-03, the owner reported the GPU available. Preflight found 44 C and about 21808 MiB
free VRAM, retaining 330 W. Both 1080p60 phases completed successfully, but repeated NVML init/shutdown
between samples still produced zeros. Holding one NVML monitoring reference across the same phases
produced encoder/decoder peaks of 18%/22%, independently confirmed by `nvidia-smi dmon`.

The GUI repository now uses an opt-in persistent read-only backend session. Handles are still reacquired
by pinned UUID for every snapshot. Errors/device loss release the reference for fresh initialization on a
later read; no missing telemetry is replaced with stale values. Cleanup closes only the reader's reference,
with no fan, clock or power setter. One-shot probes retain per-call balanced initialization/shutdown.

A further real-media check observed matching raw/backend encoder/decoder peaks of 37%/8%, also seen
through the actual UI repository/model. The isolated GTK simulated-startup/Restore check passed. These
observations establish the correction for this branch's monitoring lifetime; they do not establish why
every previously reported playback/old-app reading was zero. Idle or non-NVDEC playback can still show
zero legitimately. The earlier unresolved branch observation is superseded by these current-host results.

Full simulated validation passed with 514 tests on each interpreter, including preserved sampling
history, initialization failures, lost-device reinitialization, balanced probes and retryable close failures.
The local snapshot is updated only after confirming no competing control window; no root service or
power/fan setting is changed by that update. Earlier native candidates are retained; the rebuilt client
includes this correction.

## Remaining target acceptance

Use the native-package build/review procedure in [packaging](packaging-plan.md). Artifacts are local
candidates, not automatically installed or published. Current-host native dependency installation and
explicit migration of the unmanaged helper still need review before package installation.
Target Kubuntu 26.04 must validate its actual GTK/native libraries and dependencies, Wayland startup,
NVML reads, UUID selection, both fans, power readback, close/disconnect/recovery, and the owner's real
CUDA workloads. Driver/host failure recovery and an independently captured suspend/resume trace remain
pending. Do not repeat earlier accepted brief tests as a substitute for these missing environments.

The full simulated suite passed on both Python 3.12 and 3.14 with 508 tests each. The staged native client
passed its GTK startup/Restore check using bundled Python modules and precompiled resources; control was
simulated and NVML telemetry read-only. Package tests include deterministic archives, explicit permissions,
active/pending/unknown-state refusal and absence of private DB/config payload. Existing Reactivex datetime
deprecation warnings remain non-fatal. Privileged acceptance and native installation remain separate.
