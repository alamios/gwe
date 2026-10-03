# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded process supervision independent of NVML and GTK."""

import multiprocessing
import math
import signal
import time


class SupervisorError(RuntimeError):
    pass


def supervise(target, args, recover, *, heartbeat_seconds=5, total_seconds=20,
              inject_signal=None, emit=lambda message: None):
    """Worker sends a tick only after verified control and done after cleanup.

    The caller must install SIGTERM/SIGINT handlers that raise in the supervisor.
    Recovery runs after the worker stops, never concurrently with manual writes.
    Native recovery can itself hang; production service supervision remains required.
    """
    if (not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
                for v in (heartbeat_seconds, total_seconds))
            or heartbeat_seconds <= 0 or total_seconds <= heartbeat_seconds):
        raise ValueError("Invalid supervision deadlines")
    if inject_signal not in (None, signal.SIGTERM, signal.SIGKILL, signal.SIGSTOP):
        raise ValueError("Unsupported fault injection")
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    worker = context.Process(target=target, args=(sender, *args))
    injected = False
    done = False
    ticks = 0
    outcome = None
    started = time.monotonic()
    deadline = started + heartbeat_seconds
    try:
        worker.start()
        sender.close()
        while True:
            now = time.monotonic()
            if now - started >= total_seconds:
                raise SupervisorError("Total experiment deadline exceeded")
            if now >= deadline:
                if injected and inject_signal == signal.SIGSTOP:
                    outcome = "stalled_worker_detected"
                    break
                raise SupervisorError("Worker heartbeat expired")
            if receiver.poll(min(0.05, max(0, deadline - now))):
                try:
                    message = receiver.recv()
                except EOFError:
                    break
                if not isinstance(message, dict):
                    raise SupervisorError("Invalid worker message")
                if message.get("event") == "tick":
                    ticks += 1
                    emit(message)
                    if not injected:
                        deadline = time.monotonic() + heartbeat_seconds
                    if inject_signal is not None and not injected and ticks >= 2:
                        import os
                        os.kill(worker.pid, inject_signal)
                        injected = True
                elif message.get("event") == "done":
                    done = True
                else:
                    raise SupervisorError("Worker reported a failure")
            elif not worker.is_alive():
                break
        worker.join(0.2)
        if outcome is None:
            if injected and inject_signal in (signal.SIGTERM, signal.SIGKILL):
                if worker.is_alive() or worker.exitcode == 0:
                    raise SupervisorError("Injected termination did not stop worker")
                outcome = "terminated_worker_detected"
            elif not done or worker.exitcode != 0:
                raise SupervisorError("Worker exited without successful cleanup")
            else:
                outcome = "completed"
        return {"outcome": outcome, "ticks": ticks, "injected": injected}
    finally:
        handlers = {sig: signal.signal(sig, signal.SIG_IGN) for sig in (signal.SIGINT, signal.SIGTERM)}
        try:
            if worker.pid is not None and worker.is_alive():
                worker.kill()
                worker.join(3)
                if worker.is_alive():
                    raise SupervisorError("Worker still alive; manual operator recovery required")
            recover()
        finally:
            sender.close()
            receiver.close()
            for sig, handler in handlers.items():
                signal.signal(sig, handler)
