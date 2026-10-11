# GreenWithEnvy

GreenWithEnvy (GWE) monitors NVIDIA GPUs and controls fan curves and power limits through NVML.
This independent fork is maintained by **alamios**, starting with version **1.0.0**, and is based on
[Roberto Leinardi's original GWE](https://gitlab.com/leinardi/gwe).
Original authors, copyright notices and the GPL-3.0-or-later license are retained.

**The project is maintained with AI assistance**, including implementation, tests and documentation.
Compatibility claims are limited to recorded validation.

- [Source and issues](https://github.com/alamios/gwe)
- [Releases](https://github.com/alamios/gwe/releases)
- [Changelog](https://github.com/alamios/gwe/blob/main/CHANGELOG.md)

## Features

- NVML telemetry: temperature, utilization, memory, power, clocks, video engines and device information.
- Editable fan curves with hysteresis, automatic profiles and saved-curve startup restoration.
- Supervised fan control independent of GTK scheduling, with leases, watchdog and automatic recovery.
- Verified power-limit changes, saved per GPU and restored once when GWE starts.
- Guarded curve reapplication after suspend, once service recovery is verified.
- Minimize-to-tray support, desktop notifications and persistent control-failure notices.

The GTK desktop works without X11 GPU-control extensions. Missing readings remain unavailable;
a measured zero is displayed as zero. Clock-offset and overclock control are not supported.

## Install and run

The native **gwe-nvml** `.deb` includes the desktop and privileged helper. It uses system Python and
GTK; no development environment or separate installation script is required. It does not replace
drivers, kernels or CUDA.

Choose a release package and verify its checksum. Before an update, quit GWE using **Quit**, pause GPU
work and allow recovery to finish. For the current prepared candidate:

```bash
sudo apt install ./gwe-nvml_1.0.0~rc1-9_all.deb
```

Launch **GreenWithEnvy** from the application menu or run `gwe-nvml`. Normal launch opens no terminal
and requests no password; administrator authorization is configured during installation.

See the [user guide](docs/user-guide.md) for curves, power, startup, updates and recovery.
Back up your profiles using the [configuration guide](docs/configuration-backup.md).

## Compatibility and status

The development candidate is **1.0.0-rc1**. The latest prepared package is **1.0.0~rc1-9**.
Testing covers an RTX 3090 Ti with two fans, NVIDIA 580.178.04 and KDE on Kubuntu 26.04/Wayland.
The complete automated suite passes 632 tests on system Python 3.14.4. Installed lifecycle and
supervisor recovery have hardware evidence; the owner reports working power restoration.
Installed automatic curve resume and the latest icon correction still need acceptance.

See [validation](docs/validation.md) for exact scope and outstanding checks. These results do not
establish compatibility with every NVIDIA GPU, driver or desktop.

## Documentation

- [User guide](docs/user-guide.md)
- [Configuration backup and restore](docs/configuration-backup.md)
- [Architecture and control contracts](docs/architecture.md)
- [Development and testing](docs/development.md)
- [Building native packages](docs/packaging.md)
- [Validation and remaining checks](docs/validation.md)
- [Technical references](docs/technical-references.md)
- [Contributing](CONTRIBUTING.md), [release procedure](RELEASING.md) and [agent instructions](AGENTS.md)

## Credits and license

Created by Roberto Leinardi, with contributions from Gabriele Musco and the original community.
The fork maintainer is alamios. Existing artwork and dependency acknowledgements are retained.
Licensed under [GPL-3.0-or-later](COPYING.txt).
