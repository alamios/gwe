# SPDX-License-Identifier: GPL-3.0-or-later
"""Authenticate a socket-activated desktop session without interactive privilege escalation."""
import os
from pathlib import Path
import socket
import stat
import struct


def activated_listener(path, uid):
    if os.environ.get('LISTEN_PID') != str(os.getpid()) or os.environ.get('LISTEN_FDS') != '1':
        raise RuntimeError('Exactly one systemd activation descriptor is required')
    listener = socket.socket(fileno=os.dup(3))
    try:
        info = Path(path).lstat()
        if (listener.family != socket.AF_UNIX or listener.type != socket.SOCK_SEQPACKET
                or listener.getsockname() != str(path)
                or not listener.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN)
                or not stat.S_ISSOCK(info.st_mode) or info.st_uid != uid
                or stat.S_IMODE(info.st_mode) != 0o600):
            raise RuntimeError('Unexpected activation socket')
        listener.settimeout(5)
        peer, _ = listener.accept()
        try:
            pid, actual_uid, _ = struct.unpack('3i', peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if actual_uid != uid or pid <= 1:
                raise PermissionError('Unauthorized desktop peer')
        except BaseException:
            peer.close()
            raise
        return listener, peer, pid
    except BaseException:
        listener.close()
        raise
