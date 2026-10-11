# Native packaging

## Package contents

One **gwe-nvml** `.deb` contains the unprivileged GTK desktop, reviewed pure-Python vendor modules,
public desktop/tray icons, the privileged helper and its systemd units. It runs with system Python.
System GTK, Matplotlib and other native dependencies are declared in the package. Drivers, kernels and
CUDA are not bundled or changed. Licenses and dependency-version notices accompany the vendor modules.

The build entry point is `scripts/build_debs.py`. It refuses changed dependency versions, missing
required licenses, existing destinations and unexpected symlinks. It does not install dependencies.
Use this native builder rather than alternate build/install scripts.

## Reviewed build inputs

Use a compatible Python environment containing the exact distributions listed in `VENDORS` in the
builder. Keep its distribution metadata and original licenses. To preserve those pure-Python inputs
independently of an interpreter environment:

```bash
/usr/bin/python3 scripts/stage_build_dependencies.py /path/to/reviewed/site-packages /path/to/new-build-inputs
```

The staging command reads an existing reviewed dependency set; it does not download or install packages.
It checks versions and paths and writes a `SHA256SUMS` manifest. Choose a new destination. A local
maintainer copy is preserved under `.local-backups/build-dependencies-py314/`; this is not a dependency
bundle shipped in source releases. Fresh builders must prepare their own reviewed inputs.

Set `GWE_BUILD_INPUTS` to the input directory. Verify its checksum manifest before use. Also provide
`dpkg-deb`, `glib-compile-resources` and `glib-compile-schemas` through the build environment:

```bash
export GWE_BUILD_INPUTS="$PWD/.local-backups/build-dependencies-py314"
(cd "$GWE_BUILD_INPUTS" && sha256sum --check SHA256SUMS)
PYTHONPATH="$GWE_BUILD_INPUTS" /usr/bin/python3 scripts/build_debs.py \
  build/new-candidate --version 1.0.0~rc1-9 --epoch 1791590400
```

Choose the version and fixed source epoch for the intended release. The command uses a new destination;
it does not clear old build output. The current target build interpreter is system Python 3.14.
The Peewee migration literal patch escapes two strings without changing their runtime regex values;
`BUNDLED_PATCHES` records that adjustment.

## Inspect and retain

Inspect control metadata and payload with `dpkg-deb --info` and `dpkg-deb --contents`. Check permissions,
licenses, declared dependencies, desktop/icon identity and compiled resources. Ensure that no database,
private configuration, UUID, screenshot or diagnostic log enters the package or source archive.

Test the extracted desktop with its packaged vendor modules and resources. Record the exact source
commit, package version/checksum, build interpreter, tests and remaining hardware gates in `BUILD_INFO`.
Create `SHA256SUMS` for the retained release assets. The builder creates a package checksum manifest;
keep it alongside the package and any additional release assets.

After validation, retain `.deb`, checksums and build records. Extraction trees, staged helpers and
synthetic test states may be removed; preserve diagnostic evidence separately when needed. Do not
replace published bytes under an existing version or tag. Publishing is covered by [RELEASING.md](../RELEASING.md).

## Install/update guarantees

The package configures authorization and socket activation during installation. Desktop launch needs no
sudo or terminal. Maintainer scripts refuse an active controller or pending recovery before replacement.
Authorization and private user configuration are preserved during updates/removal. Quit and finish
recovery before package operations; do not remove journals to bypass a guard.

The installed desktop identity is `io.github.alamios.gwe`. Public `hicolor` assets include native and
original artwork names for GTK/tray lookup. Original internal resource names retain attribution.
For ordinary use and rollback, see the [user guide](user-guide.md).
