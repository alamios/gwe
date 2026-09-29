# Preparing the Python 3.12 development GUI

The first graphical validation uses the current Ubuntu 24.04 system interpreter and native GTK3 libraries.
Python 3.14 remains the backend compatibility environment; do not expose Python 3.12 binary extension modules
to it. This preparation does not replace or update the installed GWE Flatpak.

## Prerequisites checked

The host provides Python 3.12, PyGObject, Pycairo, GTK3 and Notify. The dedicated Python 3.12 environment
currently cannot see the system GI/Cairo modules. Dazzle and AyatanaAppIndicator typelibs and
`glib-compile-resources` are missing. The following packages are available in the host's configured Ubuntu repositories:

```bash
sudo apt install gir1.2-dazzle-1.0 gir1.2-ayatanaappindicator3-0.1 libglib2.0-dev-bin
```

Dazzle is required by the historical graphs. Ayatana provides the optional tray indicator.
`libglib2.0-dev-bin` supplies the resource compiler for the bundled GTK UI files.

## Expose host GI and install Python dependencies

The owner should update the existing Python 3.12 environment using the host interpreter. Substitute its
actual path below; updating an existing venv this way preserves installed packages and enables host package visibility:

```bash
/usr/bin/python3 -m venv --system-site-packages /path/to/python312-env
/path/to/python312-env/bin/python -m pip install -r requirements-ui312.txt
```

Run the pip command from the repository root. Do not run the historical system-wide pip instructions.
The UI requirements include the diagnostic/repository test dependencies. They retain the inherited
matplotlib and peewee versions for the initial baseline and use NumPy 1.26.4 with matplotlib 3.8.2.
Requests has a bounded version range; record the resolved version after installation.
These are preparation requirements, not a claim of a completed reproducible GUI build or validation on 3.14.

System package visibility is intentional for GI/Cairo and means the environment is not fully isolated.
Validate imports and `pip check` after the owner installs the requirements. Do not install the old PyGObject pin
from `requirements.txt` over the distribution binding.

## Next validation

1. Check GTK3, Dazzle, Notify, Cairo and matplotlib GTK imports without creating the application.
2. Compile resources into an ignored local build directory and prepare a source launcher for monitor-only mode.
   The old Meson installation still references a missing vendored python-xlib directory; do not use its
   historical build/install commands as the development workflow without repair.
3. Run the test suite, then launch the isolated monitor with `GWE_MONITOR_ONLY=1` and verify visible telemetry.
4. Confirm the monitoring instance uses its separate configuration/application ID and exits without GPU writes.

The existing GWE may stay running while preparing dependencies. Only the monitor instance will be launched
for graphical checks; future fan-control testing requires a separate procedure with one active controller.
