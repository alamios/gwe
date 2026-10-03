# Local builds and future releases

This maintenance continuation has no published release or chosen public hosting namespace yet.
The installed Flathub application is the historical upstream build, not a build of this branch.
The current v5 native client/helper candidates are installed on the owner's X11 host. They remain
development builds; their terminal wrapper, trial UI and read-only profile source are not the release
user experience. See [packaging](docs/packaging-plan.md) for the existing implementation.

## First local X11 release: agreed requirements

These are acceptance requirements, not claims of implemented behavior. The initial release targets the
tested X11 host with NVML fan/power control. Wayland, other machines and driver/host failure guarantees
remain outside the validated scope. Publication and push remain unauthorized.

- Deliver one `.deb` containing both the unprivileged desktop application and the privileged helper.
  Process/privilege separation, pinned GPU/desktop-user authorization, lease expiry, watchdog and
  post-stop recovery must survive the packaging consolidation.
- Ask for administrative authorization during installation/setup only. Normal application launch must
  open no terminal and request no password. Replace the interactive sudo session wrapper with a reviewed
  service lifecycle; changing the desktop entry alone does not satisfy this requirement. Do not grant
  blanket passwordless sudo or execute the GTK application as root. Preserve controller exclusion and
  recovery after client loss in the new lifecycle.
- Create private writable user configuration automatically, with the original curve editor available.
  Creation, editing, deletion, selection and persistence must work through the NVML integration. Reapply
  the selected custom curve at startup; explicit automatic mode and faults must not unexpectedly rearm it.
  The backup database is an explicit import source, not the permanent runtime database. Prepare and explain
  the import before touching the owner's profiles; preserve the source and recovery copies.
- Remove the development status band (including ordinary "Curve active" messages), trial-only notices,
  trial window titles and temporary control labels from the release UI. Keep actionable failures visible
  through ordinary dialogs/notifications and retain bounded diagnostic logs; do not silently hide loss of
  control or unverified recovery along with the band.
- Respect the existing minimize-to-tray preference on window close. Hiding the window must retain the
  application, active curve and service lease. Explicit Quit and closing with that preference disabled
  must perform verified release/cleanup. Test both window and tray actions.
- Remove the flashing behavior of controls during routine telemetry/lease renewal. Enable/disable controls
  only for meaningful user operations, capability changes or errors; retain necessary transition guards.
- Restore the original curve-editor button and icon instead of the temporary Restore action. Expose return
  to automatic through the normal fan-profile interaction and test that route; do not lose automatic
  recovery when returning the editor button to its original purpose.
- Audit other trial-only behavior, including fixed-duration runs, demo profiles, backup-path requirements,
  smoke flags, isolated test identity/settings and repeated notices. Keep test facilities in developer
  tools rather than the release launch path. Preserve deliberately unsupported control states (including
  overclock) rather than enabling them solely to match the historical appearance.
- Correct the bundled Peewee escape warnings with a reviewed compatibility change and regression checks;
  do not globally suppress Python warnings. Refresh the README, installation/upgrade/recovery guide,
  version metadata and release notes, and include artifact checksums.

Final acceptance must exercise the actual unified installed package and system Python, not the previous
user-local snapshot or a venv supplying omitted dependencies. Group automated checks and one installed
session check covering profile persistence/startup, editor interaction, tray close/show, explicit Quit,
automatic recovery and unchanged power unless explicitly applied. Retain earlier fault-injection evidence
and rerun affected lifecycle checks when replacing the launcher; do not repeat unrelated hardware trials.
An independently captured suspend/resume trace remains pending and must be described honestly.

## Current preparation phase

- Work on `maintenance/nvml-revival` and follow the [maintenance plan](docs/maintenance-plan.md).
- Keep upstream version history in `CHANGELOG.md`; do not claim a new application version for documentation preparation.
- Establish a reproducible environment, dependency set and build before providing new installation commands.
- Review `build.sh` before running it: it regenerates `CHANGELOG.md` from AppStream metadata and clears build output.
- Review the uninitialized `flatpak` submodule before fetching it. It targets the historical Flathub repository.
- Keep experimental builds separate from the installed application and its profiles.

## Before a public release

1. Choose the owner's hosting namespace, application ID and support/contact destinations. Honor upstream's
   request not to publish a continuation under `leinardi` or `com.leinardi.gwe`.
2. Update application metadata, desktop entries, schemas, build scripts and package manifests together.
   Provide an explicit settings/profile migration and rollback procedure before changing identifiers.
3. Validate the target Python/UI stack, the NVIDIA backend and the fan recovery scenarios in the plan.
4. Update the application version and AppStream release notes, then regenerate and review the changelog.
5. Record exact tested GPU, driver, operating system, session and package/runtime versions, including limitations.
6. Build and inspect artifacts locally. Publishing, pushing tags and contacting upstream services are separate
   actions for the owner to decide once hosting and release destinations exist.

The former upstream publishing checklist remains available in Git history. It is not the release procedure
for this continuation. In particular, do not uninstall the working Flatpak merely to test a development build.
