# SPDX-License-Identifier: GPL-3.0-or-later
"""Small local diagnostic log with explicit fields, redaction and bounded retention."""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import stat
import threading

EVENTS = {'preview_opened', 'control_window_opened', 'acquire_requested', 'starting', 'active',
          'release_requested', 'stopping', 'recovery_verified', 'failed', 'disconnected', 'window_closed',
          'power_verified', 'power_rolled_back', 'power_failed', 'heartbeat_expired',
          'suspend_detected', 'resume_cancelled', 'resume_recovery_verified', 'resume_acquired'}
STATES = {'idle', 'starting', 'active', 'stopping', 'resuming', 'fault'}
OPERATIONS = {'preview', 'connect', 'status', 'acquire', 'renew', 'release', 'ui_tick', 'worker_tick',
              'power_status', 'power_apply'}
ERRORS = {'invalid_response', 'request_refused', 'service_busy', 'service_fault',
          'service_recovery_failed', 'service_not_owner', 'service_worker_unavailable',
          'service_not_idle', 'socket_timeout', 'socket_permission_denied',
          'service_connection_unavailable', 'client_error', 'ui_heartbeat_expired',
          'recovery_not_verified', 'ownership_or_state_lost', 'worker_heartbeat_expired',
          'unexpected_automatic_recovery', 'resume_recovery_timeout', 'resume_service_not_idle'}
ERRORS |= {'trial_guard_active', 'stale_power', 'outside_limits', 'power_busy', 'busy',
           'saved_power_invalid', 'power_save_failed',
           'recovery_pending', 'recovery_failed', 'worker_unavailable', 'worker_lost',
           'worker_stuck', 'driver_error', 'verification_failed', 'identity_mismatch'}


class FanGuiLog:
    """JSON lines, UTC timestamps, mode 0600, one rotated file; no profile fields."""
    def __init__(self, path, max_bytes=65536):
        if max_bytes < 512:
            raise ValueError('Diagnostic log size is too small')
        self.path = Path(path)
        self.max_bytes = max_bytes
        self.lock = threading.Lock()
        self.path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        if self.path.parent.is_symlink():
            raise ValueError('Diagnostic directory cannot be a symlink')
        self.path.parent.chmod(0o700)
        with self._open():
            pass

    def _open(self):
        descriptor = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            details = os.fstat(descriptor)
            if not stat.S_ISREG(details.st_mode) or details.st_uid != os.geteuid() or details.st_nlink != 1:
                raise ValueError('Unexpected diagnostic file ownership or type')
            os.fchmod(descriptor, 0o600)
            return os.fdopen(descriptor, 'a', encoding='utf-8')
        except BaseException:
            os.close(descriptor)
            raise

    def record(self, event, *, state='idle', operation='preview', error=None, **ignored):
        # Never serialize arbitrary messages, request data, exceptions or profile metadata.
        row = {'time_utc': datetime.now(timezone.utc).isoformat(),
               'event': event if event in EVENTS else 'failed',
               'state': state if state in STATES else 'fault',
               'operation': operation if operation in OPERATIONS else 'preview',
               'error': error if error in ERRORS else ('client_error' if error is not None else None)}
        if event == 'heartbeat_expired':
            for key in ('heartbeat_age_seconds', 'tick_gap_seconds'):
                value = ignored.get(key)
                if type(value) in (int, float) and math.isfinite(value):
                    row[key] = round(max(-86400, min(86400, value)), 3)
        line = json.dumps(row, separators=(',', ':')) + '\n'
        with self.lock:
            if self.path.stat().st_size + len(line.encode('utf-8')) > self.max_bytes:
                os.replace(self.path, self.path.with_name(self.path.name + '.1'))
            with self._open() as output:
                output.write(line)
