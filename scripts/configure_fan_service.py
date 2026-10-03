#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Replace only the installed placeholder configuration; no GPU setters or service start."""
import json
import os
from pathlib import Path
import pwd
import runpy
import stat
import tempfile

PLACEHOLDER = {'version': 1, 'allowed_uid': 0, 'gpu_uuid': 'REPLACE_WITH_LOCAL_GPU_UUID'}


def configuration(current, uid, nvml):
    if current != PLACEHOLDER:
        raise ValueError('Configuration is already populated or differs from the template')
    if type(uid) is not int or uid <= 0:
        raise ValueError('Run sudo from the intended non-root desktop account')
    nvml.nvmlInit()
    try:
        if nvml.nvmlDeviceGetCount() != 1:
            raise ValueError('Expected exactly one GPU; explicit selection needs review')
        handle = nvml.nvmlDeviceGetHandleByIndex(0)
        if nvml.nvmlDeviceGetName(handle) != 'NVIDIA GeForce RTX 3090 Ti':
            raise ValueError('Unexpected GPU model')
        if nvml.nvmlDeviceGetNumFans(handle) != 2:
            raise ValueError('Unexpected fan count')
        uuid = nvml.nvmlDeviceGetUUID(handle)
        return {'version': 1, 'allowed_uid': uid, 'gpu_uuid': uuid}
    finally:
        nvml.nvmlShutdown()


def main():
    if os.geteuid() != 0:
        raise PermissionError('Run with sudo from the intended desktop account')
    uid = int(os.environ.get('SUDO_UID', '0'))
    pwd.getpwuid(uid)
    # Reuse the installed entry point's ownership checks and isolated import path.
    runpy.run_path('/opt/gwe-fan-service/entry.py', run_name='installed_service_bootstrap')
    from gwe.fan_daemon import UUID_PATTERN, load_config
    import pynvml
    path = Path('/etc/gwe-fan-service.json')
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o600:
        raise PermissionError('Unexpected configuration ownership or mode')
    current = json.loads(path.read_text())
    result = configuration(current, uid, pynvml)
    if not isinstance(result['gpu_uuid'], str) or not UUID_PATTERN.fullmatch(result['gpu_uuid']):
        raise ValueError('Invalid device identity')
    descriptor, temporary = tempfile.mkstemp(prefix='.gwe-fan-config-', dir='/etc')
    try:
        with os.fdopen(descriptor, 'w') as output:
            json.dump(result, output, indent=2)
            output.write('\n')
            output.flush()
            os.fsync(output.fileno())
        # Do not replace a config edited during read-only device discovery.
        latest = path.lstat()
        fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_mode', 'st_uid')
        if any(getattr(latest, field) != getattr(info, field) for field in fields) or json.loads(path.read_text()) != current:
            raise RuntimeError('Configuration changed during discovery')
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    load_config(path)
    print('Configuration valid for the desktop user and RTX 3090 Ti; identity not displayed.')
    print('No GPU settings changed. Service not started.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        raise SystemExit(f'Configuration failed: {type(error).__name__}: {error}') from None
