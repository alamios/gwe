# SPDX-License-Identifier: GPL-3.0-or-later
"""Nonblocking process adapter: native calls never run in the socket service."""
import json
import multiprocessing
import signal
import socket
import time

from gwe.fan_service import boot_time
from gwe.nvml_fan_control import NvmlFanController


def nvml_factory():
    import pynvml
    return pynvml


def send(channel, message):
    data = json.dumps(message, allow_nan=False).encode()
    if channel.send(data) != len(data):
        raise RuntimeError('Incomplete internal message')


def receive(channel):
    try:
        data = channel.recv(1024)
    except BlockingIOError:
        return None
    if not data:
        raise EOFError('Supervisor disconnected')
    return json.loads(data)


def interrupted(signum, frame):
    raise RuntimeError('Control process interrupted')


def control_worker(channel, factory, uuid, curve, deadline, ceiling):
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    nvml = factory()
    controller = None
    initialized = False
    failed = False
    try:
        nvml.nvmlInit()
        initialized = True
        controller = NvmlFanController(nvml, uuid, curve, clock=boot_time, temperature_ceiling=ceiling)

        def own(fans):
            # No native write before the service records ownership and acknowledges it.
            send(channel, {'event': 'owned', 'fans': list(fans)})
            limit = boot_time() + 1
            while boot_time() < min(limit, deadline):
                message = receive(channel)
                if message == {'op': 'go'}:
                    return
                if message is not None:
                    raise RuntimeError('Unexpected ownership response')
                time.sleep(0.01)
            raise RuntimeError('Ownership acknowledgement expired')

        if boot_time() >= deadline:
            raise RuntimeError('Initial lease expired')
        controller.start(on_owned=own)
        next_tick = boot_time()
        while boot_time() < deadline:
            for _ in range(16):
                message = receive(channel)
                if message is None:
                    break
                if message.get('op') != 'renew':
                    raise RuntimeError('Unexpected worker command')
                # Late commands never revive an already expired lease.
                if boot_time() >= deadline:
                    break
                deadline = min(float(message['deadline']), boot_time() + 5)
            if boot_time() >= deadline:
                break
            if boot_time() >= next_tick:
                result = controller.tick()
                send(channel, {'event': 'tick', **result})
                next_tick = boot_time() + 1
            time.sleep(0.02)
    except BaseException:
        failed = True
    finally:
        try:
            if controller is not None:
                controller.stop()
        except BaseException:
            failed = True
        if initialized:
            try:
                nvml.nvmlShutdown()
            except BaseException:
                failed = True
        try:
            send(channel, {'event': 'fault' if failed else 'done'})
        except (OSError, EOFError):
            pass
        channel.close()


def recover_worker(factory, uuid, fans):
    """Bounded by the parent; never selects a device by index."""
    nvml = factory()
    nvml.nvmlInit()
    failures = []
    try:
        for fan in fans:
            try:
                handle = nvml.nvmlDeviceGetHandleByUUID(uuid)
                if nvml.nvmlDeviceGetUUID(handle) != uuid:
                    raise RuntimeError('Identity mismatch')
                nvml.nvmlDeviceSetDefaultFanSpeed_v2(handle, fan)
            except Exception:
                failures.append(fan)
        for fan in fans:
            try:
                handle = nvml.nvmlDeviceGetHandleByUUID(uuid)
                if (nvml.nvmlDeviceGetUUID(handle) != uuid or
                        nvml.nvmlDeviceGetFanControlPolicy_v2(handle, fan) != nvml.NVML_FAN_POLICY_TEMPERATURE_CONTINOUS_SW):
                    failures.append(fan)
            except Exception:
                failures.append(fan)
    finally:
        nvml.nvmlShutdown()
    if failures:
        raise SystemExit(1)


class ProcessBackend:
    """start/stop queue work; poll advances it. idle means verified recovery.

    A dead service is covered by worker EOF/lease expiry while native calls remain
    responsive; systemd cgroup teardown and ExecStopPost cover service failure.
    """
    def __init__(self, uuid, *, factory=nvml_factory, ceiling=60, heartbeat=5,
                 recovery_timeout=5, record=lambda fans: None, clear=lambda: None,
                 active_clock=time.monotonic):
        self.uuid, self.factory, self.ceiling = uuid, factory, ceiling
        self.heartbeat, self.recovery_timeout = heartbeat, recovery_timeout
        self.record, self.clear = record, clear
        self.context = multiprocessing.get_context('spawn')
        self.state = 'idle'
        self.worker = self.recovery = self.channel = None
        self.fans = ()
        self.failure = False
        self.acknowledged = False
        self.finished = self.unexpected_exit = False
        self.deadline = 0
        self.stop_deadline = 0
        self.recovery_deadline = 0
        self.active_clock = active_clock
        self.last_poll_boot = boot_time()
        self.last_poll_active = active_clock()

    def start(self, curve):
        if self.state != 'idle':
            raise RuntimeError('Backend is not idle')
        self.fans, self.failure, self.acknowledged = (), False, False
        self.finished = self.unexpected_exit = False
        parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        parent.setblocking(False)
        child.setblocking(False)
        self.channel = parent
        self.worker = self.context.Process(target=control_worker, args=(
            child, self.factory, self.uuid, curve, boot_time() + 5, self.ceiling))
        try:
            self.worker.start()
        except BaseException:
            parent.close()
            self.channel = None
            self.worker = None
            self.state = 'fault'
            raise
        finally:
            child.close()
        self.state = 'starting'
        self.deadline = boot_time() + self.heartbeat

    def renew(self, deadline):
        if self.state not in ('starting', 'active'):
            raise RuntimeError('Backend is not active')
        # Initial renewal may precede ownership handshake; the initial lease is already five seconds.
        if self.acknowledged:
            try:
                send(self.channel, {'op': 'renew', 'deadline': deadline})
            except OSError:
                self.failure = True
                self.stop()
                raise RuntimeError('Worker unavailable') from None

    def _drain(self):
        if self.channel is None:
            return
        for _ in range(32):
            try:
                message = receive(self.channel)
            except (EOFError, OSError, ValueError):
                return
            if message is None:
                break
            event = message.get('event')
            if event == 'owned':
                fans = message.get('fans')
                if not isinstance(fans, list) or not 1 <= len(fans) <= 32 or fans != list(range(len(fans))):
                    self.failure = True
                    self.stop()
                    return
                self.fans = tuple(fans)
                if self.state == 'starting':
                    try:
                        self.record(self.fans)
                        send(self.channel, {'op': 'go'})
                        self.acknowledged = True
                    except Exception:
                        self.failure = True
                        self.stop()
            elif event == 'tick' and self.state in ('starting', 'active'):
                self.state = 'active'
                self.deadline = boot_time() + self.heartbeat
            elif event == 'fault':
                self.failure = True
            elif event == 'done':
                self.finished = True

    def stop(self):
        if self.state in ('idle', 'fault', 'recovery_failed', 'stopping'):
            return
        self.state = 'stopping'
        self.stop_deadline = boot_time() + 3
        if self.worker is not None and self.worker.is_alive():
            self.worker.kill()

    def poll(self):
        now = boot_time()
        active_now = self.active_clock()
        suspended = now - self.last_poll_boot - (active_now - self.last_poll_active) >= 1
        self.last_poll_boot, self.last_poll_active = now, active_now
        self._drain()
        if suspended and self.state in ('starting', 'active'):
            # Resume ends the old writer and verifies recovery. It does not
            # grant a new lease or clear a driver fault already seen by _drain.
            self.stop()
        if self.state in ('starting', 'active'):
            if not self.worker.is_alive():
                self.unexpected_exit = True
                self.stop()
            elif now >= self.deadline or self.failure:
                self.failure = True
                self.stop()
        if self.state == 'stopping':
            if self.worker is not None:
                if self.worker.is_alive():
                    if now >= self.stop_deadline:
                        self.state = 'recovery_failed'
                    return self.state
                self.worker.join(0)
                self._drain()  # Capture ownership/completion sent immediately before exit.
                if self.unexpected_exit and not self.finished:
                    self.failure = True
                self.worker.close()
                self.worker = None
                self.channel.close()
                self.channel = None
                if self.fans and self.acknowledged:
                    self.recovery = self.context.Process(target=recover_worker, args=(self.factory, self.uuid, self.fans))
                    try:
                        self.recovery.start()
                    except Exception:
                        self.recovery = None
                        self.state = 'recovery_failed'
                        return self.state
                    self.recovery_deadline = now + self.recovery_timeout
            if self.recovery is not None:
                if self.recovery.is_alive():
                    if now >= self.recovery_deadline:
                        self.recovery.kill()
                        self.failure = True
                        # Do not release ownership or start a new writer until it exits.
                        self.state = 'recovery_failed'
                    return self.state
                self.recovery.join(0)
                success = self.recovery.exitcode == 0
                self.recovery.close()
                self.recovery = None
                if not success:
                    self.state = 'recovery_failed'
                    return self.state
            try:
                self.clear()
            except Exception:
                self.state = 'recovery_failed'
                return self.state
            self.state = 'fault' if self.failure else 'idle'
        return self.state

    def close(self, timeout=10):
        self.stop()
        limit = time.monotonic() + timeout
        while self.state == 'stopping' and time.monotonic() < limit:
            self.poll()
            time.sleep(0.01)
        if self.state == 'stopping':
            self.state = 'recovery_failed'
        for process in (self.worker, self.recovery):
            if process is not None:
                if process.is_alive():
                    process.kill()
                process.join(0.2)
        if self.channel is not None:
            self.channel.close()
        return self.state != 'recovery_failed'
