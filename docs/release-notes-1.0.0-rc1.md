# GreenWithEnvy 1.0.0-rc1

First candidate of the independent [alamios/gwe](https://github.com/alamios/gwe) fork of
[Roberto Leinardi's original GreenWithEnvy](https://gitlab.com/leinardi/gwe), maintained with AI
assistance. Original authors, credits, history and GPL-3.0-or-later licensing are retained.

- NVML GPU monitoring, custom fan curves and explicit power-limit control.
- One native `.deb`, with an unprivileged GTK desktop and separately supervised privileged helper.
- Installation-time authorization; ordinary launch requires no terminal or password.
- Writable curve editor, startup profile persistence, automatic mode and minimize-to-tray behavior.
- Readable links and title controls, consistent circular hover feedback and separate maintainer credits.

Initial validation targets RTX 3090 Ti / NVIDIA 580.178.04 / Ubuntu-Kubuntu 24.04.5 / KDE X11.
Kubuntu 26.04, Wayland and other hardware remain untested. Clock-offset control is unsupported.
Driver/host failure recovery and independently recorded suspend/resume remain outside the validated scope.
Power changes require explicit Apply and verification; committed limits remain after ordinary exit.

Download the `.deb` and `SHA256SUMS`, verify the package, quit any other GPU fan controller, then install:

```bash
sudo apt install ./gwe-nvml_1.0.0~rc1-5_all.deb
```

Launch **GreenWithEnvy** from the menu. No venv or repository installer is required.
This fork currently has no Flatpak or PyPI distribution. Preserve existing profile backups before import;
see the configuration/import and recovery documentation included in the repository.

Installed native acceptance passed on 2026-10-04: startup with the saved curve, editor/tray/Quit,
SIGKILL and SIGSTOP/watchdog recovery, with automatic fans, unchanged power and restored CoolerControl.
The previous rc1-3 GUI hang's exact cause remains unconfirmed; rc1-5 includes nonblocking error notices
validated with continued fan renewals and Quit while a notice is open. Please report recurring hangs.
