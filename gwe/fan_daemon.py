# SPDX-License-Identifier: GPL-3.0-or-later
"""Experimental, explicitly installed system service. No autoloaded profiles."""
import argparse
import fcntl
import json
import multiprocessing
import os
from pathlib import Path
import re
import signal
import socket
import stat
import subprocess
import time

from gwe.fan_process import ProcessBackend, nvml_factory, recover_worker
from gwe.fan_service import FanService, boot_time

RUNTIME = Path('/run/gwe-fan-service')
UUID_PATTERN = re.compile(r'GPU-[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}')


def trusted(path):
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError('An absolute non-symlink path is required')
    for component in (path, *path.parents):
        info = component.stat()
        if info.st_uid != 0 or info.st_mode & 0o022:
            raise PermissionError('Service files must be root-owned and not writable by others')
    return path


def load_config(path):
    path = trusted(path)
    if not stat.S_ISREG(path.stat().st_mode) or path.stat().st_size > 4096:
        raise ValueError('Invalid configuration file')
    config = json.loads(path.read_text())
    if set(config) != {'version', 'allowed_uid', 'gpu_uuid'} or type(config['version']) is not int or config['version'] != 1:
        raise ValueError('Invalid configuration schema')
    if type(config['allowed_uid']) is not int or config['allowed_uid'] <= 0:
        raise ValueError('A non-root desktop UID is required')
    if not isinstance(config['gpu_uuid'], str) or not UUID_PATTERN.fullmatch(config['gpu_uuid']):
        raise ValueError('Invalid GPU UUID')
    return config


class OwnershipRecord:
    def __init__(self, path, uuid):
        self.path, self.uuid = Path(path), uuid

    def record(self, fans):
        # Written before acknowledging permission for the first native setter.
        descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w') as output:
            json.dump({'version': 1, 'gpu_uuid': self.uuid, 'fans': list(fans)}, output)
            output.flush()
            os.fsync(output.fileno())

    def clear(self):
        self.path.unlink(missing_ok=True)


def notify(message):
    address = os.environ.get('NOTIFY_SOCKET')
    if not address:
        return
    if address.startswith('@'):
        address = '\0' + address[1:]
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as channel:
        channel.settimeout(.2)
        channel.connect(address)
        channel.sendall(message.encode())


def recover_record(path):
    if not path.exists():
        return
    trusted(path)
    if not stat.S_ISREG(path.stat().st_mode) or path.stat().st_size > 4096:
        raise ValueError('Invalid recovery record')
    record = json.loads(path.read_text())
    fans = record.get('fans')
    if (record.get('version') != 1 or not isinstance(fans, list) or not 1 <= len(fans) <= 32
            or any(type(fan) is not int for fan in fans) or fans != list(range(len(fans)))
            or not isinstance(record.get('gpu_uuid'), str) or not UUID_PATTERN.fullmatch(record['gpu_uuid'])):
        raise ValueError('Invalid recovery record')
    process = multiprocessing.get_context('spawn').Process(
        target=recover_worker, args=(nvml_factory, record['gpu_uuid'], tuple(fans)))
    process.start()
    process.join(5)
    if process.is_alive():
        process.kill()
        process.join(2)
        raise RuntimeError('Recovery timed out; ownership record retained')
    if process.exitcode != 0:
        raise RuntimeError('Recovery failed; ownership record retained')
    process.close()
    path.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('run', 'recover', 'check'))
    parser.add_argument('--config', default='/etc/gwe-fan-service.json')
    args = parser.parse_args(argv)
    if os.geteuid() != 0:
        parser.error('This installed service requires root')
    lock = None
    try:
        if args.action != 'check' and RUNTIME.exists():
            trusted(RUNTIME)
            lock = os.open(RUNTIME / 'service.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action == 'recover':
            # Called only after systemd has stopped the entire service cgroup.
            recover_record(RUNTIME / 'owned.json')
            return 0
        config = load_config(args.config)
        if args.action == 'check':
            print('Configuration valid; no NVML calls performed')
            return 0
        trusted(RUNTIME)
        if stat.S_IMODE(RUNTIME.stat().st_mode) != 0o711:
            raise ValueError('Unexpected runtime directory permissions')
        # Do not stop cooling services implicitly. Operator arranges exclusivity.
        result = subprocess.run(['systemctl', 'is-active', 'coolercontrold.service'], capture_output=True, timeout=2)
        if result.returncode != 3 or result.stdout.strip() not in (b'inactive', b'failed'):
            raise RuntimeError('CoolerControl must be confirmed stopped before starting')
        # Process names provide an additional guard, not a global GPU ownership lock.
        for entry in Path('/proc').iterdir():
            if entry.name.isdigit():
                try:
                    name = (entry / 'comm').read_text().strip().lower()
                except (FileNotFoundError, ProcessLookupError):
                    continue
                if name in ('gwe', 'fancontrol', 'nvfancontrol'):
                    raise RuntimeError('Another fan controller is running')
        record = OwnershipRecord(RUNTIME / 'owned.json', config['gpu_uuid'])
        if record.path.exists():
            raise RuntimeError('Unresolved recovery record; refusing new control')
        endpoint = RUNTIME / 'control.sock'
        if endpoint.exists():
            if not stat.S_ISSOCK(endpoint.lstat().st_mode):
                raise RuntimeError('Unexpected existing endpoint')
            endpoint.unlink()  # Root-owned parent, only after an old service has stopped.
        backend = ProcessBackend(config['gpu_uuid'], record=record.record, clear=record.clear)
        service = FanService(endpoint, backend, allowed_uid=config['allowed_uid'], provision=True)
        stopping = False
        def stop(signum, frame):
            nonlocal stopping
            stopping = True
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, stop)
        try:
            notify('READY=1')
            expires = boot_time() + 60
            last_notify = 0
            while not stopping and boot_time() < expires:
                service.step()
                if backend.state == 'recovery_failed':
                    raise RuntimeError('Backend recovery failed')
                if boot_time() - last_notify >= 1:
                    notify('WATCHDOG=1')
                    last_notify = boot_time()
        finally:
            service.close()
            if not backend.close():
                raise RuntimeError('Backend shutdown recovery failed')
        return 0
    except Exception as error:
        # Do not expose private configuration, UUID or underlying driver messages.
        print(f'Service failed: {type(error).__name__}', flush=True)
        return 1
    finally:
        if lock is not None:
            os.close(lock)


if __name__ == '__main__':
    raise SystemExit(main())
