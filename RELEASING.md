# Local builds and future releases

This maintenance continuation has no published release or chosen public hosting namespace yet.
The installed Flathub application is the historical upstream build, not a build of this branch.
See the [NVML packaging architecture](docs/packaging-plan.md) for the proposed separate desktop client
and native host helper. The current local snapshot is not a standalone binary, `.deb` or new Flatpak.
Separate local `.deb` candidates can now be generated with `scripts/build_debs.py`; they are test
artifacts, not an installed or published release. Review helper migration and native dependencies first.

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
