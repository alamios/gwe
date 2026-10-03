# SPDX-License-Identifier: GPL-3.0-or-later
"""Installation-time desktop authorization. Never call a GPU setter or start a controller."""
import json
import os
from pathlib import Path
import pwd
import stat
import tempfile

OWNER_OVERRIDE = Path('/etc/systemd/system/gwe-fan-service.socket.d/10-owner.conf')


def configure(config_path, uid=None):
    from gwe.fan_daemon import load_config, trusted
    path = Path(config_path)
    if path.exists() or path.is_symlink():
        config = load_config(path)  # Preserve an existing pinned authorization.
    else:
        if type(uid) is not int or uid <= 0:
            raise ValueError('Install from the desktop user with sudo, or supply its UID explicitly')
        account = pwd.getpwuid(uid)
        if account.pw_uid < 1000:
            raise ValueError('A desktop account is required')
        config = dict(version=1, allowed_uid=uid)
    # Validate an existing override before any configuration/identity work or write.
    expected = '[Socket]\nSocketUser=' + str(config['allowed_uid']) + '\n'
    if OWNER_OVERRIDE.exists() or OWNER_OVERRIDE.is_symlink():
        trusted(OWNER_OVERRIDE)
        info = OWNER_OVERRIDE.stat()
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 128
                or OWNER_OVERRIDE.read_text() != expected):
            raise ValueError('Unrecognized socket authorization override; review it explicitly')
    if not path.exists():
        import pynvml
        pynvml.nvmlInit()
        try:
            if pynvml.nvmlDeviceGetCount() != 1:
                raise ValueError('Configure a GPU explicitly when more than one GPU is present')
            uuid = pynvml.nvmlDeviceGetUUID(pynvml.nvmlDeviceGetHandleByIndex(0))
            if isinstance(uuid, bytes):
                uuid = uuid.decode('ascii')
        finally:
            pynvml.nvmlShutdown()
        config = dict(version=1, allowed_uid=uid, gpu_uuid=uuid)
        # Validate before committing a private installation-generated configuration.
        from gwe.fan_daemon import UUID_PATTERN
        if not UUID_PATTERN.fullmatch(uuid):
            raise ValueError('Unexpected NVML identity')
        trusted(path.parent)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as target:
            json.dump(config, target)
            target.flush()
            os.fsync(target.fileno())
    directory = OWNER_OVERRIDE.parent
    directory.mkdir(mode=0o755, exist_ok=True)
    trusted(directory)
    fd, temporary = tempfile.mkstemp(prefix='.gwe-owner-', dir=directory)
    try:
        with os.fdopen(fd, 'w') as target:
            target.write(expected)
            target.flush()
            os.fsync(target.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, OWNER_OVERRIDE)
    finally:
        Path(temporary).unlink(missing_ok=True)
    print('Desktop authorization configured; no GPU settings changed')
