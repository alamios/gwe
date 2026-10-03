# Source and binary releases on GitHub

The fork develops on `main`. The annotated `upstream-baseline` tag preserves the inherited original
commit; the maintenance branch is merged without squash. Existing upstream tags and historical branches
are retained, but are not new fork releases. A separate `release` branch is not needed.

## Accepted candidate

The first fork version is `1.0.0-rc1`, targeting the tested KDE/X11 host. Before tagging or publishing,
record installed startup/editor/tray/Quit and SIGKILL/watchdog recovery using the unified package:

```bash
/usr/bin/python3 scripts/check_native_recovery.py
```

Run as the desktop user after **Quit**, with the GPU idle and cool. The command authenticates sudo for
two service faults, keeps GTK unprivileged, restores automatic fans and verifies the current power
unchanged. It does not apply a power limit or clock offset. Do not substitute the old power trial,
which uses a historical 250 W baseline. If recovery is not verified, stop and inspect the service.

The owner completed the installed rc1-5 gate on 2026-10-04: startup/editor/tray/Quit, SIGKILL and
SIGSTOP/watchdog recovery all passed. Independent checks verified automatic fans, unchanged power,
restored CoolerControl and an available socket. Package inspection confirms rc1-5 and unchanged payload.
The child normal-startup checks printed FAIL when deliberately interrupted; those were not failures of
the independent recovery checks. The developer harness now uses ordinary sessions for fault injection.

Wayland/Kubuntu 26.04, other GPUs and driver/host failure guarantees remain outside validated scope.
The exact original rc1-3 hang cause is unconfirmed; rc1-5 contains the tested nonblocking-notice fix.
The local annotated `v1.0.0-rc1` tag and publication assets are prepared; no push or publication occurred.

## Generate local assets

Use the reviewed Python 3.12 build environment described in [packaging](packaging-plan.md).
The `.deb` contains GTK application source, reviewed Python modules and a privileged helper; it is the
installable binary distribution. GitHub does not generate this package automatically from a tag.
Use a fresh directory and a monotonically increasing Debian revision, preserving earlier artifacts:

```bash
python scripts/build_debs.py build/release-rc1-5 --version 1.0.0~rc1-5 --epoch 1790985600
```

The prepared assets are in `build/publish-v1.0.0-rc1/`. The `.deb` is copied byte-for-byte from the
installed, accepted rc1-5 artifact, originally built in `build/release-rc1-5` at `db50975`. It is deliberately not rebuilt
after acceptance. The source archive uses the final `v1.0.0-rc1` tag; subsequent changes are documentation
and the developer fault harness only, with no changes to packaged application/helper code. `BUILD_INFO`
records both commits; `SHA256SUMS` checksums the package, archive and build information. Upload only those four files; review trees and service bundles are local
inspection material. Never attach personal configuration, databases, screenshots or diagnostic logs.
Inspect the archive/package contents and verify checksums before upload. Publication should use the
exact tested package; source-only documentation changes must be recorded separately from its build.

## Build-directory cleanup

After owner-authorized cleanup, `build/` contains only `publish-v1.0.0-rc1/`. Prior package/source
snapshots, manifests and diagnostic logs were archived privately under Git-ignored `.local-backups/`,
with verified checksums, before removing generated review trees, smoke states and synthetic videos.
The four publication files and annotated version tag were preserved unchanged. Build commands above
are for generating a new review directory; they are not needed to publish the accepted assets.

## Publish manually (owner action)

Preparation does not authorize a push or publication. Once acceptance passes and the owner chooses to
publish, push `main` and the specific fork version tag to `alamios/gwe`. Avoid `git push --tags`, which
would also publish every inherited upstream tag. Push `upstream-baseline` explicitly if desired.
Once the local version tag exists, the owner can push explicitly:

```bash
git push -u origin main
git push origin v1.0.0-rc1 upstream-baseline
```

These commands publish repository history/tags; they have not been run during preparation.
Create the empty `alamios/gwe` GitHub repository first if needed (without an initial README/license).
Set `main` as its default branch.

1. Open **Releases → Draft a new release** in `alamios/gwe`.
2. Select the existing `v1.0.0-rc1` tag and title the release `GreenWithEnvy 1.0.0-rc1`.
3. Paste the reviewed release notes and select **Set as a pre-release**.
4. Attach the `.deb`, source archive, `BUILD_INFO` and `SHA256SUMS`.
5. Save a draft, inspect its assets/notes, then publish when approved.

GitHub also provides source ZIP/tar archives for the tag. Those are source downloads, not `.deb`
installers. Follow [GitHub's release guide](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository).

Users download the `.deb`, verify it against `SHA256SUMS`, quit other controllers and install normally:

```bash
sudo apt install ./gwe-nvml_1.0.0~rc1-5_all.deb
```

No development venv or repository installation wrapper is required. For future releases, change the
application version, AppStream and changelog together, run appropriate checks, build new assets and
create a new tag. Never replace a published package with different bytes under the same name/version.
