# Packaging the NVML continuation

Reviewed on 2026-10-03. Two local native `.deb` candidates can now be built and inspected; installation
and target-OS acceptance remain pending. There is no new Flatpak release. The current menu installation
is a user-owned source snapshot using a prepared external Python environment; the installed root helper
is a separately reviewed directory and systemd unit.

## Two deliverables

The desktop client contains Python modules, a launcher, compiled GTK resources/settings schemas, icons
and application metadata. It runs without root and owns only a renewable fan-control lease. The host
helper contains the bounded fan/power implementation, pinned NVML binding, systemd unit and recovery
entry point. It runs on the host with the explicitly configured desktop UID and GPU identity. Driver,
CUDA toolkit and kernel packages are not bundled or replaced by either application package.

Python does not require generating a native standalone executable. The executable entry is a launcher;
native GTK and NVIDIA libraries are supplied by a distribution or Flatpak runtime/driver integration.
Freezing Python does not remove the host-service, GTK or driver compatibility requirements.

For the owner's Kubuntu-first use, the recommended initial reproducible package target is native `.deb`
packaging, with separate client/helper packages and declared dependencies. This avoids adding sandbox
integration during OS migration. The builder now emits `gwe-nvml-client` and `gwe-nvml-service`.
It does not prohibit a later Flatpak UI.

## Native candidates: build and review

Use the reviewed Python 3.12 build environment, containing the exact vendor versions declared in
`scripts/build_debs.py`, plus `dpkg-deb` and GLib resource/schema compilers. No packages are installed by
the builder. Choose a new destination, an explicit Debian version and a fixed source epoch:

```bash
python scripts/build_debs.py build/native-candidates --version 0.15.9+nvml20261003.3 --epoch 1790985600
```

The build produces two `.deb` files, `SHA256SUMS`, unpacked review trees and the reviewed service bundle.
The desktop client contains precompiled resources and private vendored pure-Python modules for Injector,
Peewee, Reactivex, typing-extensions, both NVML bindings and xmltodict, with exact versions, original source
headers and distribution license files. Installed metadata with private origin paths is not copied.
GTK, Matplotlib, Xlib, XDG, requests and their native dependencies are declared distro dependencies.
The client entry uses system Python and requires an explicit private local configuration/backup, reusing
the existing local configuration format rather than importing a personal profile automatically.

The host helper installs its code at the already validated `/opt/gwe-fan-service` path and the unit at
`/usr/lib/systemd/system/gwe-fan-service.service`. It supplies only a configuration example; existing
`/etc/gwe-fan-service.json` is never embedded, overwritten or purged by the package. Configure a desktop
UID and pinned UUID explicitly on a fresh machine. Neither package starts/enables a service, changes
GPU settings or touches CUDA/kernel/driver packages. Configuration and profiles are not payload files.

Package changes refuse active control, pending ownership/power/session recovery or a remaining runtime
override. Failed inspection of an existing helper also refuses the operation. The service package rejects
an existing unmanaged helper on first installation. **Do not install it over the current manual helper.**
Migration requires a verified inactive/recovered service, archiving the current code and `/etc` unit,
preserving private configuration, and removing the archived unit's shadowing copy only after the archive
is verified. That system migration has not been executed by the agent.

Inspect candidate metadata/content with `dpkg-deb --info` and `dpkg-deb --contents`. Resolve declared
dependencies only after reviewing the exact transaction; the current system lacks several of the native
Python packages, so a successful venv/simulated GUI check is not a native installation acceptance.
The owner installs missing system dependencies; the agent does not change system packages independently.
Close both client launchers and recover the service before package update/downgrade/removal. Retain prior
`.deb` files and private configuration for rollback; no automatic package downgrade or profile migration
occurs in maintainer scripts.

Validation covers matching archives from identical source/epoch/input files, root-owned payload metadata,
absence of personal DB/config, guard rejection, precompiled resources and a staged client GTK startup/
Restore check with simulated control. Builds export code from the reviewed installed build environment;
fully independent clean-room builds still need immutable dependency archives/hashes and target-native
dependency acceptance. Do not treat version pins alone as supply-chain authentication.
The initial complete local artifacts are retained in `build/native-debs-v3/` with version
`0.15.9+nvml20261003.3`. A second complete build produced identical archive hashes. The client extracted
from the final `.deb` passed the simulated GTK startup/Restore check; native installation remains pending.
The later `build/native-debs-v4/` candidates, version `0.15.9+nvml20261003.4`, include the verified
persistent read-only NVML session correction for encoder/decoder telemetry. Earlier candidates remain
retained; no native package was installed automatically.

## Installing the reviewed candidates

For the existing manual installation only, close both GWE clients and run from a desktop terminal:

```bash
bash scripts/install_native.sh
```

This owner-run system installation requires sudo authentication. It pins both version
`0.15.9+nvml20261003.4` artifact hashes, copies them to private root-owned staging, verifies an inactive
helper with no pending recovery, and validates the existing private service configuration without NVML
calls. The desktop wrapper checks competing GWE clients and holds the existing session lock.

The current dependency simulation requires 25 new desktop packages (Matplotlib, Xlib and dependencies),
with no upgrades/removals; the two GWE packages make 27 new packages total. Recommended packages are
omitted. The installer refuses unrelated packages, upgrades and removals in the dependency simulation.
It installs pinned dependency versions before moving the manual helper. It does not run apt update,
autoremove, change repository priorities or request driver/kernel/CUDA changes.

The original helper and shadowing `/etc` unit are retained in a private, uniquely named
`/var/backups/gwe-native-*` directory, together with a verified private configuration copy. The live
configuration is preserved. The archive path and rollback command are printed before package installation.
The original Flatpak, profile backup, local snapshots and startup preference remain intact.
After installation, the wrapper checks the installed GTK client using system Python and simulated
startup/Restore control. It does not activate the real curve. Afterwards, launch with `gwe-nvml` or
**GreenWithEnvy (NVML native)**; the configured startup curve then applies as usual.

If installation fails after moving the manual helper, retain the printed archive and do not launch GWE.
Recovery: `sudo sh /var/backups/gwe-native-<printed-suffix>/restore.sh`.
This refuses active/pending control, removes only the two GWE packages through dpkg, restores the original
code and unit, and reloads systemd. It neither overwrites live configuration nor starts the service.
If package removal fails, the archive is retained and recovery stops for review. Newly installed desktop
dependencies are intentionally retained on rollback.

Validation: focused installer/package tests cover rejection of unexpected dependency changes and
preserving the archive when rollback package removal fails. Actual sudo installation and native
system-Python GTK acceptance still require the owner's terminal run.

## Flatpak option

A Flatpak would package the desktop client; the host helper remains a separately installed native package.
Flatpak sandboxing restricts host processes, services and files by default. The current host wrapper's
sudo/systemctl preparation, root launcher-PID supervision and desktop-controller inspection cannot simply
be copied into a sandbox unchanged. A reviewed host-side activation/session interface is required, with
explicit authorization and the same ownership, watchdog, thermal and post-stop recovery guarantees.
Possible transports include a narrowly permitted D-Bus interface or deliberate exposure of the existing
Unix socket; exposure alone does not implement authorized service startup/cleanup.

Required work before calling it supported:

1. Choose an independent application ID and an explicit profile import/rollback procedure. Keep the old
   Flatpak intact during acceptance; never point a writable new database at the old configuration.
2. Review the historical Flathub manifest without running `build.sh`, then prepare a new maintained
   manifest with a tested GTK3-capable runtime/SDK. Pin dependencies and sources/checksums. Check Dazzle,
   AppIndicator, Notify and Python dependencies against the chosen runtime rather than assuming availability.
3. Compile resources and schemas during build, not into the read-only installed `/app` tree at launch.
   Use Flatpak-private state directories. Adapt the current development/resource launcher accordingly.
4. Add minimal Wayland/X11 and service permissions; validate NVML library/device access against the host
   NVIDIA driver integration. A Python NVML binding alone does not supply the native driver library.
5. Build locally with `flatpak-builder`, inspect artifacts and run the complete UI/control/recovery
   acceptance against the installed host helper. Test disconnects, shutdown, stale telemetry and denied
   authorization across the sandbox boundary. No global host access or sandbox escape as a substitute.
6. Export a local repository or a `.flatpak` bundle with `flatpak build-bundle`. The single-file artifact
   still requires its runtime and does not install the privileged host helper. No Flathub publication or
   remote hosting is necessary for personal installation.

Primary references consulted on 2026-10-03:
[first build and manifest/runtime/SDK](https://docs.flatpak.org/en/latest/first-build.html),
[sandbox permissions](https://docs.flatpak.org/en/latest/sandbox-permissions.html),
[single-file bundles](https://docs.flatpak.org/en/latest/single-file-bundles.html).

## Migration scope

Future driver compatibility is the goal, not a promise to support old drivers indefinitely. An upgrade
rollback is still a recovery option if a new kernel/driver fails to boot or load. It is distinct from the
application's support policy. Earlier observations of broken `nvidia-fs` DKMS sources, CUDA repository
priority and NVIDIA utilities from a different driver branch need current read-only reassessment before
system changes. Their relevance to the owner's workload must be established; do not automatically remove
or replace packages. Package builds do not authorize kernel, driver or distribution upgrades.
