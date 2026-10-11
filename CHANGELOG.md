# Changelog

## 1.0.0-rc1 — unreleased

Independent fork maintained by alamios with AI assistance. Original GWE authors and GPL-3.0-or-later
license retained. Validation scope and remaining release gates are in [validation](docs/validation.md).

- Replace desktop X11 GPU-control dependencies with NVML telemetry and supervised fan/power control.
- Preserve editable curves, hysteresis, startup profile restoration and minimize-to-tray behavior.
- Renew fan leases independently of GTK; supervise privileged workers with watchdog and verified recovery.
- Report unexpected control loss with persistent notices and desktop notifications.
- Restore the previously applied curve once after detected suspend and verified service recovery.
- Verify power writes with identity/range checks, compare-and-set, readback and rollback journals.
- Save verified power targets per GPU and restore them once on normal application startup.
- Package the unprivileged desktop and privileged helper in one native `.deb`, with installation-time
  authorization and terminal-free launch.
- Publish desktop/tray artwork under the native identity and align GTK identity for Wayland integration.
- Improve title-button contrast/hover, links, nonblocking error notices and maintainer credits.
- Update project/support links, consolidate documentation and disclose AI maintenance.

Clock-offset/overclock control is unsupported. Installed automatic resume and the latest KDE icon
rendering still require acceptance; power restoration has owner-reported functional evidence.
