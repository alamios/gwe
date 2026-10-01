# Manual continuous control session

Implemented and prepared on 2026-10-02. This is an experimental session for the current host, not a
production/background service or Wayland acceptance. The installed Flatpak and personal database are
not replaced. The service's conservative 60 C fan-control ceiling is retained: reaching that ceiling
stops manual control and attempts automatic recovery. Initial use must remain under light load.

## Start and stop

Close installed GWE and other development windows first. From the repository, using the prepared
Python 3.12 interpreter and explicit read-only backup:

```bash
bash scripts/run_control_session.sh /path/to/prepared/python3.12 "$BACKUP_DB" build/session-service-v1
```

This one command checks inactive/failed service state, completes any outstanding recovery, resets the
expected failed state from fault tests and installs the reviewed bundle. An existing rollback copy is
retained under `/opt/gwe-fan-service.previous.<UTC timestamp>`; the updater creates another rollback
copy of the installation it replaces. Existing configuration is preserved. No packages are changed.

The wrapper temporarily stops CoolerControl and installs the bundle's root-owned runtime systemd
override. The override selects `run --continuous` and removes the 60-second lifetime; the watchdog,
process supervision and independent ExecStopPost recovery remain enabled. No boot enablement occurs.
The application opens with isolated settings, explicit backup access and no selected/applied curve.
Select a compatible curve and press **Apply selected curve**. **Restore automatic** releases it.
Closing the application ends the session, stops/recovers the service, removes the runtime override
and restores CoolerControl's original active state only after recovery succeeds. Keep the launching
terminal open. Normal verified power changes remain committed on close, as documented in
[power control](power-control.md); this session does not install the special 250 W acceptance guard.

After the first successful update, subsequent sessions can reuse the installation without another update:

```bash
bash scripts/run_control_session.sh /path/to/prepared/python3.12 "$BACKUP_DB" --installed
```

## Recovery and limitations

The GUI renews the same five-second service lease once per second; continuous mode removes only the
ten-second GUI deadline. Lost/stale telemetry, a stale UI heartbeat, socket loss, explicit release and
application exit still initiate recovery. A service/worker failure cannot rely solely on GUI cleanup;
the existing watchdog and independent post-stop recovery remain in place. Startup never imports,
migrates or applies a saved profile. Faults never automatically reacquire a curve.

If the terminal/wrapper itself is killed with SIGKILL, its EXIT trap cannot run. GUI connection loss still
expires fan ownership, but CoolerControl may remain stopped and the runtime override may remain.
The launcher refuses an existing override rather than silently replacing it. Stop the experimental unit,
run its installed recovery action, review pending records and remove the runtime override before
restoring CoolerControl. A restart of the host clears the runtime override, but is not a substitute for
verifying GPU recovery while the host is running.

Suspend/resume, extended real operation, driver/host failures and target-OS/Wayland remain unvalidated.
The 60 C ceiling deliberately prevents claiming unrestricted daily/gaming use at this stage.

## Automated validation

The full suite passed with 435 tests on each interpreter, followed by an additional passing cleanup
failure test on each interpreter. Coverage includes simulated three-minute GUI renewal, stale heartbeat
disconnect, continuous daemon operation beyond its historical lifetime, backend faults, preserving older
rollback copies, source/installed launch modes and cleanup after GUI or recovery failures. The Python
3.12 GTK simulated-service check held an active curve beyond ten seconds, explicitly restored it and
closed during a subsequent active lease. All native GPU access during that GTK check was read-only.
The bundle is staged privately at `build/session-service-v1`; it has not been installed or run continuously
on hardware yet. Existing Reactivex datetime deprecation warnings remain non-fatal.
