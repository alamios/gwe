# SPDX-License-Identifier: GPL-3.0-or-later
"""Serialize continuous fan requests and lease renewal independently of GTK."""
from concurrent.futures import Future
from queue import Empty, Queue
from threading import Thread


class FanSessionWorker:
    """One socket owner; UI commands and periodic renewals never overlap.

    The privileged worker supplies and validates its own thermal telemetry. A
    delayed GTK frame must not stop that worker. A stopped desktop process still
    cannot renew: the existing service lease, pidfd and watchdog cover its loss.
    """
    def __init__(self, session):
        self.session = session
        self.commands = Queue()
        self.stopping = False
        self.thread = Thread(target=self._run, name='gwe-fan-session')
        self.thread.start()

    def submit(self, operation, *arguments):
        if self.stopping:
            raise RuntimeError('Fan session worker is closed')
        future = Future()
        self.commands.put((future, operation, arguments))
        return future

    def _run(self):
        next_tick = self.session.clock()
        try:
            while True:
                timeout = max(0, min(1, next_tick - self.session.clock()))
                try:
                    command = self.commands.get(timeout=timeout)
                except Empty:
                    command = ()
                if command is None:
                    return
                future = None
                if command:
                    future, operation, arguments = command
                    if not future.set_running_or_notify_cancel():
                        future = None
                    else:
                        try:
                            operation(*arguments)
                        except Exception as error:
                            self.session._fail(error)
                # Check after every command, too: a busy queue cannot starve
                # renewals. Complete transition futures after their first poll.
                now = self.session.clock()
                if now >= next_tick or future is not None:
                    self.session.tick(now)
                    next_tick = self.session.clock() + 1
                if future is not None:
                    future.set_result(None)
        finally:
            self.session.close()

    def shutdown(self, wait=True):
        if not self.stopping:
            self.stopping = True
            self.commands.put(None)
        if wait:
            self.thread.join()
