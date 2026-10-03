# GreenWithEnvy (GWE)

![maintenance resumed](https://img.shields.io/badge/status-maintenance%20resumed-blue)

> **Maintenance resumed — personal setup first**
>
> We are resuming maintenance of GWE, initially for an NVIDIA GeForce RTX 3090 Ti on Kubuntu.
> Our first priorities are preserving custom fan curves, moving GPU control toward NVML for Wayland,
> and validating driver and CUDA upgrades with a documented recovery procedure.
>
> Development continues on **`maintenance/nvml-revival`**. This is an independent fork of
> [Roberto Leinardi's original GreenWithEnvy](https://gitlab.com/leinardi/gwe), maintained by **alamios**
> for the upcoming 1.0.0 release. The main change is moving GPU monitoring and fan/power control to NVML.
> **This fork is maintained with AI assistance**, including implementation, testing and documentation.
> The planned home is [alamios/gwe on GitHub](https://github.com/alamios/gwe), with source code and native
> `.deb` downloads through [GitHub Releases](https://github.com/alamios/gwe/releases). No release has
> been published by this maintenance session; Wayland compatibility is not yet validated. Flatpak is
> not a distribution channel for this fork at present.

## Maintenance documentation

- [Setup assessment and observed baseline](docs/setup-compatibility.md)
- [Maintenance plan and validation criteria](docs/maintenance-plan.md)
- [Technical references](docs/technical-references.md)
- [Read-only NVML diagnostics and tests](docs/nvml-diagnostics.md)
- [NVML backend contract and validation](docs/nvml-backend.md)
- [Supervised NVML fan experiment and recovery](docs/nvml-fan-trial.md)
- [Experimental NVML curves and process recovery](docs/nvml-fan-curves.md)
- [Local fan-service protocol and implementation status](docs/fan-service.md)
- [Isolated fan-profile review and GUI service client](docs/fan-gui.md)
- [Main-window NVML service integration](docs/main-window-service.md)
- [Explicit power-limit control and guarded acceptance](docs/power-control.md)
- [Experimental manual continuous session](docs/continuous-session.md)
- [Separate local desktop installation and rollback](docs/local-installation.md)
- [Native/Flatpak packaging architecture and remaining work](docs/packaging-plan.md)
- [Current migration readiness and grouped installed-session check](docs/migration-readiness.md)
- [Development monitor-only integration](docs/monitor-mode.md)
- [Preparing the development GUI](docs/gui-development.md)
- [Configuration backup and restore](docs/configuration-backup.md)
- [Contributing and development workflow](CONTRIBUTING.md)
- [Repository instructions for coding agents](AGENTS.md)
- [Local builds and future releases](RELEASING.md)

The next local X11 release will use one package, writable profile configuration and the regular desktop
controls without the trial terminal or status band. These changes are specified, not yet implemented;
see the [agreed release requirements](RELEASING.md#first-local-x11-release-agreed-requirements).

The reviewed local `.deb` candidates have a guarded first-install procedure:
`bash scripts/install_native.sh`. See [installation and recovery](docs/packaging-plan.md#installing-the-reviewed-candidates).
The first native installation exposed missing bundled Peewee `playhouse` modules. Corrected v5 packages
pass the extracted-client GTK check with system Python; updating the installed v4 packages is pending.
Kubuntu 26.04/Wayland validation remains pending. Decoder utilization
during ordinary playback is still reported as zero despite successful controlled NVDEC telemetry checks.
During the owner's Firefox/YouTube reproduction, direct NVML, the installed v5 backend and nvidia-smi
also reported zero video-engine utilization. Firefox decoding diagnostics remain pending; the observed
zero is not introduced by the GWE display mapping.

All maintained documentation is written in English. The default control mode still requires X11 NV-CONTROL.
Both fans have passed a supervised NVML manual-control trial and normal automatic restoration on the
current X11 host with administrator privileges. Recovery after worker SIGTERM, SIGKILL and SIGSTOP-induced
stalls is also verified with the supervisor alive. Kubuntu 26.04 and driver/host failure recovery remain unvalidated.
The read-only NVML backend and diagnostics pass on Python 3.12 and 3.14, including GPU selection by UUID
and real reads without display variables. An opt-in monitor-only UI integration is implemented;
514 automated tests pass on both Python versions, including the socket-to-process service, client loss
and recovery. The isolated Python
3.12 GTK monitor has passed a live startup, telemetry, disabled-controls and shutdown check on the current
X11 desktop. Wayland remains untested. The separate fan trial held a 40% target for ten seconds on both
fans at 55–56 C and verified automatic restoration; CoolerControl is running again. Unprivileged reset
calls were denied. An independent curve engine and bounded process supervisor are implemented and tested
with simulated devices. The normal synthetic-curve hardware trial also passed: ten ticks at a 45% target,
54–55 C and verified automatic restoration. Subsequent worker SIGTERM, SIGKILL and stalled-worker trials
also returned both fans to automatic. A production privileged service, suspend/resume and recovery from
driver/host failures remain pending. The local protocol and renewable lease now connect to a supervised
NVML process adapter. Service/worker failures and recovery are tested with simulated devices. A standalone
root-owned package and 60-second systemd trial unit have been installed and configured for the local
user/GPU. Normal release, client disconnection and lease-expiry hardware trials passed with an
unprivileged client, verified automatic recovery and clean service shutdown. A complete-service SIGKILL
hardware trial also passed with systemd post-stop recovery and both fans automatic. Freezing the complete
service with SIGSTOP also passed: watchdog termination and post-stop recovery restored both fans to
automatic. Suspend/resume, extended operation and driver/host failure recovery remain unvalidated. No production service or profile
migration is enabled.
An isolated GTK profile-review window reads an explicit backup without modifying it and prepares opt-in
ten-second service trials. A saved-curve GUI hardware trial succeeded on Python 3.12/X11 with verified
automatic recovery on the second attempt and two subsequent consecutive successes. The owner accepts
this bounded GUI trial provisionally; the first failure remains unexplained. A private, bounded local log
retains future state changes and redacted diagnostics.
An opt-in integration now uses the existing main window with isolated settings and explicit ten-second
service trials. Read-only and simulated-service GTK checks pass. Main-window ten-second hardware trials
have logged verified recovery and independent follow-up automatic-policy reads; a connection loss near
the service lifetime remains documented. A reported post-trial interval near 30% was followed by a
read-only minute at automatic policy and zero RPM; the transient cause remains undetermined.
Explicit early release and closing during active control with the documented shell cleanup also passed,
with independent automatic-policy verification. Continuous operation remains pending. Telemetry includes power draw and limits, current/maximum clocks, and per-fan percentages and RPM.
VBIOS, PCIe links, CUDA core count, memory bus width, encoder/decoder utilization and thermal thresholds
are also connected. All these reads passed on the current host; unavailable readings remain blank, never
substituted with zero.
Explicit power-limit control is implemented behind a separate launch flag, with UUID/range validation,
readback verification, an interrupted-transaction journal and rollback to the previous value. Simulated
backend/GUI checks pass; the first bundle update stopped at its installation-path validation before any
power trial. The corrected `build/power-service-v2` bundle was subsequently installed, preserving its
configuration and rollback copy. A missing-runtime preparation failure was corrected in the trial wrapper;
the protected 250→240→250 W hardware trial passed using its `--installed` mode, including independent
readback, retention after client disconnect and verified cleanup back at 250 W. After notice visibility and
allowlisted diagnostics were improved, the owner confirmed a visible verified result in the guarded main
window. Its final session logged two verified transactions and independent follow-up confirmed 250 W,
automatic fan policies and clean shutdown. Earlier GUI failures remain unexplained. Power-worker fault
recovery on real hardware, continuous service and target-OS/Wayland validation remain pending.
An optional single-command service recovery check now combines SIGKILL and watchdog scenarios with
automatic guarded restoration and independent readback. Both hardware scenarios passed on 2026-10-02,
restoring 250 W and automatic fan policies with no pending records. The final watchdog failure state is
expected; CoolerControl is active again.
An experimental manual continuous session supports explicit Apply/Restore, renewable ownership and
watchdog/post-stop recovery. A real client session remained active for about 104 seconds; its service
recorded an error at shutdown, followed by verified automatic policies and no pending GPU records.
The follow-up with an 85 C continuous ceiling, graceful process-group shutdown and root supervision
of launcher exit/cleanup has now been used successfully. A real session logged about 2 hours 33 minutes
of active curve control and a verified power operation; follow-up found clean service shutdown and no
pending records. See the single-command session launcher.
Continuous sessions now advertise support for changing power alongside a stable active curve; transitions
and faults remain blocked. A combined simulated GTK 320 W Apply/renewal/release check passes. The owner
reports successful real use; after returning to the old application, read-only inspection found 320 W,
63 C and 94% GPU use. This is a later observation, not the trial's measured peak temperature.
The session launcher now resets only an actually failed unit; unnecessary `reset-failed` calls could
abort preparation after recovery unloaded an inactive unit. Focused launcher regression checks pass.
Verified power changes persist on normal window/service close; no reboot persistence is configured.
An optional separate local desktop installation snapshots the reviewed GUI, preserves prior code for
rollback and checks for another GWE before service operations. It reuses the installed root service and
explicit read-only backup; it does not replace Flatpak or migrate profiles. See the local installation guide.
See the main-window and power-control guides.
An opt-in named startup curve now waits for telemetry and attempts service acquisition once per launch;
release and faults never rearm it. Simulated validation is separate from real startup acceptance.
The installed local snapshot is not automatically replaced while the owner is using it.
After the owner closed it, the snapshot was updated with the requested startup preference and actual
installed rollback/return completed. A grouped real startup/close check is prepared but needs sudo
authentication. Local native client/service `.deb` candidates now build with precompiled resources,
declared native dependencies, bundled reviewed Python modules and guarded package operations; they are
not installed. Read-only follow-up found kernel 7.0.0-38, retained 330 W and the previously reported DKMS/
repository/utility issues. Encoder/decoder zeros were also observed directly through NVML during a small
synthetic video check; higher-resolution validation stopped on VRAM allocation failure during CUDA use.
After VRAM became available, 1080p60 completed but per-snapshot NVML initialization still returned zeros.
Keeping the monitoring session alive restored encoder/decoder readings, confirmed against nvidia-smi
and the actual UI telemetry model. The monitor/service GUI now retains its read-only NVML reference
until cleanup, resetting it after read errors; one-shot probes remain balanced. See migration readiness.
Run `python -m gwe.nvml_probe` for terminal diagnostics, or `python scripts/run_monitor.py` in the prepared
Python 3.12 UI environment for the isolated graphical monitor. See the guides above.

The original authorship and GPL-3.0-or-later license are retained. Existing application identifiers remain
for now to avoid an unplanned settings migration. Any future publication must use an independent hosting
namespace and application ID, with an explicit profile migration plan.

---

## About (historical)

GWE is/was a GTK system utility designed to provide information, control the fans and overclock your NVIDIA video card
and graphics processor.

> **Note:** The information below is preserved for reference. It may be outdated and is **not supported**.

## 💡 Features
<img src="/data/icons/hicolor/48x48@2x/apps/com.leinardi.gwe.png" width="96" align="right" hspace="0" />

* Show general GPU stats (model name, driver version, gpu/memory/power usage, clocks, temps, etc)
* GPU and Memory overclock offset profiles
* Custom Fan curve profiles
* Change power limit
* Historical data graphs

<img src="/art/screenshot-1.png" width="800" align="middle"/>

## 📦 How to get GWE
If you don't like to reading manuals and/or you don't know what the Nvidia CoolBits are,
you can watch the following How To made by [Intelligent Gaming](https://www.youtube.com/channel/UCH4d4o0Otxa7BNYs5Z5UEjg):

[![How To Overclock And Control Fans On An nVidia Graphic Card In Linux - Green With Envy / GWE](https://img.youtube.com/vi/HAKe9ladLvc/0.jpg)](https://www.youtube.com/watch?v=HAKe9ladLvc)

### Install from Flathub
This is the preferred way to get GWE on any major distribution (Arch, Fedora, Linux Mint, openSUSE, Ubuntu, etc).

If you don't have Flatpak installed you can find step by step instructions [here](https://flatpak.org/setup/).

Make sure to have the Flathub remote added to the current user:

```bash
flatpak --user remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
```

#### Install
```bash
flatpak --user install flathub com.leinardi.gwe
flatpak update # needed to be sure to have the latest org.freedesktop.Platform.GL.nvidia
```

#### Run
```bash
flatpak run com.leinardi.gwe
```
#### ⚠ Flatpak limitations
##### Beta Drivers
Currently [Flatpak does not support Nvidia Beta drivers](https://github.com/flathub/org.freedesktop.Platform.GL.nvidia/issues/1)
like 396.54.09 or 415.22.05.

##### Bumblebee and Optimus
Currently [Flatpak does not support Bumblebee](https://github.com/flatpak/flatpak/issues/869). If you want to use GWE with Bumblebee
you need to install it from the source code.

### Distro specific packages
#### Arch Linux
Install the `gwe` package from the AUR using your favourite helper, for example `yay -S gwe`.

#### Fedora
GWE avaliable in official Fedora [repos](https://src.fedoraproject.org/rpms/gwe) for F31+: `sudo dnf install gwe`

For older Fedora releases you can use [COPR package](https://copr.fedorainfracloud.org/coprs/atim/gwe/): `sudo dnf copr enable atim/gwe -y && sudo dnf install gwe`

### Install from source code
#### Build time dependencies
| Distro                | pkg-config         | Python 3.6+   | gobject-introspection       | meson | ninja-build | appstream-util |
| --------------------- | ------------------ | ------------- | --------------------------- | ----- | ----------- | -------------- |
| Arch Linux            | pkg-config         | python        | gobject-introspection       | meson | ninja       | appstream-glib |
| Fedora                | pkgconf-pkg-config | python3-devel | gobject-introspection-devel | meson | ninja-build | appstream-util |
| OpenSUSE              | pkgconf-pkg-config | python3-devel | gobject-introspection-devel | meson | ninja-build | appstream-glib |
| Ubuntu                | pkg-config         | python3-dev   | libgirepository1.0-dev      | meson | ninja-build | appstream-util |

Arch Linux:
```bash
sudo pacman -S pkg-config python gobject-introspection meson ninja appstream-glib
```
Fedora:
```bash
sudo dnf install pkgconf-pkg-config python3-devel gobject-introspection-devel meson ninja-build appstream-util
```
OpenSUSE:
```bash
sudo zypper install pkgconf-pkg-config python3-devel gobject-introspection-devel meson ninja-build appstream-glib
```
Ubuntu/Debian:
```bash
sudo apt install pkg-config python3-dev libgirepository1.0-dev meson ninja-build appstream-util
```

#### Run time dependencies
| Distro      | Python 3.6+ | pip         | gobject-introspection       | libappindicator          | gnome-shell-extension-appindicator | libdazzle |
|-------------| ----------- | ----------- | --------------------------- | ------------------------ | ---------------------------------- | --------- |
| Arch Linux  | python      | python-pip  | gobject-introspection       | libappindicator3         | gnome-shell-extension-appindicator | libdazzle |
| Fedora      | python3     | python3-pip | gobject-introspection-devel | libappindicator-gtk3     | gnome-shell-extension-appindicator | libdazzle |
| OpenSUSE    | python3     | python3-pip | gobject-introspection       | libappindicator3-1       | gnome-shell-extension-appindicator | typelib-1_0-libdazzle-1_0 |
| Ubuntu      | python3     | python3-pip | libgirepository1.0-dev      | gir1.2-appindicator3-0.1 | gnome-shell-extension-appindicator | libdazzle-1.0-dev |
| Debian      | python3     | python3-pip | libgirepository1.0-dev      | gir1.2-ayatanaappindicator3-0.1  | gnome-shell-extension-appindicator | libdazzle-1.0-dev |
[comment]: <> (TODO: confirm if only debian and only KDE-Plasma. Might affect more systems and Desktop Environments)

Arch Linux:
```bash
sudo pacman -S python python-pip gobject-introspection libappindicator3 gnome-shell-extension-appindicator libdazzle
```

Fedora:
```bash
sudo dnf install python3 python3-pip gobject-introspection-devel libappindicator-gtk3 gnome-shell-extension-appindicator libdazzle
```
OpenSUSE:
```bash
sudo zypper install python3 python3-pip gobject-introspection libappindicator3-1 gnome-shell-extension-appindicator typelib-1_0-libdazzle-1_0
```
Ubuntu:
```bash
sudo apt install python3 python3-pip libgirepository1.0-dev gir1.2-appindicator3-0.1 gnome-shell-extension-appindicator libdazzle-1.0-dev
```

Debian:
```bash
sudo apt install python3 python3-pip libgirepository1.0-dev gir1.2-ayatanaappindicator3-0.1 gnome-shell-extension-appindicator libdazzle-1.0-dev
```

plus all the Python dependencies listed in [requirements.txt](requirements.txt)

For Debian (with KDE-Plasma) we have to use `--break-system-packages`. However, this will break things. Currently only matplotlib.
Then we have to use `sudo pip3 uninstall matplotlib` and then `sudo apt reinstall python3-matplotlib`
#### It is recommended to use the flatpak version for Debian.

#### Clone project and install
If you have not installed GWE yet:
```bash
git clone --recurse-submodules -j4 https://gitlab.com/leinardi/gwe.git
cd gwe
git checkout release
sudo -H pip3 install -r requirements.txt
meson . build --prefix /usr
ninja -v -C build
sudo ninja -v -C build install
```

#### Update old installation
If you installed GWE from source code previously and you want to update it:
```bash
cd gwe
git fetch
git checkout release
git reset --hard origin/release
git submodule init
git submodule update
sudo -H pip3 install -r requirements.txt
meson . build --prefix /usr
ninja -v -C build
sudo ninja -v -C build install
```

#### Run
Once installed, to start it you can simply execute on a terminal:
```bash
gwe
```

#### ⚠ Bumblebee and Optimus
If you want to use GWE with Bumblebee you need to start it with `optirun` and set the `--ctrl-display` parameter to `:8`:

```bash
optirun gwe --ctrl-display ":8"
```

## ℹ️ TODO

- [x] Show general GPU info
- [x] Show power info
- [x] Show clocks info
- [x] Show GPU temp in both app and app indicator
- [x] Show fan info
- [x] Allow to hide main app window
- [x] Add command line option to start the app hidden
- [x] Add Refresh timeout to settings
- [x] Add command line option to add desktop entry
- [x] About dialog
- [x] Distributing with PyPI
- [x] Show chart of selected fan profile
- [x] Allow to select and apply a fan profile
- [x] Add/Delete/Edit multi speed fan profiles (fan curve)
- [x] Add option to restore last applied fan profile on app startup
- [x] Find better icons for app indicator
- [x] Try to lower resource consumption (mostly caused by `nvidia-settings` invocations)
- [x] Show historical data of most important values in a separate dialog (requires GTK 3.24/GNOME 3.30)
- [x] Add overclock profiles
- [x] Add option to restore last applied overclock profile on app startup
- [ ] Disable unsupported preferences
- [x] Distributing with Flatpak
- [x] Publishing on Flathub
- [ ] Distributing with Snap
- [x] Check if NV-CONTROL is available and tell the user if is not
- [ ] Add support for multi-GPU
- [ ] Allow to select profiles from app indicator
- [ ] Add support for i18n (internationalization and localization)

<!--
## Application entry
To add a desktop entry for the application run the following command (not supported by Flatpak):
```bash
gwe --application-entry
```
If you don't want to create this custom rule you can run gwe as root
(using sudo) but we advise against this solution.
-->
## ⌨️ Command line options

  | Parameter                 | Description                               | Source | Flatpak |
  |---------------------------|-------------------------------------------|:------:|:-------:|
  |-v, --version              |Show the app version                       |    x   |    x    |
  |--debug                    |Show debug messages                        |    x   |    x    |
  |--hide-window              |Start with the main window hidden          |    x   |    x    |
  |--ctrl-display DISPLAY     |Specify the NV-CONTROL display             |    x   |    x    |
  |--autostart-on             |Enable automatic start of the app on login |    x   |         |
  |--autostart-off            |Disable automatic start of the app on login|    x   |         |

## 🖥️ Build, install and run with Flatpak
If you don't have Flatpak installed you can find step by step instructions [here](https://flatpak.org/setup/).

Make sure to have the Flathub remote added to the current user:

```bash
flatpak --user remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
```

### Clone the repo
```bash
git clone --recurse-submodules -j4 https://gitlab.com/leinardi/gwe.git
```
It is possible to build the local source or the remote one (the same that Flathub uses)
### Local repository
```bash
./build.sh --flatpak-local --flatpak-install
```
### Remote repository
```bash
./build.sh --flatpak-remote --flatpak-install
```
### Run
```bash
flatpak run com.leinardi.gwe --debug
```

## ❓ FAQ
### I see some message about CoolBits in the Overclock/Fan profile section, what's that?
Coolbits was a Windows registry hack for Nvidia graphics cards Windows drivers, that allows
tweaking features via the Nvidia driver control panel.
Something similar is available also on Linux and is the only way to enable Overclock and manual Fan control.
To know more about Coolbits and how to enable them click
[here](https://wiki.archlinux.org/index.php/NVIDIA/Tips_and_tricks#Enabling_overclocking)
(to enable both OC and Fan control you need to set it to `12`).

### Can I make the power limit survive a reboot?
GWE cannot set the power limit automatically because, to change this value, root permission is required.  
If your distribution is using systemd, you can easily set the power limit on boot creating a custom service.

Simply create a new file `/etc/systemd/system/nvidia-tdp.timer` and paste the following text inside:
```
[Unit]
Description=Set NVIDIA power limit on boot

[Timer]
OnBootSec=5

[Install]
WantedBy=timers.target
```

Then create another file `/etc/systemd/system/nvidia-tdp.service` and paste the following text inside (replace `XXX` with the power limit value you want to set):
```
[Unit]
Description=Set NVIDIA power limit

[Service]
Type=oneshot
ExecStartPre=/usr/bin/nvidia-smi -pm 1
ExecStart=/usr/bin/nvidia-smi -pl XXX
```

Finally, run the following command:
```
sudo systemctl enable nvidia-tdp.timer
```

### The Flatpak version of GWE is not using my theme, how can I fix it?
To fix this issue install a Gtk theme from Flathub. This way, Flatpak applications will automatically pick the
installed Gtk theme and use that instead of Adwaita.

Use this command to get a list of all the available Gtk themes on Flathub:
```bash
flatpak --user remote-ls flathub | grep org.gtk.Gtk3theme
```
And then just install your preferred theme. For example, to install Yaru:
```
flatpak install flathub org.gtk.Gtk3theme.Yaru
```

### I have installed the app using Flatpak, but all the GWE fields are empty
This issue can be usually solved by closing GWE, executing `flatpak update` and starting GWE again.
This is necessary to be sure to have the latest [org.freedesktop.Platform.GL.nvidia](https://github.com/flathub/org.freedesktop.Platform.GL.nvidia).
If, after the update, all the fields are still empty, feel free to open a new issue on the project tracker.

### Why the memory overclock offsets effectively applied does not match the one set in the Nvidia Settings app?
Because Memory Transfer Rate, what Nvidia Settings reports and changes,
is different from the effective Memory Clock, what is actually being
displayed by GWE. It is also what other Windows applications like MSI Afterburner show.
The Memory Transfer Rate is simply double the Memory Clock.

### Where are the settings and profiles stored on the filesystem?
| Installation type |                     Location                     |
|-------------------|:------------------------------------------------:|
| Flatpak           |        `$HOME/.var/app/com.leinardi.gwe/`        |
| Source code       | `$XDG_CONFIG_HOME` (usually `$HOME/.config/gwe`) |

### GreenWithEnvy, why using such name?
The name comes from the slogan of the GeForce 8 series, that was "Green with envy".
Nvidia is meant to be pronounced "invidia", which means envy in Latin (and Italian). And their logo is green so, GreenWithEnvy

## 💚 How to help the project
### Help is needed for the following topics
 - Snap (see [#18](https://gitlab.com/leinardi/gwe/issues/18))
 - Getting current GTK theme text color (see [#36](https://gitlab.com/leinardi/gwe/issues/36))
 - Making Bumblebee work with Flatpak (see [#35](https://gitlab.com/leinardi/gwe/issues/35))

### Discord server
If you want to help testing or developing it would be easier to get in touch using the discord server of the project: https://discord.gg/xBybdRt
Just write a message on the general channel saying how you want to help (test, dev, etc) and quoting @leinardi. If you don't use discor but still want to help just open a new issue here.


### Can I support this project some other way?

Something simple that everyone can do is to star it on both [GitLab](https://gitlab.com/leinardi/gwe) and [GitHub](https://github.com/leinardi/gwe).
Feedback is always welcome: if you found a bug or would like to suggest a feature,
feel free to open an issue on the [issue tracker](https://gitlab.com/leinardi/gwe/issues).

## ⚠ Dropped PyPI support
Development builds were previously distributed using PyPI. This way of distributing the software is simple
but requires the user to manually install all the non Python dependencies like cairo, glib, appindicator3, etc.
The current implementation of the historical data uses a new library, Dazzle, that requires Gnome 3.30 which is
available, using Python Object introspection, only starting from Ubuntu 18.10 making the latest Ubuntu LTS, 18.04,
unsupported.
A solution for all this problems is distributing the app via Flatpak, since with it all the dependencies
will be bundled and provided automatically, making possible to use Gnome 3.30 features also on distributions
using an older version of Gnome.

**No new build will be published on PyPI**.

### Uninstall pip version
If you have already installed GWE via `pip`, please make sure to uninstall it completely before moving to a newer version:

```bash
pip3 uninstall gwe
rm -rf ~/.config/gwe
```

## ℹ️ Acknowledgements
Thanks to:

 - GabMus and TingPing for the huge help with Flatpak
 - @999eagle for maintaining the [AUR package](https://aur.archlinux.org/packages/gwe/)
 - @tim74 for maintaining the [COPR package](https://copr.fedorainfracloud.org/coprs/atim/gwe/)
 - Lighty for moderating the [Discord](https://discord.gg/YjPdNff) server
 - fbcotter for the [py3nvml](https://github.com/fbcotter/py3nvml/) library
 - all the devs of the [python-xlib](https://github.com/python-xlib/python-xlib/) library
 - tiheum for the [Faenza](https://www.deviantart.com/tiheum/art/Faenza-Icons-173323228) icons set, from which I took the current GWE launcher icon
 - all the people that helped testing and reported bugs

## 📰 Media coverage
 - [OMG! Ubuntu](https://www.omgubuntu.co.uk/2019/02/easily-overclock-nvidia-gpu-on-linux-with-this-new-app) 🇬🇧
 - [GamingOnLinux](https://www.gamingonlinux.com/articles/greenwithenvy-an-impressive-tool-for-overclocking-nvidia-gpus.13521) 🇬🇧
 - [Phoronix](https://www.phoronix.com/scan.php?page=news_item&px=GreenWithEnvy-0.11-Released) 🇬🇧
 - [ComputerBase](https://www.computerbase.de/2019-02/green-envy-uebertakten-nvidia-grafikkarten-linux/) 🇩🇪
 - [lffl](https://www.lffl.org/2019/02/overclock-scheda-nvidia-linux.html) 🇮🇹
 - [osside blog](https://www.osside.net/2019/02/greenwithenvy-gwe-linux-easy-nvidia-status-overclock/) 🇮🇹
 - [Diolinux](https://www.diolinux.com.br/2019/02/greenwithenvy-uma-nova-forma-de-voce-gerenciar-gpu-nvidia.html?m=1) 🇧🇷
 - [Blog do Edivaldo](https://www.edivaldobrito.com.br/overclock-em-gpus-nvidia-no-linux/) 🇧🇷
 - [Linux Adictos](https://www.linuxadictos.com/greenwithenvy-programa-para-overclocking-en-gpus-nvidia.html) 🇪🇸


## 📝 License
```
This file is part of gwe.

Copyright (c) 2019 Roberto Leinardi

gwe is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

gwe is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with gwe.  If not, see <http://www.gnu.org/licenses/>.
```
