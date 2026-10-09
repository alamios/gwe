# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded UI-owned service trial, independent of GTK and the legacy GPU writers."""
import time

from gwe.fan_service import FanClient, boot_time


class GuiTrialError(RuntimeError):
    """A local diagnostic code; never wraps raw protocol or driver error text."""


class FanGuiSession:
    """Serialize calls in one I/O worker; continuous renewals are independent of GTK."""
    def __init__(self, path, *, factory=FanClient, clock=boot_time, event_sink=None, continuous=False,
                 active_clock=None):
        self.path, self.factory, self.clock = path, factory, clock
        self.client = None
        self.state = 'idle'
        self.message = 'Preview only; no curve applied.'
        self.deadline = self.last_tick = self.recovery_deadline = None
        self.last_error = None
        self.last_operation = 'preview'
        self.event_sink = event_sink
        self.log_failed = False
        self.continuous = continuous
        # BOOTTIME includes suspend; MONOTONIC excludes it. Scheduling stalls
        # advance both equally and must remain latched faults, not resume triggers.
        self.active_clock = active_clock or (time.monotonic if clock is boot_time else clock)
        self.last_active_tick = None
        self.applied = self.resume_target = None
        self.resume_deadline = None

    def _emit(self, event, **timing):
        if self.event_sink is not None:
            try:
                self.event_sink(event, state=self.state, operation=self.last_operation,
                                error=self.last_error, **timing)
            except Exception:
                # A disk failure must never interrupt disconnect or service recovery.
                self.log_failed = True

    def _request(self, operation, **fields):
        self.last_operation = operation
        response = self.client.request(operation, **fields)
        if not isinstance(response, dict):
            raise GuiTrialError('invalid_response')
        if response.get('ok') is not True:
            code = response.get('error')
            known = ('busy', 'fault', 'recovery_failed', 'not_owner', 'worker_unavailable')
            raise GuiTrialError('service_' + code if isinstance(code, str) and code in known
                                else 'request_refused')
        return response

    def _fail(self, error=None):
        if isinstance(error, GuiTrialError):
            code = str(error)
        elif isinstance(error, TimeoutError):
            code = 'socket_timeout'
        elif isinstance(error, PermissionError):
            code = 'socket_permission_denied'
        elif isinstance(error, OSError):
            code = 'service_connection_unavailable'
        else:
            code = 'client_error'
        self.last_error = code
        self.close()
        self.state = 'fault'
        self.message = (f'Control stopped ({code} during {self.last_operation}). '
                        'The selected fan curve is no longer being maintained by this application. '
                        'Automatic recovery is not verified; check the service before restarting GWE.')
        self._emit('failed')

    def begin(self, curve, limits):
        if self.state != 'idle' or self.client is not None:
            raise RuntimeError('A trial is already active or requires recovery review')
        curve.validate_limits(*limits)
        try:
            self.last_error = None
            self.last_operation = 'connect'
            self._emit('acquire_requested')
            self.client = self.factory(self.path)
            status = self._request('status')
            if status.get('state') != 'idle' or status.get('owned') is not False:
                raise GuiTrialError('service_not_idle')
            self._request('acquire', points=[list(point) for point in curve.points],
                          hysteresis=curve.hysteresis, vbios_silent=curve.vbios_silent)
            self.last_tick = self.clock()
            self.last_active_tick = self.active_clock()
            self.applied = (curve, tuple(limits))
            self.deadline = None if self.continuous else self.last_tick + 10
            self.state = 'starting'
            self.message = ('Starting the selected curve; waiting for verified control.' if self.continuous
                            else 'Starting a ten-second trial; waiting for verified control.')
            self._emit('starting')
        except Exception as error:
            self._fail(error)

    def release(self):
        if self.state == 'resuming':
            self.close()
            self.state = 'idle'
            self.message = 'Resume cancelled; no curve reapplied.'
            self._emit('resume_cancelled')
            return
        if self.state not in ('starting', 'active'):
            return
        try:
            self._emit('release_requested')
            self._request('release')
            self.state = 'stopping'
            self.recovery_deadline = self.clock() + 10
            self.message = 'Restoring automatic control; waiting for verification.'
            self._emit('stopping')
        except Exception as error:
            self._fail(error)

    def tick(self, heartbeat):
        if self.state == 'resuming':
            self._resume()
            return
        if self.client is None:
            return
        try:
            now = self.clock()
            active_now = self.active_clock()
            if (self.continuous and self.state in ('starting', 'active') and self.applied is not None
                    and now - self.last_tick - (active_now - self.last_active_tick) >= 1):
                target = self.applied
                self.close()  # Release stale ownership; never revive an expired lease.
                self.resume_target = target
                self.resume_deadline = now + 15
                self.state = 'resuming'
                self.message = 'Resuming after suspend; waiting for verified automatic control.'
                self._emit('suspend_detected')
                self._resume()
                return
            if now - heartbeat > 2 or heartbeat < self.last_tick or now - self.last_tick > 2.5:
                self.last_operation = 'worker_tick' if self.continuous else 'ui_tick'
                self._emit('heartbeat_expired', heartbeat_age_seconds=now - heartbeat,
                           tick_gap_seconds=now - self.last_tick)
                raise GuiTrialError('worker_heartbeat_expired' if self.continuous else 'ui_heartbeat_expired')
            self.last_tick = now
            self.last_active_tick = active_now
            if self.state in ('starting', 'active') and self.deadline is not None and now >= self.deadline:
                self.release()
            if self.client is None:
                return
            status = self._request('status')
            state = status.get('state')
            if state == 'idle' and status.get('owned') is False:
                if self.state != 'stopping':
                    raise GuiTrialError('unexpected_automatic_recovery')
                self.close()
                self.state = 'idle'
                self.message = 'Both fans restored to automatic; recovery verified by the service.'
                self._emit('recovery_verified')
            elif self.state == 'stopping':
                if state != 'stopping' or self.clock() >= self.recovery_deadline:
                    raise GuiTrialError('recovery_not_verified')
            elif state in ('starting', 'active') and status.get('owned') is True:
                # Native/socket delays must not extend the ten-second trial.
                if self.deadline is not None and self.clock() >= self.deadline:
                    self.release()
                else:
                    self._request('renew')
                    became_active = self.state != 'active' and state == 'active'
                    self.state = state
                    self.message = 'Curve active; service owns fan writes.' if state == 'active' else self.message
                    if became_active:
                        self._emit('active')
            else:
                if state in ('fault', 'recovery_failed'):
                    raise GuiTrialError('service_' + state)
                raise GuiTrialError('ownership_or_state_lost')
        except Exception as error:
            self._fail(error)

    def _resume(self):
        """One bounded reacquisition, only after a measured suspend and verified idle."""
        try:
            if self.clock() >= self.resume_deadline:
                raise GuiTrialError('resume_recovery_timeout')
            if self.client is None:
                self.last_operation = 'connect'
                self.client = self.factory(self.path)
            status = self._request('status')
            if self.clock() >= self.resume_deadline:
                raise GuiTrialError('resume_recovery_timeout')
            if status.get('state') == 'stopping' and status.get('owned') is False:
                return
            if status.get('state') != 'idle' or status.get('owned') is not False:
                raise GuiTrialError('resume_service_not_idle')
            target = self.resume_target
            self.close()
            self.state = 'idle'
            self._emit('resume_recovery_verified')
            # The ordinary acquisition revalidates the curve; the privileged
            # worker rechecks identity, current limits, policies and temperature.
            self.begin(*target)
            if self.state == 'starting':
                self._emit('resume_acquired')
        except Exception as error:
            self._fail(error)

    def close(self):
        self.resume_target = None
        if self.state == 'resuming':
            self.state = 'idle'
        if self.client is not None:
            self.client.close()  # Disconnect initiates independent service recovery.
            self.client = None
            self._emit('disconnected')
