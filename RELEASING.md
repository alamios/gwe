# Preparing and publishing fork releases

This independent fork is maintained by **alamios** with AI assistance at
**https://github.com/alamios/gwe**. Original authors, credits, history and GPL-3.0-or-later licensing
are retained. Source and native `.deb` assets are intended for GitHub Releases; no push or publication
has occurred during local preparation. This fork has no Flatpak or PyPI distribution.

## Accepted X11 candidate

**1.0.0-rc1**, Debian revision **1.0.0~rc1-5**, is ready for owner publication as a **prerelease**.
On 2026-10-04 the owner completed the installed unified-package check with system Python:

- Saved-curve startup, original editor, tray hide/show retaining ownership and explicit Quit passed.
- Service SIGKILL and SIGSTOP/watchdog recovery passed while the saved curve controlled the fans.
- Independent checks verified automatic fans, unchanged power, restored CoolerControl and an available
  activation socket after every session. Read-only inspection confirms installed rc1-5, clean package
  integrity, service inactive/success and socket active.

The fault sessions also printed `Startup control check: FAIL` from the deliberately interrupted child
application. Those messages describe normal-completion checks, not failed recovery; the external verifier
passed. The development harness now launches ordinary sessions during fault injection to avoid that
misleading message. No packaged application/helper behavior changed after installed acceptance.

The most recent full simulated suites passed 573 tests on Python 3.12 and 563 backend/package tests on
Python 3.14. Ten HTTP update tests were excluded on 3.14 for its documented missing requests dependency;
they passed on 3.12 and requests is a native package dependency. The subsequent nonblocking-notice change
passed 74 focused tests and the expanded extracted-package GTK check with system Python: a notice stayed
open for ten seconds while simulated leases renewed, and Quit completed with it still open.
Reactivex's datetime warning remains non-fatal.

Hardware evidence targets RTX 3090 Ti, NVIDIA 580.178.04, Ubuntu/Kubuntu 24.04.5 and KDE/X11.
**Kubuntu 26.04, Wayland, other hardware and driver/host failure guarantees remain unvalidated.**
An independently recorded suspend/resume trace remains pending. Clock-offset control is unsupported.
The original rc1-3 hang cause remains unconfirmed; rc1-5 fixes a synchronous-dialog control-loop hazard.
The hang itself was recovered by terminating only the GUI, preserving the observed 340 W and automatic
fans, and restoring CoolerControl. The installed rc1-5 recovery tests above supersede earlier pending
acceptance statements. See [native desktop](docs/native-desktop.md) and [migration readiness](docs/migration-readiness.md).

## Branches and artifacts

Develop on `main`. The maintenance phase is merged without squash; the annotated `upstream-baseline`
tag preserves the inherited original commit. Existing upstream tags and historical branches remain.
Fork releases use annotated tags such as `v1.0.0-rc1`, not a separate release branch.

The final publication assets are in **build/publish-v1.0.0-rc1/**:

- `gwe-nvml_1.0.0~rc1-5_all.deb`: exact bytes of the installed, accepted package built at `db50975`.
- `gwe-1.0.0-rc1-source.tar.gz`: source from the final annotated version tag.
- `BUILD_INFO`: separate package-build and tagged-source commits, validation and limitations.
- `SHA256SUMS`: checksums for the three assets above.

Later commits contain documentation and developer fault-harness changes only; packaged runtime sources
are unchanged. Earlier package snapshots and diagnostic evidence were moved to a private, checksummed
Git-ignored `.local-backups/` archive before cleanup. `build/` now retains only the publication folder;
generated review trees, smoke states and synthetic media were removed. Keep rollback assets privately
and never replace a published artifact with different bytes under the same version/name. Private databases, UUIDs, screenshots and logs are
excluded from publication assets. The release notes are in [the prepared notes](docs/release-notes-1.0.0-rc1.md).

The native package installs through `sudo apt install ./gwe-nvml_1.0.0~rc1-5_all.deb`. Its maintainer
scripts configure authorization and socket activation. Ordinary launch is terminal-free and unprivileged;
no repository installer, development venv or hardware trial is required for normal users.

## Future release checklist

1. Update application version, AppStream, changelog and public metadata together. Preserve original
   credits/license and disclose AI maintenance. Use the fork's source, support and changelog links.
2. Preserve configuration/import backups and document any schema/identity migration plus rollback.
3. Run relevant simulated/backend/UI checks. Rerun affected installed lifecycle tests for runtime changes;
   do not substitute older launcher tests or venv dependencies for actual installed-package acceptance.
4. Build into a new directory with the reviewed Python modules and fixed epoch. Inspect package/source
   contents, permissions, licenses, dependencies and checksums. Keep driver/kernel/CUDA changes separate.
5. Record the exact tested target and remaining limits. Tag only the reviewed commit after its gate passes.
6. Publish only when the owner authorizes it. Follow [the GitHub source/binary release guide](docs/github-releases.md),
   select the existing tag, attach the four assets and mark candidates as prereleases.

Inspect build scripts before use. The historical `build.sh` regenerates the changelog and clears build
output; it is not this fork's package builder. The uninitialized Flatpak submodule is historical upstream
packaging and must not be fetched or installed as part of native release preparation.
