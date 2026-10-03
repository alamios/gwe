# GreenWithEnvy (GWE)

GreenWithEnvy monitors NVIDIA GPUs and controls fan curves and power limits through NVML.
This is an independent fork of [Roberto Leinardi’s original GWE](https://gitlab.com/leinardi/gwe),
maintained by **alamios** from version **1.0.0**.

**This project is maintained with AI assistance**, including implementation, testing and documentation.
Recorded tests describe what has been verified; AI assistance does not establish hardware compatibility.
Original authors, contributor credits and the GPL-3.0-or-later license are retained.

The project home is [alamios/gwe](https://github.com/alamios/gwe). Source and native `.deb` packages are
intended for [GitHub Releases](https://github.com/alamios/gwe/releases). The first candidate is
**1.0.0-rc1**; Debian revision `1.0.0~rc1-3` is installed on the current host.
Publication and final installed recovery acceptance are pending. This fork currently has no Flatpak
or PyPI distribution.

## What changed

- NVML monitoring replaces the desktop’s dependency on X11 NV-CONTROL for GPU access.
- Fan curves and explicit power-limit changes use a separately privileged, supervised helper with
  authenticated ownership, renewable leases, watchdog and post-stop recovery.
- One native package contains the unprivileged GTK application and helper. Normal launch opens no
  terminal and requests no password; administrator authorization happens during installation/setup.
- Window controls and links retain the desktop GTK theme with scoped contrast fixes and circular
  title-button hover feedback. About separates the original authors from the fork maintainer.
- The original curve editor, profile persistence and minimize-to-tray preference remain available.
  The last applied curve can be restored at startup. Automatic profiles release fan control.
- Private configuration is created automatically; existing development profile sources are imported
  through a verified copy with recovery backups. Trial controls and the development status band are removed.

Clock-offset/overclock control is **not supported** by the NVML desktop. Power changes require explicit
Apply and readback verification; a committed limit remains in effect after normal exit. No boot-time
power-limit persistence is configured. Missing readings remain unavailable rather than becoming zero.

## Validation and limitations

Current hardware evidence covers an RTX 3090 Ti with two fans, NVIDIA driver 580.178.04 and Ubuntu/Kubuntu
24.04.5 on KDE/X11. Earlier supervised fan and power trials passed, including SIGKILL and watchdog recovery.
The new native desktop has passed isolated graphical checks with simulated control and real read-only
telemetry. The unified package’s actual socket lifecycle still needs installed acceptance.

**Kubuntu 26.04 and Wayland remain untested.** Python 3.14 backend tests do not reproduce their native GTK
stack. Driver/host failure guarantees and an independently recorded suspend/resume trace remain pending.
See [migration readiness](docs/migration-readiness.md) for evidence and remaining work.

Encoder/decoder telemetry has been checked against direct NVML and `nvidia-smi`. Firefox/YouTube returned
zero in all three; Firefox reported hardware decoding blocked by its decoding test. Playback alone does
not require encoder activity. This observation is separate from GWE’s successful controlled video-engine
checks.

## Build, install and configuration

The maintained build is [the native package builder](docs/packaging-plan.md). It uses reviewed Python
modules with their licenses and distribution-provided GTK/Matplotlib libraries, not a frozen executable.
It does not bundle or replace drivers, kernels or CUDA. Follow the documented package inspection and
installation procedure; do not run the historical upstream build/reset/install instructions.

Close other GWE applications with **Quit**, then install the reviewed local candidate normally:

```bash
sudo apt install ./build/release-rc1-4/gwe-nvml_1.0.0~rc1-4_all.deb
```

The package handles helper setup and socket activation; no separate installation script or venv is
required. The optional `scripts/install_release_candidate.sh` combines installation with development
checks and a real startup/recovery trial. Those tests are not required for ordinary installation.
The current-host package is installed and the owner reports successful ordinary use and corrected UI.
Recorded native startup/quit and fault-recovery acceptance remain pending.

After installation, launch **GreenWithEnvy** from the application menu or run `gwe-nvml`.
Configuration and curves belong to the desktop user; the root helper stores only its authorization.
See [native configuration, import and rollback](docs/native-desktop.md). Close any other GPU fan
controller before beginning a control session. Closing can minimize to the tray; use **Quit** to release.

## Development and recovery documentation

Development continues on `main`. The annotated `upstream-baseline` tag preserves the inherited
original code; version tags identify fork releases. The maintenance branch has been merged with its
full history. See [publishing source and packages](docs/github-releases.md).
Documentation and code comments are in English. Tests do not authorize writes to a live GPU.

- [Contributing](CONTRIBUTING.md), [agent instructions](AGENTS.md) and [release checklist](RELEASING.md)
- [Setup assessment](docs/setup-compatibility.md), [maintenance plan](docs/maintenance-plan.md) and
  [technical references](docs/technical-references.md)
- [Native packaging](docs/packaging-plan.md), [native desktop](docs/native-desktop.md) and
  [configuration backup](docs/configuration-backup.md)
- [NVML diagnostics](docs/nvml-diagnostics.md), [backend contract](docs/nvml-backend.md),
  [monitor mode](docs/monitor-mode.md) and [GUI environment](docs/gui-development.md)
- [Fan service](docs/fan-service.md), [power control](docs/power-control.md) and
  [migration readiness](docs/migration-readiness.md)

Earlier supervised experiments remain documented in [fan trials](docs/nvml-fan-trial.md),
[curve recovery](docs/nvml-fan-curves.md), [profile review](docs/fan-gui.md),
[main-window trials](docs/main-window-service.md), [continuous sessions](docs/continuous-session.md) and
[local snapshots](docs/local-installation.md). These developer procedures are not the ordinary release
launch path. Historical Flatpak references describe the original installation and its backup/rollback.

Report this fork’s issues at [alamios/gwe issues](https://github.com/alamios/gwe/issues).
See [CHANGELOG.md](CHANGELOG.md) for fork notes and preserved upstream history.

## Credits and license

Original GWE was created by Roberto Leinardi, with contributions including Gabriele Musco and the upstream
community. Thanks also to the NVML bindings, python-xlib and the original icon contributors; existing
source and bundled dependency license notices are retained.

Upstream acknowledgements include TingPing, 999eagle, tim74, Lighty, fbcotter, the python-xlib developers
and tiheum’s Faenza icons, alongside everyone who tested and reported bugs. Historical packaging credits
do not imply those contributors maintain this fork.

Licensed under [GPL-3.0-or-later](COPYING.txt). This software is provided without warranty; see the license.
