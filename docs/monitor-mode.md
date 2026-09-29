# Development monitor-only integration

Set `GWE_MONITOR_ONLY=1` before starting a development build to select NVML telemetry in the existing UI.
This is an opt-in integration, not a switch of the installed Flatpak or the default legacy controller.
The complete GTK development environment/build is still pending validation; do not treat the commands below
as an installation guide for the existing Flatpak.

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

In a prepared source build environment, preserve the usual built-resource launcher and prefix its command
with `GWE_MONITOR_ONLY=1`. Do not launch the development GUI until GTK dependencies/resources are validated.
Do not run `python -m gwe` as an assumed harmless import check: it starts the full application.

For tests of repository routing and blocked writes, the owner installs `requirements-monitor-tests.txt`
into the isolated development environments, then runs:

```bash
python -m pytest -q
```

The lightweight tests in `test_nvml_monitor.py` and `test_runtime_mode.py` require only the diagnostic
requirements. Tests in `test_monitor_repository.py` additionally require the existing DI, Rx and Xlib/NVML
packages listed in `requirements-monitor-tests.txt`; they do not import GTK or access hardware.

## Current evidence

All 41 tests pass on Python 3.12.3 and 3.14.6, including repository write rejection, cleanup as a no-op,
NVML startup routing and preservation of the default X11 gate. Both environments pass pip check.
Live repository/interactor reads also passed with display variables removed, returning the RTX 3090 Ti
and its two fans. No development GUI has been launched and no GPU control operation has been performed.
Visible UI behavior is not yet confirmed. The system exposes GTK3, but Dazzle and AyatanaAppIndicator3
typelibs are missing; full application dependencies and build resources still need preparation.
Reactivex 4.0.4 emits a datetime deprecation warning in both interpreters; it does not fail these tests. The installed GWE can remain open
for read-only diagnostics; a future control test requires ensuring only one controller owns the fans.

See [configuration backup](configuration-backup.md) before any future profile migration or control test.
