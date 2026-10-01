# SPDX-License-Identifier: GPL-3.0-or-later
"""Main-window adapter for the bounded service client; no GTK or profile DB writes."""
from concurrent.futures import ThreadPoolExecutor
from html import escape

from gwe.fan_service import boot_time

_factory = None


def configure_factory(factory):
    """Called by the isolated launcher before importing application/DI modules."""
    global _factory
    _factory = factory


def create_controller(view):
    if _factory is None:
        raise RuntimeError('Service trial requires its isolated launcher')
    return _factory(view)


class FanMainController:
    def __init__(self, view, profiles, limits, session, *, allow_control=False, clock=boot_time, power=None):
        self.view, self.profiles, self.limits = view, profiles, limits
        self.session, self.allow_control, self.clock = session, allow_control, clock
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.pending = None
        self.selected = None
        self.next_tick = 0
        self.closed = False
        self.telemetry_available = False
        self.power = power
        if power is not None:
            power.fan_busy = lambda: self.pending is not None or self.session.state != 'idle'

    def start(self):
        self.view.prepare_service_controls()
        self.view.set_service_continuous(self.session.continuous)
        self.view.refresh_fan_profile_combobox(
            [(profile.identifier, escape(profile.name)) for profile in self.profiles], None)
        self.refresh()

    def problem(self):
        if self.selected is None:
            return 'Select a saved curve. Startup never applies a profile.'
        if self.selected.problem:
            return self.selected.problem
        try:
            self.selected.curve.validate_limits(*self.limits)
        except ValueError as error:
            return str(error)
        return None

    def select(self, identifier):
        if self.pending is not None or self.session.state != 'idle' or self.closed:
            return
        self.selected = next((profile for profile in self.profiles if profile.identifier == identifier), None)
        self.view.refresh_service_curve(self.selected.curve if self.selected else None)
        self.refresh()

    def refresh(self):
        busy = self.pending is not None or self.session.state != 'idle' or self.closed
        busy = busy or (self.power is not None and self.power.busy)
        self.view.set_service_selection_enabled(not busy)
        self.view.set_apply_fan_profile_button_enabled(bool(
            self.allow_control and self.telemetry_available and not busy and not self.problem()))
        self.view.set_edit_fan_profile_button_enabled(
            not self.closed and self.pending is None and self.session.state in ('starting', 'active'))
        message = self.session.message
        if self.session.state == 'idle':
            message += ' ' + (self.problem() or 'Selected curve is compatible with current manual limits.')
            if not self.allow_control:
                message += ' Preview only.'
        if self.session.log_failed:
            message += ' Local diagnostic log unavailable.'
        if self.power is not None:
            # Keep the relevant result visible before optional preview instructions.
            if self.session.state == 'idle':
                message = self.power.message + ('\n' + message if self.allow_control else '')
                if self.session.log_failed and not self.allow_control:
                    message += ' Local diagnostic log unavailable.'
            else:
                message += '\n' + self.power.message
        self.view.show_main_infobar_message(message)

    def _submit(self, operation, *arguments):
        if self.closed or self.pending is not None:
            return
        self.pending = self.executor.submit(operation, *arguments)
        self.refresh()

    def apply(self):
        if (self.allow_control and self.telemetry_available and self.session.state == 'idle'
                and not (self.power is not None and self.power.busy)
                and not self.problem()):
            self._submit(self.session.begin, self.selected.curve, self.limits)

    def release(self):
        self._submit(self.session.release)

    def telemetry(self, available):
        self.telemetry_available = available
        self.refresh()

    def pulse(self):
        if self.closed:
            return False
        if self.power is not None:
            self.power.pulse()
            self.refresh()
        if self.pending is not None and self.pending.done():
            task, self.pending = self.pending, None
            try:
                task.result()
            except Exception as error:
                self.session._fail(error)
            self.refresh()
        now = self.clock()
        if self.pending is None and self.session.client is not None:
            if not self.telemetry_available and self.session.state in ('starting', 'active'):
                self.release()
            elif now >= self.next_tick:
                self.next_tick = now + 1
                self._submit(self.session.tick, now)
        return True

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.power is not None:
            self.power.close()
        self.executor.submit(self.session.close)
        self.executor.shutdown(wait=True)
        self.session._emit('window_closed')
