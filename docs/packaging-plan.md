# Native packaging

Latest prepared candidate: `build/icon-fix-rc1-9/gwe-nvml_1.0.0~rc1-9_all.deb`, runtime source
`82f8087`. All 632 tests, GTK public/tray icon lookup and the extracted native Wayland GUI check pass.
Protocol inspection confirms the isolated `.Smoke` window identity. Checksums, source correspondence
and absence of private databases in the package were verified. Installed KDE visual acceptance remains
pending; installed hardware acceptance of earlier revisions does not automatically cover this candidate.

The installed correction is `1.0.0~rc1-8`, adding guarded curve resume and saved-power startup
restoration. Installed suspend and reboot acceptance remains pending. See
[suspend/resume](suspend-resume.md) and [power persistence](power-control.md#native-startup-persistence).
Preserve accepted rc1-6 bytes and earlier release artifacts.

**Current acceptance (2026-10-10):** the corrected rc1-6 package passes installed lifecycle and
service supervisor SIGKILL/watchdog recovery on KDE/Wayland and Ubuntu 26.04.1. See the
[acceptance record](continuous-control-incident.md#corrected-service-acceptance-2026-10-10).

The accepted package is `build/curve-fix-rc1-6/gwe-nvml_1.0.0~rc1-6_all.deb` (runtime source
`8c6ad03`). Its extracted system-Python GTK check also passes, including a six-second GTK stall
and persistent fault display. Preserve these tested bytes and the original rc1-5 assets.
`BUILD_INFO` and `SHA256SUMS` accompany the package. A corrected publication set/tag still needs
preparation; no package was rebuilt or published during the acceptance follow-up.

The 1.0.0 fork maintained by alamios ships one **gwe-nvml** `.deb` containing an unprivileged GTK desktop
and a separately privileged NVML helper. Source and packages are intended for
[GitHub Releases](https://github.com/alamios/gwe/releases); no publication has occurred in this session.
The fork is maintained with AI assistance. Flatpak publication is outside the initial release scope.

## Build and inspect

Use system Python 3.14 on the migrated host, plus `dpkg-deb`, `glib-compile-resources` and
`glib-compile-schemas`. The builder needs the exact reviewed pure-Python distributions declared in
`scripts/build_debs.py`, including original distribution metadata and licenses. Standalone inputs
are preserved at `.local-backups/build-dependencies-py314/`, with a `SHA256SUMS` manifest; the old
3.12 interpreter environment is not required. No dependencies are installed into system Python.

On 2026-10-10, the old 3.12 environment was retired to a private recovery archive. System Python
3.14.4 passes all 632 tests using the preserved standalone inputs, and builds the native package
after retirement. The rebuilt executable payload matches rc1-8; only the updated packaged documentation
and its checksum differ. The installed rc1-8 package passes `dpkg -V`. Generated extraction/staging trees
and temporary duplicate builds were removed after validation; retained packages, checksums, build records
and original publication assets remain. Trial state and diagnostics were archived privately.

`scripts/stage_build_dependencies.py SOURCE_SITE_PACKAGES NEW_DESTINATION` prepares those inputs
from an already reviewed dependency set, refusing changed/missing versions and unsafe file paths.
The builder independently verifies versions and required licenses. Verify the preserved input
manifest before building. Use a new destination and a fixed source epoch:

```bash
(cd .local-backups/build-dependencies-py314 && sha256sum --check SHA256SUMS)
PYTHONPATH="$PWD/.local-backups/build-dependencies-py314" /usr/bin/python3 \
  scripts/build_debs.py build/new-candidate --version 1.0.0~rc1-8 --epoch 1791590400
```

Keep a checksum and build/acceptance record alongside every retained release artifact.
Inspect with `dpkg-deb --info` and `dpkg-deb --contents`. The directory also contains unpacked review trees,
licenses, dependency versions and a reviewed service bundle. No private database, UUID or user configuration
is included. Build destinations are never cleared automatically.

The package uses system Python. GTK, Matplotlib, XDG, Xlib, requests and packaging are declared system
dependencies; the reviewed pure-Python vendor modules retain their original licenses. The bundled Peewee
3.17.0 migration literals receive two explicit escaping corrections, recorded in `BUNDLED_PATCHES`;
the parsed code and runtime regex strings are unchanged. Python warnings are not globally suppressed.
Legacy internal resource/icon names retain upstream attribution; the public application/desktop identity
is `io.github.alamios.gwe` and the user database has its own native namespace.

Debian revision `1.0.0~rc1-5` retains the scoped contrast/circular title-button fixes and separate
maintainer credits, points the development changelog to `main`, and keeps native error notices nonblocking;
the application version remains `1.0.0-rc1`. It upgrades the original candidate through ordinary APT.
Earlier package/source artifacts and diagnostics are retained in a private, checksummed
Git-ignored `.local-backups/` archive. Generated build trees were cleaned;
`build/publish-v1.0.0-rc1/` retains the original assets unchanged. Correction builds use fresh directories.

## Installing the reviewed candidates

The first X11 prerelease passed installed rc1-5 acceptance; publication has not occurred.
The publish directory retains the exact tested package plus tagged source and checksums. Close all
GWE applications and let recovery finish before installing, updating, downgrading or removing the package.
Review the APT simulation first:

```bash
apt-get --simulate install ./gwe-nvml_1.0.0~rc1-5_all.deb
sudo apt install ./gwe-nvml_1.0.0~rc1-5_all.deb
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

This historical wrapper targets the original `build/release-rc1` artifact, not revision 5. Use the
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

The local `build/power-persistence-rc1-8/gwe-nvml_1.0.0~rc1-8_all.deb` was built from source
commit `4acec67`. All packaged desktop Python modules match that source; the privileged helper is
unchanged from rc1-7. The checksum and absence of private databases were verified. All 632 source
tests and the final extracted-package native GTK check pass on system Python 3.14.4, with isolated
configuration, synthetic control and read-only telemetry. Actual installed reboot power restoration
and the included suspend/reapplication correction remain pending. Older dated acceptance remains
evidence for its tested revision only; the package has not been installed or published by the agent.

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
