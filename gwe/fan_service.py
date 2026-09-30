# SPDX-License-Identifier: GPL-3.0-or-later
"""Local fan-service boundary with asynchronous supervised backend support."""
import json
import os
from pathlib import Path
import selectors
import socket
import stat
import struct
import time

from gwe.fan_curve import FanCurve

MAX_PACKET = 4096


def boot_time():
    return time.clock_gettime(time.CLOCK_BOOTTIME)


def decode(packet):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate field')
            result[key] = value
        return result
    if len(packet) > MAX_PACKET:
        raise ValueError('Oversized request')
    request = json.loads(packet, object_pairs_hook=pairs,
                         parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite value')))
    if not isinstance(request, dict) or type(request.get('version')) is not int or request['version'] != 1:
        raise ValueError('Unsupported protocol')
    op = request.get('op')
    fields = {'version', 'op', 'points', 'hysteresis', 'vbios_silent'} if op == 'acquire' else {'version', 'op'}
    if op not in ('status', 'acquire', 'renew', 'release') or set(request) != fields:
        raise ValueError('Unknown operation or fields')
    if op == 'acquire':
        points = request['points']
        if not isinstance(points, list) or not 1 <= len(points) <= 32:
            raise ValueError('Invalid curve size')
        request['curve'] = FanCurve(points, request['hysteresis'], request['vbios_silent'])
    return request


class Lease:
    """One connection owns a renewable lease; faults never silently rearm."""
    def __init__(self, backend, clock=boot_time):
        self.backend, self.clock = backend, clock
        self.owner = None
        self.deadline = None
        self.state = 'idle'

    def stop(self):
        self.owner = self.deadline = None
        try:
            self.backend.stop()
        except Exception:
            self.state = 'recovery_failed'
            return False
        self.state = getattr(self.backend, 'state', 'idle')
        return self.state not in ('fault', 'recovery_failed')

    def expire(self):
        poll = getattr(self.backend, 'poll', None)
        if poll is not None:
            state = poll()
            if self.state not in ('fault', 'recovery_failed'):
                self.state = state
            if state in ('idle', 'fault', 'recovery_failed'):
                self.owner = self.deadline = None
        if self.owner is not None and self.clock() >= self.deadline:
            self.stop()

    def disconnect(self, connection):
        if self.owner is connection:
            self.stop()

    def request(self, connection, request):
        self.expire()  # A late renewal cannot revive an expired lease.
        op = request['op']
        if op == 'status':
            return {'ok': True, 'state': self.state, 'owned': self.owner is connection}
        if self.state in ('fault', 'recovery_failed'):
            return {'ok': False, 'error': self.state}
        if op == 'acquire':
            if self.owner is not None or self.state != 'idle':
                return {'ok': False, 'error': 'busy'}
            try:
                self.backend.start(request['curve'])
            except Exception:
                if self.stop():
                    self.state = 'fault'
                return {'ok': False, 'error': self.state}
            self.owner, self.deadline = connection, self.clock() + 5
            self.state = getattr(self.backend, 'state', 'active')
            return {'ok': True, 'lease_seconds': 5, 'state': self.state}
        if self.owner is not connection:
            return {'ok': False, 'error': 'not_owner'}
        if op == 'renew':
            self.deadline = self.clock() + 5
            renew = getattr(self.backend, 'renew', None)
            if renew is not None:
                try:
                    renew(self.deadline)
                except Exception:
                    self.stop()
                    return {'ok': False, 'error': 'worker_unavailable'}
            return {'ok': True, 'lease_seconds': 5}
        return {'ok': self.stop(), 'state': self.state}


class FanService:
    """Linux SOCK_SEQPACKET transport with kernel peer credentials and bounded I/O.

    Caller owns lifecycle/event-loop scheduling. Production root-to-user socket
    provisioning uses an explicitly supplied root-owned runtime directory.
    """
    def __init__(self, path, backend, *, allowed_uid, clock=boot_time, provision=False):
        self.path = Path(path)
        parent = self.path.parent.stat()
        if type(allowed_uid) is not int or allowed_uid < 0:
            raise ValueError('Invalid allowed UID')
        expected_mode = 0o711 if provision else 0o700
        if provision and os.geteuid() != 0:
            raise PermissionError('Only root may provision a desktop socket')
        if parent.st_uid != os.geteuid() or stat.S_IMODE(parent.st_mode) != expected_mode:
            raise ValueError('Socket directory ownership or mode mismatch')
        self.allowed_uid = allowed_uid
        self.lease = Lease(backend, clock)
        self.selector = selectors.DefaultSelector()
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        try:
            self.listener.bind(str(self.path))  # Never remove or replace an existing endpoint.
        except BaseException:
            self.listener.close()
            self.selector.close()
            raise
        self.inode = self.path.stat().st_ino
        os.chmod(self.path, 0o600)
        if provision:
            os.chown(self.path, allowed_uid, -1)
        self.listener.listen(8)
        self.listener.setblocking(False)
        self.selector.register(self.listener, selectors.EVENT_READ)
        self.clients = set()

    def _drop(self, client):
        self.lease.disconnect(client)
        self.clients.discard(client)
        self.selector.unregister(client)
        client.close()

    def step(self, timeout=0.1):
        self.lease.expire()
        for key, _ in self.selector.select(min(max(timeout, 0), 0.1)):
            self.lease.expire()
            client = key.fileobj
            if client is self.listener:
                peer, _ = self.listener.accept()
                uid = struct.unpack('3i', peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[1]
                if uid != self.allowed_uid or len(self.clients) >= 8:
                    peer.close()
                    continue
                peer.setblocking(False)
                self.clients.add(peer)
                self.selector.register(peer, selectors.EVENT_READ)
                continue
            try:
                packet = client.recv(MAX_PACKET + 1)
                if not packet:
                    self._drop(client)
                    continue
                try:
                    request = decode(packet)
                    response = self.lease.request(client, request)
                except (ValueError, TypeError, OverflowError, RecursionError):
                    # Malformed owner traffic terminates its lease, not just the request.
                    self.lease.disconnect(client)
                    response = {'ok': False, 'error': 'invalid_request'}
                data = json.dumps(response, allow_nan=False).encode()
                if client.send(data) != len(data):
                    self._drop(client)
            except (ConnectionError, OSError):
                if client in self.clients:
                    self._drop(client)
        self.lease.expire()

    def close(self):
        for client in tuple(self.clients):
            self._drop(client)
        self.listener.close()
        self.selector.close()
        if self.path.exists() and self.path.stat().st_ino == self.inode:
            self.path.unlink()


class FanClient:
    """Unprivileged persistent connection; close relinquishes its lease."""
    def __init__(self, path):
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.socket.settimeout(2)
        try:
            self.socket.connect(str(path))
        except BaseException:
            self.socket.close()
            raise

    def request(self, op, **fields):
        packet = json.dumps({'version': 1, 'op': op, **fields}, allow_nan=False).encode()
        if len(packet) > MAX_PACKET:
            raise ValueError('Oversized request')
        self.socket.sendall(packet)
        return json.loads(self.socket.recv(MAX_PACKET + 1))

    def close(self):
        self.socket.close()
