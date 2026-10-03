# SPDX-License-Identifier: GPL-3.0-or-later
"""Nonblocking bounded power worker and separate rollback process."""
import multiprocessing
import time

from gwe.nvml_power import PowerError, PowerRecord, apply, recover


def nvml_factory():
    import pynvml
    return pynvml


def worker(channel, factory, directory, uuid, requested, expected):
    try:
        result = apply(factory(), PowerRecord(directory), uuid, requested, expected)
    except BaseException as error:
        code = str(error) if isinstance(error, PowerError) else 'driver_error'
        result = {'state': 'failed', 'error': code}
    try:
        channel.send(result)
    finally:
        channel.close()


def recovery_worker(channel, factory, directory, uuid, trial=False):
    try:
        from gwe.power_trial import TrialRecord
        result = recover(factory(), (TrialRecord if trial else PowerRecord)(directory), uuid)
    except BaseException:
        result = {'state': 'fault', 'error': 'recovery_failed'}
    try:
        channel.send(result)
    finally:
        channel.close()


class PowerBackend:
    def __init__(self, uuid, directory, *, factory=nvml_factory, context=None,
                 clock=time.monotonic, timeout=3):
        self.uuid, self.directory, self.factory = uuid, str(directory), factory
        self.context = context or multiprocessing.get_context('spawn')
        self.clock, self.timeout = clock, timeout
        self.process = self.channel = None
        self.deadline = 0
        self.kill_deadline = None
        self.recovering = False
        self.result = {'state': 'idle'}
        self.operation_id = 0

    @property
    def busy(self):
        return self.process is not None

    def status(self):
        self.poll()
        return {'ok': True, 'gpu_uuid': self.uuid, 'operation_id': self.operation_id,
                'trial_active': (PowerRecord(self.directory).directory / 'power-trial.json').exists(),
                **self.result}

    def _spawn(self, target, *args):
        parent, child = self.context.Pipe(duplex=False)
        process = self.context.Process(target=target, args=(child, self.factory, self.directory, self.uuid, *args))
        try:
            process.start()
        except BaseException:
            parent.close()
            child.close()
            raise
        child.close()
        self.process, self.channel = process, parent
        self.kill_deadline = None
        self.deadline = self.clock() + (5 if self.recovering else self.timeout)

    def start(self, requested, expected):
        self.poll()
        if self.busy or self.result['state'] == 'fault':
            return {'ok': False, 'error': 'power_busy'}
        if PowerRecord(self.directory).pending.exists():
            self.result = {'state': 'fault', 'error': 'recovery_pending'}
            return {'ok': False, 'error': 'recovery_pending'}
        from gwe.power_trial import TrialRecord
        trial = TrialRecord(self.directory)
        if trial.pending.exists():
            try:
                guard = trial.read(trial.pending)
                if (guard['gpu_uuid'] != self.uuid or guard['outcome'] != 'pending'
                        or requested not in (guard['previous_mw'], guard['requested_mw'])
                        or expected not in (guard['previous_mw'], guard['requested_mw'])):
                    return {'ok': False, 'error': 'trial_guard_active'}
            except Exception:
                self.result = {'state': 'fault', 'error': 'invalid_trial_guard'}
                return {'ok': False, 'error': 'recovery_pending'}
        self.operation_id += 1
        self.result = {'state': 'busy'}
        try:
            self._spawn(worker, requested, expected)
        except Exception:
            self.result = {'state': 'failed', 'error': 'worker_unavailable'}
        return self.status()

    def _dispose(self):
        self.process.join(0)
        self.process.close()
        self.channel.close()
        self.process = self.channel = None

    def poll(self):
        if not self.busy:
            return
        if self.process.is_alive():
            if self.clock() < self.deadline:
                return
            if self.kill_deadline is None:
                self.process.kill()
                self.kill_deadline = self.clock() + 2
            elif self.clock() >= self.kill_deadline:
                self.result = {'state': 'fault', 'error': 'worker_stuck'}
            # Reap on a later tick; never block the fan supervisor or watchdog.
            return
        try:
            result = self.channel.recv() if self.channel.poll() else {'state': 'failed', 'error': 'worker_lost'}
        except (EOFError, OSError):
            result = {'state': 'failed', 'error': 'worker_lost'}
        self._dispose()
        record = PowerRecord(self.directory)
        if self.recovering:
            self.recovering = False
            self.result = result if not record.pending.exists() and result['state'] in ('idle', 'rolled_back') else {
                'state': 'fault', 'error': 'recovery_failed'}
        elif record.pending.exists():
            self.recovering = True
            self.result = {'state': 'busy', 'error': 'restoring_previous'}
            try:
                self._spawn(recovery_worker)
            except Exception:
                self.result = {'state': 'fault', 'error': 'recovery_failed'}
        else:
            self.result = result

    def close(self):
        # systemd ExecStopPost handles any pending journal after cgroup death.
        if self.busy:
            if self.process.is_alive():
                self.process.kill()
            self.process.join(2)
            if self.process.is_alive():
                raise PowerError('worker_stuck')
            self._dispose()
