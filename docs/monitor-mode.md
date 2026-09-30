# Development monitor-only integration

Set `GWE_MONITOR_ONLY=1` before starting a development build to select NVML telemetry in the existing UI.
This is an opt-in integration, not a switch of the installed Flatpak or the default legacy controller.
The Python 3.12 source monitor has passed a live smoke check on the current X11 desktop. These instructions
do not update or install the existing Flatpak. See [GUI development](gui-development.md) for the source launcher.

## Behavior

- The startup check skips NV-CONTROL and checks NVML in this mode.
- The repository maps temperature, memory, utilization, power draw and fan percentages to existing UI models.
- The first successfully identified GPU is selected by UUID for the session. Device loss clears readings;
  a replacement GPU at the old index is not selected automatically.
- Fan, overclock and power-limit writes are rejected by the repository. Exit cleanup does not reset fans.
- UI controls for these operations are disabled. Unimplemented values (including fan RPM and clocks) remain
  blank. Historical graphs skip missing fan readings rather than converting None to a number.
- Settings use `$XDG_CONFIG_HOME/gwe-monitor/`, keeping the installed profiles separate. GTK uses a distinct
  application ID ending in `.Monitor`, avoiding activation of the installed instance through D-Bus.
- With the variable absent, the historical X11 control path and configuration namespace remain selected.

The mode does not import or migrate the installed profiles and is read-only with respect to GPU settings;
it still creates/updates its own application preferences/database. NVML metadata is read without X11.
A graphical session is still necessary to display GTK windows.

## Validation commands

Use `python scripts/run_monitor.py` from the repository root in the prepared Python 3.12 environment.
The launcher forces monitor mode and local configuration before importing the application. Add `--smoke-test`
for an automatic ten-second check and shutdown. It compiles resources locally without invoking the legacy installer.

For tests of repository routing and blocked writes, the owner installs `requirements-monitor-tests.txt`
into the isolated development environments, then runs:

```bash
python -m pytest -q
```

The lightweight tests in `test_nvml_monitor.py` and `test_runtime_mode.py` require only the diagnostic
requirements. Tests in `test_monitor_repository.py` additionally require the existing DI, Rx and Xlib/NVML
packages listed in `requirements-monitor-tests.txt`; they do not import GTK or access hardware.

## Current evidence

All 42 simulated tests pass on both Python versions. Live repository reads and the Python 3.12 GTK smoke check
pass on the current X11 desktop. The window received GPU telemetry and all three GPU control sections were
disabled; it then exited normally. No GPU control operation was performed. Python 3.14 GUI, Wayland and 26.04
remain untested. See [GUI validation](gui-development.md) for dependencies, warnings and limitations.

The installed GWE may remain open alongside the monitor. Future control testing requires a separate procedure
with only one fan controller. See [configuration backup](configuration-backup.md) before profile migration.
