#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Isolated GTK profile review and optional ten-second service-client trials."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import signal
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gwe.fan_curve import FanCurve
from gwe.fan_gui_session import FanGuiSession
from gwe.fan_profiles import SavedFanProfile, manual_limits, read_profiles
from gwe.fan_service import boot_time


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--database', type=Path, help='Explicit SQLite backup opened read-only')
    source.add_argument('--demo', action='store_true', help='Synthetic curve, no database or GPU reads')
    parser.add_argument('--allow-control', action='store_true', help='Enable explicit ten-second service trials')
    parser.add_argument('--inspect-only', action='store_true', help='Print anonymous validation counts and exit')
    parser.add_argument('--smoke-test', action='store_true', help='Check preview controls and quit after three seconds')
    args = parser.parse_args(argv)
    if args.allow_control and (args.demo or args.smoke_test or args.inspect_only):
        parser.error('Control cannot be combined with demo, smoke-test or inspect-only')
    try:
        profiles = (SavedFanProfile(1, 'Synthetic trial', FanCurve(((0, 40), (50, 40), (60, 50), (80, 100))), None),) if args.demo else read_profiles(args.database)
        limits = (30, 100) if args.demo else manual_limits()
    except Exception as error:
        print(f'Profile review failed: {type(error).__name__}; no GPU settings changed.', flush=True)
        return 1

    def problem(profile):
        if profile.problem:
            return profile.problem
        try:
            profile.curve.validate_limits(*limits)
        except ValueError as error:
            return str(error)
        return None

    if args.inspect_only:
        compatible = sum(problem(profile) is None for profile in profiles)
        print({'profiles': len(profiles), 'compatible_curves': compatible,
               'blocked_or_automatic': len(profiles) - compatible, 'manual_limits': limits})
        print('Read-only review; no profile migration or GPU writes.', flush=True)
        return 0

    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gio, GLib, Gtk

    application = Gtk.Application(application_id='com.leinardi.gwe.FanTrial',
                                  flags=Gio.ApplicationFlags.NON_UNIQUE)
    session = FanGuiSession('/run/gwe-fan-service/control.sock')
    executor = ThreadPoolExecutor(max_workers=1)
    pending = [None]
    selected = [None]
    passed = []
    widgets = {}
    next_tick = [0]

    def refresh():
        profile = selected[0]
        busy = pending[0] is not None or session.state != 'idle'
        widgets['apply'].set_sensitive(bool(args.allow_control and profile and not problem(profile) and not busy))
        widgets['release'].set_sensitive(pending[0] is None and session.state in ('starting', 'active'))
        widgets['profiles'].set_sensitive(not busy)
        widgets['status'].set_text(session.message)

    def submit(operation, *arguments):
        if pending[0] is not None:
            return
        pending[0] = executor.submit(operation, *arguments)
        refresh()

    def pulse():
        future = pending[0]
        if future is not None and future.done():
            pending[0] = None
            try:
                future.result()
            except Exception:
                session._fail()
            refresh()
        now = boot_time()
        if pending[0] is None and session.client is not None and now >= next_tick[0]:
            next_tick[0] = now + 1
            submit(session.tick, now)
        return GLib.SOURCE_CONTINUE

    def changed(combo):
        index = combo.get_active()
        selected[0] = profiles[index] if index >= 0 else None
        profile = selected[0]
        if profile:
            details = problem(profile) or 'Compatible with reported manual limits.'
            if profile.curve:
                details += f'\nHysteresis: {profile.curve.hysteresis} C; firmware silent mode: {profile.curve.vbios_silent}'
                details += '\n' + ', '.join(f'{temperature} C: {duty}%' for temperature, duty in profile.curve.points)
            widgets['details'].set_text(details)
        widgets['chart'].queue_draw()
        refresh()

    def draw(widget, context):
        width, height = widget.get_allocated_width(), widget.get_allocated_height()
        left, top, plot_width, plot_height = 45, 20, max(1, width - 70), max(1, height - 55)
        context.set_source_rgb(.4, .4, .4)
        context.set_line_width(1)
        context.move_to(left, top)
        context.line_to(left, top + plot_height)
        context.line_to(left + plot_width, top + plot_height)
        context.stroke()
        context.move_to(2, top + 5)
        context.show_text('100%')
        context.move_to(left, height - 10)
        context.show_text('0 C')
        context.move_to(left + plot_width - 40, height - 10)
        context.show_text('150 C')
        profile = selected[0]
        if profile and profile.curve:
            context.set_source_rgb(.15, .6, .9)
            context.set_line_width(2)
            points = ((0, profile.curve.points[0][1]), *profile.curve.points,
                      (150, profile.curve.points[-1][1]))
            for index, (temperature, duty) in enumerate(points):
                position = (left + temperature / 150 * plot_width, top + (100 - duty) / 100 * plot_height)
                (context.move_to if index == 0 else context.line_to)(*position)
            context.stroke()
        return False

    def activate(app):
        window = Gtk.ApplicationWindow(application=app, title='GWE fan curve review')
        window.set_default_size(700, 450)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin=16)
        window.add(box)
        intro = 'Ten-second supervised trials; the service stops above 60 C.' if args.allow_control else 'Read-only preview. Select a curve to inspect; nothing is applied.'
        box.pack_start(Gtk.Label(label=intro), False, False, 0)
        combo = Gtk.ComboBoxText()
        for profile in profiles:
            combo.append_text(profile.name)
        box.pack_start(combo, False, False, 0)
        chart = Gtk.DrawingArea()
        chart.set_size_request(500, 220)
        chart.connect('draw', draw)
        box.pack_start(chart, True, True, 0)
        details = Gtk.Label(xalign=0, wrap=True, selectable=True)
        box.pack_start(details, False, False, 0)
        buttons = Gtk.Box(spacing=12)
        apply_button = Gtk.Button(label='Run selected curve for 10 seconds')
        release_button = Gtk.Button(label='Restore automatic')
        apply_button.connect('clicked', lambda _: submit(session.begin, selected[0].curve, limits))
        release_button.connect('clicked', lambda _: submit(session.release))
        buttons.pack_start(apply_button, False, False, 0)
        buttons.pack_start(release_button, False, False, 0)
        box.pack_start(buttons, False, False, 0)
        status = Gtk.Label(xalign=0, wrap=True)
        box.pack_start(status, False, False, 0)
        widgets.update(profiles=combo, chart=chart, details=details, apply=apply_button,
                       release=release_button, status=status)
        combo.connect('changed', changed)
        combo.set_active(0 if profiles else -1)
        refresh()
        window.show_all()
        GLib.timeout_add(100, pulse)
        if args.smoke_test:
            def finish():
                valid = (selected[0] is not None and not apply_button.get_sensitive()
                         and not release_button.get_sensitive() and session.client is None)
                passed.append(valid)
                print('Fan GUI preview smoke test:', 'PASS' if valid else 'FAIL', flush=True)
                app.quit()
                return GLib.SOURCE_REMOVE
            GLib.timeout_add_seconds(3, finish)

    application.connect('activate', activate)
    for signum in (signal.SIGINT, signal.SIGTERM):
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signum, lambda: (application.quit(), False)[1])
    try:
        result = application.run(['gwe-fan-trial'])
    finally:
        # Serialized behind any pending request; disconnect is covered by service supervision.
        executor.submit(session.close)
        executor.shutdown(wait=True)
    return (0 if passed == [True] else 1) if args.smoke_test else result


if __name__ == '__main__':
    raise SystemExit(main())
