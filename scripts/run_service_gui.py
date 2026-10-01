#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run the main GWE window with isolated state and explicit bounded fan-service control."""
import argparse
import os
from pathlib import Path
import sys
import tempfile
import threading
import time

from run_monitor import prepare_environment, prepare_resources

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--database', type=Path, help='Explicit backup opened read-only')
    source.add_argument('--demo', action='store_true', help='Use a synthetic curve; telemetry still uses read-only NVML')
    parser.add_argument('--allow-control', action='store_true', help='Enable explicit ten-second service trials')
    checks = parser.add_mutually_exclusive_group()
    checks.add_argument('--smoke-test', action='store_true', help='Check the real main window in preview mode')
    checks.add_argument('--smoke-service', action='store_true', help='Exercise main-window buttons with a simulated service')
    args = parser.parse_args(argv)
    if args.allow_control and (args.demo or args.smoke_test or args.smoke_service):
        parser.error('Real control cannot be combined with demo or smoke checks')
    if args.smoke_service and not args.demo:
        parser.error('Simulated service smoke test requires --demo')

    build = prepare_environment(ROOT, 'service-gui')
    os.environ['GWE_SERVICE_TRIAL'] = '1'
    from gwe.fan_curve import FanCurve
    from gwe.fan_profiles import SavedFanProfile, read_profiles, manual_limits
    from gwe.fan_gui_session import FanGuiSession
    from gwe.fan_gui_log import FanGuiLog
    from gwe.fan_main_controller import FanMainController, configure_factory
    try:
        profiles = (SavedFanProfile(1, 'Synthetic trial', FanCurve(((0, 40), (50, 40), (80, 100))), None),) if args.demo else read_profiles(args.database)
        limits = (30, 100) if args.demo else manual_limits()
        log = FanGuiLog(build / 'logs' / 'trial.log')
        log.record('control_window_opened' if args.allow_control or args.smoke_service else 'preview_opened')
        resource_path = prepare_resources(ROOT, build)
    except Exception as error:
        print(f'Main-window trial setup failed: {type(error).__name__}; no GPU settings changed.', flush=True)
        return 1

    endpoint = '/run/gwe-fan-service/control.sock'
    stop = threading.Event()
    worker = service = temporary = backend = None
    if args.smoke_service:
        from gwe.fan_service import FanService
        class SimulatedBackend:
            starts = 0
            stops = 0
            def start(self, curve):
                self.starts += 1
            def stop(self):
                self.stops += 1
        backend = SimulatedBackend()
        temporary = tempfile.TemporaryDirectory(prefix='gwe-service-gui-')
        endpoint = str(Path(temporary.name) / 'control.sock')
        service = FanService(endpoint, backend, allowed_uid=os.geteuid())
        def serve():
            while not stop.is_set():
                service.step(.01)
        worker = threading.Thread(target=serve, daemon=True)
        worker.start()
    session = FanGuiSession(endpoint, event_sink=log.record)
    configure_factory(lambda view: FanMainController(
        view, profiles, limits, session, allow_control=args.allow_control or args.smoke_service))

    import gi
    for namespace, version in (('Gtk', '3.0'), ('Gdk', '3.0'), ('Dazzle', '1.0'), ('Notify', '0.7')):
        gi.require_version(namespace, version)
    from gi.repository import Gio, GLib, Gtk
    Gtk.IconTheme.get_default().append_search_path(str(ROOT / 'data' / 'icons' / 'hicolor'))
    resource = Gio.Resource.load(str(resource_path))
    resource._register()
    from gwe import __main__ as entry
    passed, phase = [], [0]
    deadline = time.monotonic() + 30
    if args.smoke_test or args.smoke_service:
        def check():
            app = entry.INJECTOR.get(entry.Application)
            presenter, view = app._presenter, app._view
            controller = presenter._service_controller
            def finish(valid):
                passed.append(valid)
                print('Main-window service smoke test:', 'PASS' if valid else 'FAIL', flush=True)
                app.quit()
                return GLib.SOURCE_REMOVE
            if time.monotonic() >= deadline or session.state == 'fault':
                return finish(False)
            if controller is None or not controller.telemetry_available:
                return GLib.SOURCE_CONTINUE
            if (view._overclock_frame.get_sensitive() or view._power_limit_apply_button.get_sensitive()
                    or not presenter._latest_status.read_only):
                return finish(False)
            if phase[0] == 0:
                if session.client is not None or session.state != 'idle' or presenter._fan_profile_applied is not None:
                    return finish(False)
                selected_index = next((index for index, profile in enumerate(profiles)
                                       if profile.curve is not None), 0)
                view._fan_combobox.set_active(selected_index)
                if args.smoke_test:
                    return finish(not view._fan_apply_button.get_sensitive()
                                  and not view._fan_edit_button.get_sensitive()
                                  and controller.selected is not None)
                if not view._fan_apply_button.get_sensitive():
                    return finish(False)
                view._fan_apply_button.clicked()
                phase[0] = 1
            elif phase[0] == 1 and session.state == 'active' and controller.pending is None:
                if not view._fan_edit_button.get_sensitive():
                    return finish(False)
                view._fan_edit_button.clicked()  # Existing Edit signal now releases this service lease.
                phase[0] = 2
            elif phase[0] == 2 and session.state == 'idle' and controller.pending is None:
                if not backend.stops or 'recovery verified' not in session.message:
                    return finish(False)
                view._fan_apply_button.clicked()
                phase[0] = 3
            elif phase[0] == 3 and session.state == 'active' and controller.pending is None:
                phase[0] = 4
            elif phase[0] == 4 and session.state == 'idle' and controller.pending is None:
                if backend.stops != 2 or 'recovery verified' not in session.message:
                    return finish(False)
                view._fan_apply_button.clicked()  # Third trial checks closing with an active lease.
                phase[0] = 5
            elif phase[0] == 5 and session.state == 'active' and controller.pending is None:
                phase[0] = 6
                view._window.close()  # Exercises real delete-event, not tray minimization.
                return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE
        GLib.timeout_add(100, check)

    sys.argv = ['gwe-service-trial']
    result = 1
    try:
        try:
            entry.main()
        except SystemExit as error:
            result = error.code
        if args.smoke_service and phase[0] == 6:
            controller = entry.INJECTOR.get(entry.Application)._presenter._service_controller
            passed.append(controller.closed and session.client is None)
            print('Main-window service smoke test:', 'PASS' if passed[-1] else 'FAIL', flush=True)
    finally:
        session.close()
        if service is not None:
            # Let the simulated server process socket EOF before checking window-close recovery.
            expires = time.monotonic() + 2
            while backend.stops < 3 and time.monotonic() < expires:
                time.sleep(.01)
            stop.set()
            worker.join(2)
            service.close()
            temporary.cleanup()
    if args.smoke_test or args.smoke_service:
        return 0 if passed == [True] and (backend is None or backend.starts == backend.stops == 3) else 1
    return result


if __name__ == '__main__':
    raise SystemExit(main())
