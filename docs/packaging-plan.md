# Native packaging

The 1.0.0 fork maintained by alamios ships one **gwe-nvml** `.deb` containing an unprivileged GTK desktop
and a separately privileged NVML helper. Source and packages are intended for
[GitHub Releases](https://github.com/alamios/gwe/releases); no publication has occurred in this session.
The fork is maintained with AI assistance. Flatpak publication is outside the initial release scope.

## Build and inspect

Use the prepared Python 3.12 environment with the exact reviewed modules in `scripts/build_debs.py`,
plus `dpkg-deb`, `glib-compile-resources` and `glib-compile-schemas`. The builder installs no dependencies
and refuses changed vendor versions. Use a new destination and a fixed source epoch:

```bash
python scripts/build_debs.py build/release-rc1-4 --version 1.0.0~rc1-4 --epoch 1790985600
```

Verify checksums from their directory with `cd build/release-rc1-4 && sha256sum --check SHA256SUMS`.
Inspect with `dpkg-deb --info` and `dpkg-deb --contents`. The directory also contains unpacked review trees,
licenses, dependency versions and a reviewed service bundle. No private database, UUID or user configuration
is included. Build destinations are never cleared automatically.

The package uses system Python. GTK, Matplotlib, XDG, Xlib, requests and packaging are declared system
dependencies; the reviewed pure-Python vendor modules retain their original licenses. The bundled Peewee
3.17.0 migration literals receive two explicit escaping corrections, recorded in `BUNDLED_PATCHES`;
the parsed code and runtime regex strings are unchanged. Python warnings are not globally suppressed.
Legacy internal resource/icon names retain upstream attribution; the public application/desktop identity
is `io.github.alamios.gwe` and the user database has its own native namespace.

Debian revision `1.0.0~rc1-4` retains the scoped contrast/circular title-button fixes and separate
maintainer credits, and points the development changelog to `main`;
the application version remains `1.0.0-rc1`. It upgrades the original candidate through ordinary APT.
Earlier artifacts are retained for rollback.

## Installing the reviewed candidates

The first candidate is prepared for local acceptance, not yet declared a validated release. Close all
GWE applications and let recovery finish before installing, updating, downgrading or removing the package.
Review the APT simulation first:

```bash
apt-get --simulate install ./gwe-nvml_1.0.0~rc1-4_all.deb
sudo apt install ./gwe-nvml_1.0.0~rc1-4_all.deb
```

Replacing the installed development pair intentionally removes only `gwe-nvml-client` and
`gwe-nvml-service`; the combined package declares Conflicts/Replaces for their shared files. Review any
other proposed package change separately. Do not use force-overwrite or blindly accept driver/CUDA/kernel
changes. The owner installs missing system dependencies.

The APT command above is the normal installation procedure. Package maintainer scripts perform helper
authorization and socket setup; the desktop creates its writable configuration on first launch.
No repository installation script, development venv or hardware trial is required to install the package.

For optional development acceptance in this workspace with already installed dependencies, one command combines
checksums, controller exclusion, an allowlisted APT simulation, installation and unprivileged acceptance:

```bash
bash scripts/install_release_candidate.sh
```

This historical wrapper targets the original `build/release-rc1` artifact, not revision 4. Use the
ordinary APT command for the updated package and run installed acceptance separately if needed.
It permits only the combined GWE package and removal of the old GWE pair; any other proposed package
change aborts before sudo. It requests administrative authorization for installation only. The grouped
acceptance requires the configured custom curve and verifies recovery without changing power. This
command has been tested with fake APT/sudo; the actual installation has not been executed. It is a
validation convenience, not an installation dependency or the release's normal user flow.

Installation preserves existing `/etc/gwe-fan-service.json`. Fresh setup uses the installing desktop UID
from sudo/pkexec and read-only enumeration of exactly one GPU; ambiguous identity or an unrecognized
socket authorization override fails closed. It enables only `gwe-fan-service.socket`, not an active fan
controller. Installing from a root session without an authorized desktop UID requires explicit setup.
The GUI is never run as root and normal launch uses no sudo. An unmanaged historical helper must first
be archived/migrated explicitly; the package refuses to overwrite it. The old pinned v5 installer is a
historical migration tool, not the unified candidate installer.

The authorized 0600 Unix SEQPACKET socket authenticates kernel peer credentials. The helper supervises
the GUI PID, preserves the first connection, records/stops competing CoolerControl and restores its prior
state after verified fan recovery. Lease expiry, watchdog and post-stop recovery remain enabled. Package
operations stop socket activation and recheck inactive/recovery guards before replacing files. Existing
private authorization and profiles are retained on package removal.

See [configuration/import and desktop acceptance](native-desktop.md) before first launch: the old profile
source is copied and archived, never modified. Applying custom profiles at startup is a hardware write.

## Validation and rollback

Automated checks cover real sockets with synthetic backends, rejected credentials/descriptors/modes,
maintainer-script races, deterministic archives, private-data exclusion and a real split/combined/rollback
dpkg transaction in an isolated root. Source GTK checks use simulated writes and live telemetry. Final
acceptance must use the installed unified package and system Python, including socket activation,
profile persistence/editor/tray, explicit Quit and recovery. Target OS/Wayland remain untested.

Keep the previous split `.deb` archives and private configuration backups. After Quit and verified recovery,
remove only `gwe-nvml` through APT and reinstall the retained split pair for rollback. Preserve native edits
before restoring the archived earlier launcher JSON. Do not restore an unmanaged-helper archive over a
package-owned directory or overwrite the original profile source.

For the earlier experiments and pinned split installer, see [packaging history](native-packaging-history.md).
