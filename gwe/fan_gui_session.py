# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded UI-owned service trial, independent of GTK and the legacy GPU writers."""
from gwe.fan_service import FanClient, boot_time


class FanGuiSession:
    """Serialize calls in one I/O worker. Renew only in response to fresh UI ticks."""
    def __init__(self, path, *, factory=FanClient, clock=boot_time):
        self.path, self.factory, self.clock = path, factory, clock
        self.client = None
        self.state = 'idle'
        self.message = 'Preview only; no curve applied.'
        self.deadline = self.last_tick = self.recovery_deadline = None

    def _request(self, operation, **fields):
        response = self.client.request(operation, **fields)
        if not isinstance(response, dict) or response.get('ok') is not True:
            raise RuntimeError('Service refused the request')
        return response

    def _fail(self):
        self.close()
        self.state = 'fault'
        self.message = 'Trial stopped. Automatic recovery is not verified; check the service.'

    def begin(self, curve, limits):
        if self.state != 'idle' or self.client is not None:
            raise RuntimeError('A trial is already active or requires recovery review')
        curve.validate_limits(*limits)
        try:
            self.client = self.factory(self.path)
            status = self._request('status')
            if status.get('state') != 'idle' or status.get('owned') is not False:
                raise RuntimeError('Service is busy or unavailable')
            self._request('acquire', points=[list(point) for point in curve.points],
                          hysteresis=curve.hysteresis, vbios_silent=curve.vbios_silent)
            self.last_tick = self.clock()
            self.deadline = self.last_tick + 10
            self.state = 'starting'
            self.message = 'Starting a ten-second trial; waiting for verified control.'
        except Exception:
            self._fail()

    def release(self):
        if self.state not in ('starting', 'active'):
            return
        try:
            self._request('release')
            self.state = 'stopping'
            self.recovery_deadline = self.clock() + 10
            self.message = 'Restoring automatic control; waiting for verification.'
        except Exception:
            self._fail()

    def tick(self, heartbeat):
        if self.client is None:
            return
        try:
            now = self.clock()
            if now - heartbeat > 2 or heartbeat < self.last_tick or now - self.last_tick > 2.5:
                raise RuntimeError('UI heartbeat expired')
            self.last_tick = now
            if self.state in ('starting', 'active') and now >= self.deadline:
                self.release()
            if self.client is None:
                return
            status = self._request('status')
            state = status.get('state')
            if state == 'idle' and status.get('owned') is False:
                self.close()
                self.state = 'idle'
                self.message = 'Both fans restored to automatic; recovery verified by the service.'
            elif self.state == 'stopping':
                if state != 'stopping' or self.clock() >= self.recovery_deadline:
                    raise RuntimeError('Recovery not verified')
            elif state in ('starting', 'active') and status.get('owned') is True:
                # Native/socket delays must not extend the ten-second trial.
                if self.clock() >= self.deadline:
                    self.release()
                else:
                    self._request('renew')
                    self.state = state
                    self.message = 'Curve active; service owns fan writes.' if state == 'active' else self.message
            else:
                raise RuntimeError('Ownership or service state lost')
        except Exception:
            self._fail()

    def close(self):
        if self.client is not None:
            self.client.close()  # Disconnect initiates independent service recovery.
            self.client = None
