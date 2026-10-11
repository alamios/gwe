# User guide

## Installation and updates

Install the native `gwe-nvml` package with APT; it contains both the GTK desktop and its helper.
The package declares the system libraries it requires and bundles reviewed pure-Python dependencies.
It does not install or update NVIDIA drivers, CUDA or the kernel.

Before installing, updating or removing GWE, pause GPU work, choose **Quit** and wait for recovery.
Closing the window may only minimize it to the tray. An active helper or unresolved recovery journal
blocks package changes; do not bypass this guard or delete journals to force an update.

Launch **GreenWithEnvy** from the menu or run `gwe-nvml`. The desktop runs as the authorized user;
installation configures the helper's desktop-user authorization and pinned GPU identity.

## Fan curves

Use the fan editor to create or edit a profile, then select it and press **Apply**. Selecting or editing
a profile alone does not replace the running curve. GWE checks its points against the GPU's current
manual fan range; invalid points are rejected rather than silently clamped.

Applying **Automatic** releases manual fan control. With the "load last profile" preference enabled,
GWE restores the last applied compatible curve once after fresh startup telemetry. Profiles are stored
by ID, so duplicate names do not make startup selection ambiguous.

Hiding to the tray retains control. **Quit** releases the curve and verifies automatic fan restoration.
Do not run another controller against the same GPU. The helper coordinates CoolerControl when present
and restores its prior service state after the control session ends.

## Power limits

Select a limit and press **Apply**. A successful operation requires service verification and exact
hardware readback. GWE saves only the verified target, associated with the GPU identity.

A committed limit remains in effect after normal Quit. On the next normal launch, GWE checks fresh
telemetry, identity, live constraints and fan-control state before restoring the saved target once.
If the current limit already matches, it performs no write. Explicit Apply supersedes pending startup
restoration. Rejected, rolled-back or uncertain operations do not replace the saved target or retry.

NVIDIA limits can reset on reboot or driver unload. GWE restores the preference when the application
opens, including login autostart; there is no separate boot-time power setter. Suspend recovery does
not reapply power. A storage failure is reported separately from a successfully verified hardware change.

## Startup and suspend

Enable login launch through GWE preferences if desired. Startup can apply both the saved fan profile
and saved power target; it is not a read-only launch. The login entry uses the native desktop identity.

After detecting suspend, an active curve waits for verified service recovery, then attempts to reacquire
the exact previously applied curve once. Quit, release or deletion of the applied profile cancels this.
A merely selected or edited curve is not substituted. Other failures remain latched for inspection.
Installed automatic resume acceptance is still pending; see [validation](validation.md).

## Readings and icons

Unavailable sensors stay blank. Encoder/decoder readings require actual use of those engines; video
playback may use software decoding, and playback alone does not require the encoder.

The package supplies the original artwork under the native desktop identity and advertises the tray
icon directory. The latest icon correction passes GTK lookup and isolated Wayland checks; installed
KDE rendering still needs confirmation.

## Control failures and recovery

A persistent "GPU control stopped" notice means the selected curve is no longer maintained by GWE.
Inspect the service and actual readings before restarting. A selected profile label is not proof of
active control, and a failed recovery is not cleared by dismissing its notice.

Read service state and logs with:

```bash
systemctl status gwe-fan-service.service gwe-fan-service.socket
journalctl -u gwe-fan-service.service -b
```

If recovery is unverified, quit GWE and inspect whether service processes remain. Manual recovery must
only run after the service is inactive or failed and both its main/control PIDs are zero. The reviewed
installed helper can then recover retained journals:

```bash
systemctl show gwe-fan-service.service -p ActiveState -p MainPID -p ControlPID
sudo /usr/bin/python3 -I -B /opt/gwe-fan-service/entry.py recover
```

Recovery can restore fans, interrupted power transactions and the prior cooling-service state. It does
not reset an already committed power limit merely because GWE closed. An error requires inspection;
do not repeatedly launch controllers or remove recovery records. See [architecture](architecture.md).

## Uninstall and rollback

After Quit and verified recovery, remove the package with `sudo apt remove gwe-nvml`. Keep private
configuration and backups if you intend to reinstall. Do not manually delete package-owned files.
For rollback, retain a tested `.deb` and a verified configuration backup; install that package through
APT only after recovery completes. Review schema compatibility before restoring an older database.
