# Local builds and future releases

The chosen home for this fork is **https://github.com/alamios/gwe**, maintained by **alamios** from the
1.0.0 onward. Source code and `.deb` artifacts will be distributed through that repository and its
GitHub Releases. This records the destination; no publication or push is authorized by this planning step.
The installed Flathub application is the historical upstream build, not a build of this branch.
The current v5 native client/helper candidates are installed on the owner's X11 host. They remain
development builds; their terminal wrapper, trial UI and read-only profile source are not the release
user experience. See [packaging](docs/packaging-plan.md) for the existing implementation.

The first candidate is **1.0.0-rc1**, followed by **1.0.0** after release acceptance.
Original upstream 0.x version history and attribution are preserved.

Preparation progress: the native builder now emits one `gwe-nvml` package by default. The split-to-combined
transition and rollback pass in an isolated dpkg root; host transition and the remaining requirements below
are pending. Historical split builds remain available with `--split` for recovery validation.

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

## Attribution, public text and links: agreed requirements

Complete this audit before the 1.0.0 release; current development UI/metadata still contain upstream links.

- Identify the project as a fork of [Roberto Leinardi's original GWE](https://gitlab.com/leinardi/gwe).
  Preserve original authors, contributor credits, copyright and GPL license notices. Add alamios as the
  fork maintainer beginning with 1.0.0; do not imply original authors maintain or endorse this continuation.
- Clearly disclose in the README and relevant project documentation that this fork is maintained with
  AI assistance, including implementation, testing and documentation. Do not present the work as wholly
  human-written or claim that AI assistance is a substitute for the recorded validation.
- Briefly describe the change to NVML monitoring and fan/power control. Distinguish X11 validation from
  future Wayland support and do not imply overclock support has been ported.
- Use https://github.com/alamios/gwe as the project website/source link and
  https://github.com/alamios/gwe/releases for release downloads. Update issue/support links to this fork;
  do not send its bug reports or maintenance requests to the original author. Do not invent a maintainer
  email address where none has been supplied.
- Make the in-application changelog link target CHANGELOG.md in the new repository, using an actual
  published release tag (or the correct development ref). Review the existing version-derived link logic
  rather than merely replacing the hostname. Keep original changelog history and add fork release notes.
- Update About to retain the original creators and explicitly state that, from version 1.0.0, this is an
  independent fork maintained by alamios. Set the website to the new repository and retain licensing and
  attribution. Review both runtime overrides and the Glade defaults.
- Remove obsolete Flatpak/Flathub installation, update and distribution claims from the current README,
  user-facing help and release instructions. This fork initially ships source and `.deb` GitHub Releases
  only. Keep necessary historical/provenance and backup/rollback references clearly labeled as such;
  their removal must not erase the origin of saved profiles or break recovery documentation. Flatpak
  publication may be considered later and is not a release requirement.
- Audit badges, screenshots, AppStream homepage/bugtracker/contact fields, desktop metadata, package
  maintainer fields, update checking, contribution instructions and release automation for obsolete
  upstream destinations. Do not rename application/settings identities without the separately required
  settings migration and rollback procedure.

Known implementation locations include `gwe/conf.py`, `gwe/view/main_view.py`,
`gwe/presenter/main_presenter.py` (changelog), `data/ui/main.glade`,
`data/com.leinardi.gwe.appdata.xml` and `scripts/build_debs.py`. These are audit starting points,
not permission to perform a blind replacement of upstream author/license references.

## Current preparation phase

- Work on `maintenance/nvml-revival` and follow the [maintenance plan](docs/maintenance-plan.md).
- Keep upstream version history in `CHANGELOG.md`; do not claim a new application version for documentation preparation.
- Establish a reproducible environment, dependency set and build before providing new installation commands.
- Review `build.sh` before running it: it regenerates `CHANGELOG.md` from AppStream metadata and clears build output.
- Review the uninitialized `flatpak` submodule before fetching it. It targets the historical Flathub repository.
- Keep experimental builds separate from the installed application and its profiles.

## Before a public release

1. Use the chosen `alamios/gwe` hosting namespace; finalize the application ID and support/contact metadata.
   Honor upstream's request not to publish a continuation under `leinardi` or `com.leinardi.gwe`.
2. Update application metadata, desktop entries, schemas, build scripts and package manifests together.
   Provide an explicit settings/profile migration and rollback procedure before changing identifiers.
3. Validate the target Python/UI stack, the NVIDIA backend and the fan recovery scenarios in the plan.
4. Update the application version and AppStream release notes, then regenerate and review the changelog.
5. Record exact tested GPU, driver, operating system, session and package/runtime versions, including limitations.
6. Build and inspect artifacts locally. Publishing, pushing tags and contacting upstream services are separate
   actions for the owner to decide once hosting and release destinations exist.

The former upstream publishing checklist remains available in Git history. It is not the release procedure
for this continuation. In particular, do not uninstall the working Flatpak merely to test a development build.
