# Packaging the NVML continuation

Reviewed on 2026-10-03. This is a proposed packaging architecture, not an available `.deb` or Flatpak
release. The current menu installation is a user-owned source snapshot using a prepared external Python
environment; the installed root helper is a separately reviewed directory and systemd unit.

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
integration during OS migration. This recommendation has not selected package names or implemented
build scripts. It does not prohibit a later Flatpak UI.

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
