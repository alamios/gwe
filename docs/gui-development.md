# Preparing the Python 3.12 development GUI

The first graphical validation uses the current Ubuntu 24.04 system interpreter and native GTK3 libraries.
Python 3.14 remains the backend compatibility environment; do not expose Python 3.12 binary extension modules
to it. This preparation does not replace or update the installed GWE Flatpak.

## Native prerequisites

The host provides Python 3.12, PyGObject, Pycairo, GTK3 and Notify. The owner has also installed Dazzle,
AyatanaAppIndicator and the resource compiler, and enabled system package visibility in the Python 3.12
environment. For an equivalent Ubuntu 24.04 setup, the additional native packages are:

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

## Run the isolated source monitor

From the repository root in the prepared Python 3.12 environment:

```bash
python scripts/run_monitor.py
```

The launcher compiles resources and schemas under `build/monitor/`, forces `GWE_MONITOR_ONLY=1` before
application imports and redirects XDG configuration, data and cache into that ignored build directory.
Application settings are therefore in `build/monitor/config/gwe-monitor/`. No system installation, Flatpak
replacement or original profile migration is performed. The legacy build scripts are not invoked.
The distinct `.Monitor` application ID keeps the installed GWE instance separate.

For a ten-second live check that exits automatically:

```bash
python scripts/run_monitor.py --smoke-test
```

The check requires real GPU name/temperature telemetry and disabled fan, overclock and power controls.
It returns nonzero on failure. Close any previous development monitor before running the check so D-Bus
activation does not redirect it to that instance; the installed GWE can remain open.

## Validation results

- GTK3, Gdk, Dazzle, Notify, Ayatana, Cairo and matplotlib GTK imports succeeded.
- Resolved UI packages include matplotlib 3.8.2, peewee 3.17.0 and requests 2.34.2.
- The initial GUI launch exposed an outdated SpeedStep import, now corrected. GLib option argument assignment
  now uses an integer to avoid the observed introspection warning.
- The live smoke check passed on the current X11 desktop, including telemetry, disabled controls and shutdown.
- All 42 simulated tests pass on Python 3.12.3 and 3.14.6. The latter has not run the GUI.
- With system packages visible, Python 3.12 pip check reports inherited liquidctl 0.0.0 missing smbus.
  This is unrelated to GWE; no liquidctl or system dependency was changed. The earlier clean pip check
  results applied to the environment before enabling system package visibility.
- Reactivex still emits a datetime deprecation warning during tests.

This is a focused live startup check, not a full visual or interaction audit. Wayland, Kubuntu 26.04,
profile migration and all GPU control writes remain unvalidated. The installed GWE was not stopped.

## Separate fan-profile review window

The [isolated GTK service-client preparation](fan-gui.md) uses only GTK3 and the existing service protocol.
Its synthetic and private-backup read-only preview smoke checks passed on Python 3.12/X11. It creates no
application database and does not replace the monitor launcher or historical main window. Explicit
GUI-to-service control succeeded on its second hardware attempt; the first failure remains unexplained.
Wayland remains untested; see the bounded procedure and result record in that guide.

The owner subsequently accepted two consecutive successful bounded GUI trials provisionally. Future
GUI launches retain private, bounded diagnostics under `build/fan-gui/`; see [log retention](fan-gui.md).
This does not establish continuous fan control or integration into the historical main window.

## Main-window service integration

The [new opt-in main-window launcher](main-window-service.md) passed Python 3.12/X11 read-only preview
with a private backup and simulated-service control via the actual buttons. Explicit release, automatic
ten-second completion and close during ownership were checked. The original monitor smoke test still
passes. No GPU writes occurred in these checks; main-window hardware control and Wayland remain pending.
