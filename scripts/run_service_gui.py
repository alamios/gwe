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
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--database', type=Path, help='Explicit backup opened read-only')
    source.add_argument('--demo', action='store_true', help='Use a synthetic curve; telemetry still uses read-only NVML')
    parser.add_argument('--native', action='store_true', help='Use private writable configuration and the standard desktop controls')
    parser.add_argument('--hide-window', action='store_true', help='Start minimized to the system tray')
    parser.add_argument('--delay', action='store_true', help='Delay startup briefly for desktop login')
    parser.add_argument('--allow-control', action='store_true', help='Enable explicit ten-second service trials')
    parser.add_argument('--allow-power-control', action='store_true', help='Enable explicit service power-limit Apply')
    parser.add_argument('--continuous', action='store_true', help='Keep an explicitly applied curve until release/close')
    parser.add_argument('--startup-profile', help='Apply one named saved curve once after fresh startup telemetry')
    checks = parser.add_mutually_exclusive_group()
    checks.add_argument('--smoke-test', action='store_true', help='Check the real main window in preview mode')
    checks.add_argument('--smoke-service', action='store_true', help='Exercise main-window buttons with a simulated service')
    checks.add_argument('--smoke-power', action='store_true', help='Exercise power Apply with a simulated service only')
    checks.add_argument('--smoke-combined', action='store_true', help='Exercise power during a simulated continuous curve')
    checks.add_argument('--smoke-startup', action='store_true', help='Check automatic startup and explicit release with simulated control')
    checks.add_argument('--smoke-native', action='store_true', help='Check writable curves, editor, tray and automatic mode with simulated control')
    checks.add_argument('--check-startup', action='store_true', help='Verify real startup control briefly and close; requires the supervised wrapper')
    args = parser.parse_args(argv)
    if args.smoke_native:
        args.native = args.demo = args.continuous = True
    if args.native:
        if args.database or (args.demo and not args.smoke_native):
            parser.error('--native creates/uses its own database')
        os.environ['GWE_NATIVE_DESKTOP'] = '1'
    elif not (args.database or args.demo):
        parser.error('Provide --database, --demo or --native')
    if args.smoke_startup:
        args.continuous = True
    startup_profile = args.startup_profile
    if startup_profile is None and args.allow_control and args.continuous:
        startup_profile = os.environ.get('GWE_STARTUP_PROFILE')
    if args.smoke_startup:
        startup_profile = 'Synthetic trial'
    if args.smoke_native:
        startup_profile = 'Native synthetic'
    if startup_profile is not None and not ((args.allow_control or args.smoke_startup or args.smoke_native) and args.continuous):
        parser.error('--startup-profile requires --allow-control and --continuous')
    if args.check_startup and not (args.allow_control and args.continuous and (startup_profile or args.native)):
        parser.error('--check-startup requires a configured startup curve and continuous control')
    if args.smoke_combined:
        args.continuous = True
    if args.continuous and not (args.allow_control or args.smoke_service or args.smoke_combined or args.smoke_startup or args.smoke_native):
        parser.error('--continuous requires --allow-control or a simulated continuous check')
    if (args.allow_control or args.allow_power_control) and (args.demo or args.smoke_test or args.smoke_service or args.smoke_power or args.smoke_combined or args.smoke_startup):
        parser.error('Real control cannot be combined with demo or smoke checks')
    if (args.smoke_service or args.smoke_power or args.smoke_combined or args.smoke_startup) and not args.demo:
        parser.error('Simulated service smoke test requires --demo')

    build = prepare_environment(ROOT, 'service-gui', isolate=not (args.native and not args.smoke_native))
    os.environ['GWE_SERVICE_TRIAL'] = '1'
    os.environ.pop('GWE_UI_SMOKE_TEST', None)
    if args.smoke_test or args.smoke_service or args.smoke_power or args.smoke_combined or args.smoke_startup or args.smoke_native:
        os.environ['GWE_UI_SMOKE_TEST'] = '1'
    from gwe.fan_curve import FanCurve
    from gwe.fan_profiles import SavedFanProfile, read_profiles, manual_limits
    from gwe.fan_gui_session import FanGuiSession
    from gwe.fan_gui_log import FanGuiLog
    from gwe.fan_main_controller import FanMainController, configure_factory
    try:
        if args.native:
            profiles = ()  # The writable ORM tables are initialized by the application before the factory runs.
        elif args.demo:
            profiles = (SavedFanProfile(1, 'Synthetic trial', FanCurve(((0, 40), (50, 40), (80, 100))), None),)
        else:
            profiles = read_profiles(args.database)
        limits = (30, 100) if args.demo else manual_limits()
        if startup_profile is not None and not args.native:
            matches = [profile for profile in profiles if profile.name == startup_profile]
            if len(matches) != 1 or matches[0].problem:
                raise ValueError('Startup curve must uniquely match a compatible profile')
            matches[0].curve.validate_limits(*limits)
        log = FanGuiLog(build / 'logs' / 'trial.log')
        log.record('control_window_opened' if args.allow_control or args.smoke_service else 'preview_opened')
        resource_path = prepare_resources(ROOT, build)
    except Exception as error:
        print(f'Main-window trial setup failed: {type(error).__name__}; no GPU settings changed.', flush=True)
        return 1

    endpoint = '/run/gwe-fan-service/control.sock'
    stop = threading.Event()
    worker = service = temporary = backend = None
    if args.smoke_service or args.smoke_power or args.smoke_combined or args.smoke_startup or args.smoke_native:
        from gwe.fan_service import FanService
        class SimulatedBackend:
            starts = 0
            stops = 0
            renewals = 0
            def start(self, curve):
                self.starts += 1
            def stop(self):
                self.stops += 1
            def renew(self, deadline):
                self.renewals += 1
        backend = SimulatedBackend()
        temporary = tempfile.TemporaryDirectory(prefix='gwe-service-gui-')
        endpoint = str(Path(temporary.name) / 'control.sock')
        class SimulatedPower:
            uuid = None
            calls = []
            rejections = 0
            result = {'state': 'idle', 'operation_id': 0}
            def poll(self):
                pass
            def status(self):
                return {'ok': True, 'gpu_uuid': self.uuid, **self.result}
            def start(self, requested, expected):
                # Exercise a guarded rejection before the explicit successful retry.
                if not self.rejections:
                    self.rejections += 1
                    return {'ok': False, 'error': 'trial_guard_active'}
                self.calls.append((requested, expected))
                self.result = dict(state='applied', operation_id=len(self.calls),
                                   previous_mw=expected, applied_mw=requested)
                return self.status()
        simulated_power = SimulatedPower() if args.smoke_power or args.smoke_combined else None
        if args.smoke_combined:
            simulated_power.rejections = 1
        service = FanService(endpoint, backend, allowed_uid=os.geteuid(), power=simulated_power,
                             power_with_fan=args.continuous)
        def serve():
            while not stop.is_set():
                service.step(.01)
        worker = threading.Thread(target=serve, daemon=True)
        worker.start()
    session = FanGuiSession(endpoint, event_sink=log.record, continuous=args.continuous)
    def factory(view):
        from gwe.power_gui import PowerController
        if args.native:
            from gwe.interactor.settings_interactor import SettingsInteractor
            telemetry_ttl = max(2.5, min(60, SettingsInteractor.get_int('settings_refresh_interval') + 1))
        else:
            telemetry_ttl = 2.5
        power = PowerController(view, endpoint, allowed=True, event_sink=log.record,
                                telemetry_ttl=telemetry_ttl) if (
            args.allow_power_control or args.smoke_power or args.smoke_combined) else None
        if args.native:
            from peewee import SqliteDatabase
            from gwe.di import INJECTOR
            from gwe.native_fan_controller import NativeFanController
            if args.smoke_native:
                from gwe.model.fan_profile import FanProfile
                from gwe.model.speed_step import SpeedStep
                from gwe.model.current_fan_profile import CurrentFanProfile
                profile = (FanProfile.select().where(FanProfile.name == 'Native synthetic').order_by(FanProfile.id).first()
                           or FanProfile.create(name='Native synthetic'))
                if not profile.steps.exists():
                    for temperature, duty in ((0, 40), (50, 40), (80, 100)):
                        SpeedStep.create(profile=profile, temperature=temperature, duty=duty)
                if FanProfile.select().where(FanProfile.name == profile.name).count() == 1:
                    duplicate = FanProfile.create(name=profile.name)
                    for temperature, duty in ((0, 40), (80, 100)):
                        SpeedStep.create(profile=duplicate, temperature=temperature, duty=duty)
                CurrentFanProfile.delete().execute()
                CurrentFanProfile.create(profile=profile)
                SettingsInteractor.set_bool('settings_load_last_profile', True)
            return NativeFanController(view, INJECTOR.get(SqliteDatabase), limits, session,
                                       power=power, startup_profile_name=startup_profile)
        return FanMainController(view, profiles, limits, session,
                                 allow_control=args.allow_control or args.smoke_service or args.smoke_combined or args.smoke_startup,
                                 power=power, startup_profile_name=startup_profile)
    configure_factory(factory)

    import gi
    for namespace, version in (('Gtk', '3.0'), ('Gdk', '3.0'), ('Dazzle', '1.0'), ('Notify', '0.7')):
        gi.require_version(namespace, version)
    from gi.repository import Gio, GLib, Gtk
    Gtk.IconTheme.get_default().append_search_path(str(ROOT / 'data' / 'icons' / 'hicolor'))
    resource = Gio.Resource.load(str(resource_path))
    resource._register()
    from gwe import __main__ as entry
    passed, phase = [], [0]
    power_edit_started = [0]
    deadline = time.monotonic() + (50 if args.smoke_native else 30)
    if args.smoke_test or args.smoke_service or args.smoke_power or args.smoke_combined or args.smoke_startup or args.smoke_native or args.check_startup:
        def check():
            app = entry.INJECTOR.get(entry.Application)
            presenter, view = app._presenter, app._view
            controller = presenter._service_controller
            def finish(valid):
                passed.append(valid)
                if args.smoke_startup and not valid:
                    print('Startup check:', {'phase': phase[0], 'state': session.state,
                                             'starts': backend.starts, 'stops': backend.stops,
                                             'startup_pending': controller.startup_pending if controller else None}, flush=True)
                print('Startup control check:' if args.check_startup else 'Main-window service smoke test:',
                      'PASS' if valid else 'FAIL', flush=True)
                app.quit()
                return GLib.SOURCE_REMOVE
            expected_fault = args.smoke_native and phase[0] in (52, 53)
            if time.monotonic() >= deadline or (session.state == 'fault' and not expected_fault):
                return finish(False)
            if controller is None or not controller.telemetry_available:
                return GLib.SOURCE_CONTINUE
            if args.check_startup:
                if phase[0] == 0 and session.state == 'active':
                    if args.native:
                        if view._main_infobar.get_visible():
                            return finish(False)
                        view._fan_edit_button.clicked()
                        if presenter._edit_fan_profile_presenter._profile.id != controller.selected.identifier:
                            return finish(False)
                        presenter._edit_fan_profile_presenter.view.hide()
                        original = presenter._settings_interactor.get_int
                        try:
                            presenter._settings_interactor.get_int = lambda key, *a: (
                                1 if key == 'settings_minimize_to_tray' else original(key, *a))
                            if presenter.on_application_window_delete_event() is not True or view._window.get_visible():
                                return finish(False)
                        finally:
                            presenter._settings_interactor.get_int = original
                    print('Startup curve verified by service; keeping control for six seconds', flush=True)
                    power_edit_started[0] = time.monotonic()
                    phase[0] = 1
                elif phase[0] == 1 and time.monotonic() - power_edit_started[0] >= 6:
                    phase[0] = 2
                    if args.native:
                        if session.state != 'active' or controller.pending_transition:
                            return finish(False)
                        presenter.on_toggle_app_window_clicked()
                        print('Native editor and tray ownership: PASS; quitting without changing profiles', flush=True)
                        presenter.on_quit_clicked()
                    else:
                        view._window.close()
                    return GLib.SOURCE_REMOVE
                return GLib.SOURCE_CONTINUE
            if args.smoke_native:
                if phase[0] == 0 and session.state == 'active':
                    if view._main_infobar.get_visible() or backend.starts != 1:
                        return finish(False)
                    view._fan_edit_button.clicked()
                    editor = presenter._edit_fan_profile_presenter
                    if editor._profile.name != 'Native synthetic':
                        return finish(False)
                    from gwe.model.speed_step import SpeedStep
                    step = editor._profile.steps.order_by(SpeedStep.temperature).offset(1).first()
                    step.duty = 41
                    step.save()
                    editor.view.hide()
                    if controller.selected.curve.points[1][1] != 41:
                        return finish(False)
                    from gwe.interactor.settings_interactor import SettingsInteractor
                    SettingsInteractor.set_bool('settings_minimize_to_tray', True)
                    if presenter.on_application_window_delete_event() is not True or view._window.get_visible():
                        return finish(False)
                    power_edit_started[0] = time.monotonic()
                    phase[0] = 1
                elif phase[0] == 1 and time.monotonic() - power_edit_started[0] >= 2:
                    if session.state != 'active' or backend.stops:
                        return finish(False)
                    presenter.on_toggle_app_window_clicked()
                    automatic = next(p for p in controller.profiles if p.automatic)
                    view._fan_combobox.set_active(controller.profiles.index(automatic))
                    view._fan_apply_button.clicked()
                    phase[0] = 2
                elif phase[0] == 2 and session.state == 'idle' and controller.desired is None and controller.pending is None:
                    from gwe.model.current_fan_profile import CurrentFanProfile
                    if backend.starts != backend.stops or CurrentFanProfile.get().profile.type != 'auto':
                        return finish(False)
                    presenter._edit_fan_profile_presenter.show_add()
                    editor = presenter._edit_fan_profile_presenter
                    from gwe.model.speed_step import SpeedStep
                    for temperature, duty in ((0, 40), (50, 45), (80, 100)):
                        SpeedStep.create(profile=editor._profile, temperature=temperature, duty=duty)
                    view._fan_apply_button.clicked()
                    phase[0] = 3
                elif phase[0] == 3 and session.state == 'active' and controller.pending is None:
                    if backend.starts != 2:
                        return finish(False)
                    presenter._edit_fan_profile_presenter.on_delete_profile_clicked()
                    phase[0] = 4
                elif phase[0] == 4 and session.state == 'idle' and controller.desired is None and controller.pending is None:
                    from gwe.model.current_fan_profile import CurrentFanProfile
                    if backend.starts != backend.stops or CurrentFanProfile.get().profile.type != 'auto':
                        return finish(False)
                    profile = next(p for p in controller.profiles if p.name == 'Native synthetic')
                    view._fan_combobox.set_active(controller.profiles.index(profile))
                    view._fan_apply_button.clicked()
                    phase[0] = 5
                elif phase[0] == 5 and session.state == 'active' and controller.pending is None:
                    phase[0] = 51
                    power_edit_started[0] = time.monotonic()
                    view.show_error_message_dialog('Synthetic control notice',
                                                   'Control must keep renewing while this notice is open.')
                elif phase[0] == 51 and time.monotonic() - power_edit_started[0] >= 10:
                    notice_open = any(isinstance(widget, Gtk.MessageDialog) and widget.get_visible()
                                      for widget in Gtk.Window.list_toplevels())
                    if not notice_open or session.state != 'active' or backend.stops != 2 or backend.renewals < 5:
                        return finish(False)
                    print('Native error notice: PASS; control renews and Quit remains available', flush=True)
                    renewals = backend.renewals
                    time.sleep(6)  # Deliberately block GTK beyond the five-second lease.
                    if session.state != 'active' or backend.stops != 2 or backend.renewals < renewals + 4:
                        return finish(False)
                    print('Blocked GTK: PASS; simulated curve stays active', flush=True)
                    from gwe.fan_gui_session import GuiTrialError
                    controller.executor.submit(session._fail, GuiTrialError('service_fault'))
                    phase[0] = 52
                elif phase[0] == 52 and session.state == 'fault':
                    controller.refresh()
                    if (not view._main_infobar.get_visible() or not view._main_infobar.get_revealed()
                            or view._main_infobar.get_show_close_button()
                            or 'no longer' not in view._main_infobar_label.get_text()
                            or view._fan_apply_button.get_sensitive() or view._fan_combobox.get_sensitive()):
                        return finish(False)
                    print('Control loss: PASS; persistent warning and disabled Apply', flush=True)
                    power_edit_started[0] = time.monotonic()
                    phase[0] = 53
                elif phase[0] == 53 and time.monotonic() - power_edit_started[0] >= .6:
                    if not view._main_infobar_label.get_mapped():
                        return finish(False)
                    from gwe.interactor.settings_interactor import SettingsInteractor
                    SettingsInteractor.set_bool('settings_minimize_to_tray', False)
                    phase[0] = 6
                    view._window.close()
                    return GLib.SOURCE_REMOVE
                return GLib.SOURCE_CONTINUE
            if args.smoke_startup:
                if phase[0] == 0 and session.state == 'active':
                    if backend.starts != 1 or controller.selected.name != 'Synthetic trial':
                        return finish(False)
                    view._fan_edit_button.clicked()
                    phase[0] = 1
                elif phase[0] == 1 and session.state == 'idle' and controller.pending is None:
                    power_edit_started[0] = time.monotonic()
                    phase[0] = 2
                elif phase[0] == 2 and time.monotonic() - power_edit_started[0] >= 2:
                    return finish(backend.starts == backend.stops == 1 and session.state == 'idle')
                return GLib.SOURCE_CONTINUE
            if args.smoke_combined:
                power = controller.power
                gpu = presenter._latest_status.gpu_status_list[0]
                simulated_power.uuid = gpu.info.uuid
                if view._overclock_frame.get_sensitive() or not presenter._latest_status.read_only:
                    return finish(False)
                if phase[0] == 0:
                    if simulated_power.calls or session.client is not None:
                        return finish(False)
                    view._fan_combobox.set_active(0)
                    if not view._fan_apply_button.get_sensitive():
                        return GLib.SOURCE_CONTINUE
                    view._fan_apply_button.clicked()
                    phase[0] = 1
                elif phase[0] == 1 and session.state == 'active' and view._power_limit_apply_button.get_sensitive():
                    view._power_limit_adjustment.set_value(320)
                    view._power_limit_apply_button.clicked()
                    phase[0] = 2
                elif phase[0] == 2 and power.operation_id is None and simulated_power.calls:
                    if (simulated_power.calls != [(320000, round(gpu.power.limit * 1000))]
                            or 'Power verified: 320 W' not in view._main_infobar_label.get_text()
                            or session.state != 'active' or backend.stops):
                        return finish(False)
                    power_edit_started[0] = time.monotonic()
                    phase[0] = 3
                elif phase[0] == 3 and time.monotonic() - power_edit_started[0] >= 5:
                    if session.state != 'active' or backend.renewals < 2 or backend.stops:
                        return finish(False)
                    view._fan_edit_button.clicked()
                    phase[0] = 4
                elif phase[0] == 4 and session.state == 'idle' and controller.pending is None:
                    return finish(backend.starts == backend.stops == 1 and 'recovery verified' in session.message)
                return GLib.SOURCE_CONTINUE
            if args.smoke_power:
                power = controller.power
                gpu = presenter._latest_status.gpu_status_list[0]
                simulated_power.uuid = gpu.info.uuid
                if view._overclock_frame.get_sensitive() or not presenter._latest_status.read_only:
                    return finish(False)
                if phase[0] == 0 and view._power_limit_apply_button.get_sensitive():
                    if simulated_power.calls:
                        return finish(False)
                    wanted = max(gpu.power.minimum, gpu.power.limit - 10)
                    view._power_limit_adjustment.set_value(wanted)
                    power_edit_started[0] = time.monotonic()
                    phase[0] = -1
                elif phase[0] == -1 and time.monotonic() - power_edit_started[0] >= 3:
                    wanted = max(gpu.power.minimum, gpu.power.limit - 10)
                    if view._power_limit_adjustment.get_value() != wanted:
                        return finish(False)
                    if not view._power_limit_apply_button.get_sensitive():
                        return GLib.SOURCE_CONTINUE
                    view._power_limit_apply_button.clicked()
                    phase[0] = 1
                elif phase[0] == 1 and simulated_power.rejections and power.operation_id is None:
                    if simulated_power.calls or 'only 240 W or 250 W' not in view._main_infobar_label.get_text():
                        return finish(False)
                    if not view._power_limit_apply_button.get_sensitive():
                        return GLib.SOURCE_CONTINUE
                    view._power_limit_apply_button.clicked()
                    phase[0] = 2
                elif phase[0] == 2 and power.operation_id is None and simulated_power.calls:
                    expected = round(gpu.power.limit * 1000)
                    wanted = round(max(gpu.power.minimum, gpu.power.limit - 10) * 1000)
                    return finish(simulated_power.calls == [(wanted, expected)]
                                  and 'Power verified:' in power.message and backend.starts == 0
                                  and view._main_infobar_label.get_text().startswith('Power verified:')
                                  and view._main_infobar_label.get_line_wrap()
                                  and view._main_infobar_label.get_mapped()
                                  and view._main_infobar.get_revealed())
                return GLib.SOURCE_CONTINUE
            if (view._overclock_frame.get_sensitive() or view._power_limit_apply_button.get_sensitive()
                    or not presenter._latest_status.read_only):
                return finish(False)
            if phase[0] == 0:
                if session.client is not None or session.state != 'idle' or presenter._fan_profile_applied is not None:
                    return finish(False)
                gpu = presenter._latest_status.gpu_status_list[0]
                def matches(widget, value, template):
                    return (widget.get_sensitive() == (value is not None)
                            and widget.get_text() == (template.format(value) if value is not None else ''))
                power_ok = all(matches(getattr(view, f'_power_{widget}_entry'),
                                       getattr(gpu.power, field), template)
                               for field, widget, template in (
                                   ('draw', 'draw', '{:.2f} W'), ('limit', 'limit', '{:.0f} W'),
                                   ('default', 'default', '{:.0f} W'), ('enforced', 'enforced', '{:.0f} W'),
                                   ('minimum', 'min', '{} W'), ('maximum', 'max', '{} W')))
                clocks_ok = all(matches(getattr(view, f'_clocks_{widget}_{kind}_entry'),
                                        getattr(gpu.clocks, f'{domain}_{kind}'), '{} MHz')
                                for domain, widget in (('graphic', 'graphics'), ('sm', 'sm'),
                                                       ('memory', 'memory'), ('video', 'video'))
                                for kind in ('current', 'max'))
                fans_ok = all(matches(view._fan_duty[index], percent, '{} %')
                              and matches(view._fan_rpm[index], rpm, '{} RPM')
                              for index, (percent, rpm) in enumerate(gpu.fan.fan_list or []))
                info_ok = all(matches(getattr(view, f'_info_{widget}_entry'),
                                      getattr(gpu.info, field), template)
                              for field, widget, template in (
                                  ('vbios', 'vbios', '{}'), ('cuda_cores', 'cuda', '{}'),
                                  ('memory_interface', 'memory_interface', '{} bit'),
                                  ('encoder_usage', 'encoder_usage', '{}%'),
                                  ('decoder_usage', 'decoder_usage', '{}%')))
                pcie = (gpu.info.pcie_max_link, gpu.info.pcie_max_generation,
                        gpu.info.pcie_current_link, gpu.info.pcie_current_generation)
                pcie_text = '{}x Gen{} @ {}x Gen{}'.format(*pcie) if None not in pcie else None
                info_ok = info_ok and matches(view._info_pcie_entry, pcie_text, '{}')
                temp_ok = all(matches(getattr(view, widget), getattr(gpu.temp, field), '{} °C')
                              for field, widget in (('maximum', '_temp_max_gpu_value'),
                                                    ('slowdown', '_temp_slowdown_value'),
                                                    ('shutdown', '_temp_shutdown_value')))
                scale_ok = not view._power_limit_scale.get_sensitive()
                if all(value is not None for value in (gpu.power.minimum, gpu.power.maximum,
                                                       gpu.power.default, gpu.power.limit)):
                    scale_ok = scale_ok and view._power_limit_adjustment.get_value() == gpu.power.limit
                if not all((power_ok, clocks_ok, fans_ok, info_ok, temp_ok, scale_ok)):
                    return finish(False)
                print('Main-window telemetry display: info, temperature, power, clocks and fans match backend', flush=True)
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
                power_edit_started[0] = time.monotonic()
                phase[0] = 4
            elif (phase[0] == 4 and args.continuous and session.state == 'active'
                  and controller.pending is None and time.monotonic() - power_edit_started[0] >= 11):
                if view._fan_apply_button.get_label() != 'Apply selected curve':
                    return finish(False)
                view._fan_edit_button.clicked()
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
        if args.smoke_native:
            def abort_native():
                # A regressed nested dialog must fail instead of leaving a hung smoke process.
                for widget in Gtk.Window.list_toplevels():
                    if isinstance(widget, Gtk.MessageDialog):
                        widget.destroy()
                entry.INJECTOR.get(entry.Application).quit()
                return GLib.SOURCE_REMOVE
            GLib.timeout_add(55000, abort_native)

    sys.argv = ['gwe-nvml' if args.native else 'gwe-service-trial']
    if args.hide_window:
        sys.argv.append('--hide-window')
    if args.delay:
        sys.argv.append('--delay')
    result = 1
    try:
        try:
            entry.main()
        except SystemExit as error:
            result = error.code
        if args.check_startup and phase[0] == 2:
            controller = entry.INJECTOR.get(entry.Application)._presenter._service_controller
            passed.append(controller.closed and session.client is None)
            print('Window-close disconnect:', 'PASS' if passed[-1] else 'FAIL', flush=True)
        if args.smoke_service and phase[0] == 6:
            controller = entry.INJECTOR.get(entry.Application)._presenter._service_controller
            passed.append(controller.closed and session.client is None)
            print('Main-window service smoke test:', 'PASS' if passed[-1] else 'FAIL', flush=True)
        if args.smoke_native and phase[0] == 6:
            controller = entry.INJECTOR.get(entry.Application)._presenter._service_controller
            passed.append(controller.closed and session.client is None)
            print('Native editor, create/delete, automatic mode and tray/close:',
                  'PASS' if passed[-1] else 'FAIL', flush=True)
    finally:
        session.close()
        if service is not None:
            # Let the simulated server process socket EOF before checking window-close recovery.
            expires = time.monotonic() + 2
            while (args.smoke_service or args.smoke_native) and backend.stops < 3 and time.monotonic() < expires:
                time.sleep(.01)
            stop.set()
            worker.join(2)
            service.close()
            temporary.cleanup()
    if args.smoke_test or args.smoke_service or args.smoke_power or args.smoke_combined or args.smoke_startup or args.smoke_native or args.check_startup:
        return 0 if passed == [True] and (not (args.smoke_service or args.smoke_native) or backend.starts == backend.stops == 3) else 1
    return result


if __name__ == '__main__':
    raise SystemExit(main())
