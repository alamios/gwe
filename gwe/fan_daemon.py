# SPDX-License-Identifier: GPL-3.0-or-later
"""Experimental, explicitly installed system service. No autoloaded profiles."""
import argparse
import fcntl
import json
import multiprocessing
import os
from pathlib import Path
import re
import select
import signal
import socket
import stat
import subprocess
import time

from gwe.fan_process import ProcessBackend, nvml_factory, recover_worker
from gwe.fan_service import FanService, boot_time
from gwe.nvml_power import PowerRecord
from gwe.power_process import PowerBackend, recovery_worker as power_recovery_worker

RUNTIME = Path('/run/gwe-fan-service')
UUID_PATTERN = re.compile(r'GPU-[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}')
SESSION_OVERRIDE = Path('/run/systemd/system/gwe-fan-service.service.d/90-gwe-continuous.conf')
SESSION_TEMPLATE = Path('/opt/gwe-fan-service/continuous.conf')


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


def recover_power_record(trial=False):
    from gwe.power_trial import TrialRecord
    journal = (TrialRecord if trial else PowerRecord)(RUNTIME)
    path = journal.pending
    if not path.exists():
        return
    trusted(path)
    record = journal.read(path)
    if not UUID_PATTERN.fullmatch(record['gpu_uuid']):
        raise ValueError('Invalid recovery identity')
    context = multiprocessing.get_context('spawn')
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=power_recovery_worker,
                              args=(child, nvml_factory, str(RUNTIME), record['gpu_uuid'], trial))
    try:
        process.start()
        child.close()
        process.join(5)
        if process.is_alive():
            process.kill()
            process.join(2)
            raise RuntimeError('Power recovery timed out')
        if process.exitcode != 0 or path.exists():
            raise RuntimeError('Power recovery failed')
    finally:
        parent.close()
        child.close()
        if process.pid is not None and not process.is_alive():
            process.close()


def process_identity(pid):
    path = Path('/proc') / str(pid)
    return path.stat().st_uid, int((path / 'stat').read_text().rsplit(')', 1)[1].split()[19])


def session_record():
    path = RUNTIME / 'session.json'
    if not path.exists():
        return None
    trusted(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as source:
        info = os.fstat(source.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_size > 1024 or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o600):
            raise ValueError('Invalid session record')
        row = json.load(source)
    if (not isinstance(row, dict) or set(row) != {'version', 'pid', 'uid', 'start', 'cooler_active'}
            or type(row['version']) is not int or row['version'] != 1
            or any(type(row[key]) is not int or row[key] <= 0 for key in ('pid', 'uid', 'start'))
            or row['pid'] <= 1 or type(row['cooler_active']) is not bool):
        raise ValueError('Invalid session owner')
    return row


def prepare_session(pid, uid):
    if type(pid) is not int or pid <= 1:
        raise ValueError('Explicit session owner required')
    if any((RUNTIME / name).exists() for name in ('owned.json', 'power-pending.json', 'power-trial.json')):
        raise RuntimeError('GPU recovery must complete before session preparation')
    actual_uid, start = process_identity(pid)
    if actual_uid != uid:
        raise ValueError('Session owner does not match configured desktop user')
    result = subprocess.run(['systemctl', 'is-active', 'coolercontrold.service'],
                            capture_output=True, timeout=5)
    if (result.returncode, result.stdout.strip()) not in (
            (0, b'active'), (3, b'inactive'), (3, b'failed')):
        raise RuntimeError('Cannot determine previous CoolerControl state')
    PowerRecord(RUNTIME).write(RUNTIME / 'session.json', dict(
        version=1, pid=pid, uid=uid, start=start, cooler_active=result.returncode == 0), exclusive=True)


def recover_session():
    row = session_record()
    if row is None:
        return
    # Run only after all GPU journals have recovered. Never delete an unknown override.
    if SESSION_OVERRIDE.exists() or SESSION_OVERRIDE.is_symlink():
        trusted(SESSION_OVERRIDE)
        trusted(SESSION_TEMPLATE)
        if SESSION_OVERRIDE.read_bytes() != SESSION_TEMPLATE.read_bytes():
            raise RuntimeError('Unexpected session override; retain record')
        SESSION_OVERRIDE.unlink()
        subprocess.run(['systemctl', 'daemon-reload'], check=True, timeout=10)
    if row['cooler_active']:
        subprocess.run(['systemctl', 'start', 'coolercontrold.service'], check=True, timeout=10)
    (RUNTIME / 'session.json').unlink()


def session_owner(uid):
    row = session_record()
    if row is None or row['uid'] != uid:
        raise RuntimeError('Missing authenticated manual session owner')
    fd = os.pidfd_open(row['pid'])
    try:
        if process_identity(row['pid']) != (uid, row['start']):
            raise RuntimeError('Manual session owner changed')
        return fd
    except BaseException:
        os.close(fd)
        raise


def serve(service, backend, power, stopping, *, continuous=False):
    """Keep watchdog and recovery checks identical in trial and manual sessions."""
    notify('READY=1')
    expires = None if continuous else boot_time() + 60
    last_notify = 0
    while not stopping() and (expires is None or boot_time() < expires):
        service.step()
        if backend.state == 'recovery_failed' or power.result['state'] == 'fault':
            raise RuntimeError('Backend recovery failed')
        if boot_time() - last_notify >= 1:
            notify('WATCHDOG=1')
            last_notify = boot_time()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('run', 'recover', 'check', 'setup', 'prepare-power-trial', 'prepare-session'))
    parser.add_argument('--config', default='/etc/gwe-fan-service.json')
    parser.add_argument('--continuous', action='store_true', help='Manual session without the trial lifetime')
    parser.add_argument('--desktop', action='store_true', help='Authenticated systemd socket activation')
    parser.add_argument('--owner-pid', type=int, help='Desktop launcher process to supervise')
    parser.add_argument('--allowed-uid', type=int, help='Installation-time desktop account authorization')
    args = parser.parse_args(argv)
    if args.desktop:
        if args.action != 'run':
            parser.error('--desktop is valid only for run')
        args.continuous = True
    if args.continuous and args.action != 'run':
        parser.error('--continuous is valid only for run')
    if args.owner_pid is not None and args.action != 'prepare-session':
        parser.error('--owner-pid is valid only for prepare-session')
    if args.allowed_uid is not None and args.action != 'setup':
        parser.error('--allowed-uid is valid only for setup')
    if os.geteuid() != 0:
        parser.error('This installed service requires root')
    lock = None
    owner_fd = None
    listener = peer = None
    try:
        if args.action != 'check' and RUNTIME.exists():
            trusted(RUNTIME)
            lock = os.open(RUNTIME / 'service.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action == 'recover':
            # Called only after systemd has stopped the entire service cgroup.
            failures = []
            for operation in (lambda: recover_record(RUNTIME / 'owned.json'), recover_power_record,
                              lambda: recover_power_record(trial=True)):
                try:
                    operation()
                except Exception as error:
                    failures.append(error)
            if failures:
                raise RuntimeError('Post-stop recovery failed')
            recover_session()
            return 0
        if args.action == 'setup':
            from gwe.native_setup import configure
            configure(args.config, args.allowed_uid)
            return 0
        config = load_config(args.config)
        if args.action == 'check':
            print('Configuration valid; no NVML calls performed')
            return 0
        if args.action == 'prepare-session':
            trusted(RUNTIME)
            prepare_session(args.owner_pid, config['allowed_uid'])
            return 0
        if args.action == 'prepare-power-trial':
            if (RUNTIME / 'session.json').exists():
                raise RuntimeError('Manual session recovery is pending')
            from gwe.power_trial import prepare
            trusted(RUNTIME)
            prepare(nvml_factory(), RUNTIME, config['gpu_uuid'])
            print('Trial guard prepared: 250 -> 240 -> 250 W; no GPU settings changed')
            return 0
        trusted(RUNTIME)
        if stat.S_IMODE(RUNTIME.stat().st_mode) != 0o711:
            raise ValueError('Unexpected runtime directory permissions')
        if args.desktop:
            from gwe.desktop_activation import activated_listener
            if any((RUNTIME / name).exists() or (RUNTIME / name).is_symlink()
                   for name in ('session.json', 'owned.json', 'power-pending.json', 'power-trial.json')):
                raise RuntimeError('Recovery pending before desktop activation')
            listener, peer, pid = activated_listener(RUNTIME / 'control.sock', config['allowed_uid'])
            prepare_session(pid, config['allowed_uid'])
            owner_fd = session_owner(config['allowed_uid'])
            if session_record()['cooler_active']:
                subprocess.run(['systemctl', 'stop', 'coolercontrold.service'], check=True, timeout=5)
        # Manual trials require operator-arranged exclusivity; desktop activation records the prior state.
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
        if args.continuous and (RUNTIME / 'power-trial.json').exists():
            raise RuntimeError('Acceptance guard must be recovered before a continuous session')
        if args.continuous and owner_fd is None:
            owner_fd = session_owner(config['allowed_uid'])
        if record.path.exists() or (RUNTIME / 'power-pending.json').exists():
            raise RuntimeError('Unresolved recovery record; refusing new control')
        endpoint = RUNTIME / 'control.sock'
        if endpoint.exists() and not args.desktop:
            if not stat.S_ISSOCK(endpoint.lstat().st_mode):
                raise RuntimeError('Unexpected existing endpoint')
            endpoint.unlink()  # Root-owned parent, only after an old service has stopped.
        backend = ProcessBackend(config['gpu_uuid'], ceiling=85 if args.continuous else 60,
                                 record=record.record, clear=record.clear)
        power = PowerBackend(config['gpu_uuid'], RUNTIME)
        service = FanService(endpoint, backend, allowed_uid=config['allowed_uid'], provision=True,
                             power=power, power_with_fan=args.continuous, listener=listener, initial_peer=peer)
        listener = peer = None  # Service now owns the descriptors, systemd owns the socket path.
        stopping = False
        def stop(signum, frame):
            nonlocal stopping
            stopping = True
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, stop)
        try:
            serve(service, backend, power, lambda: stopping or (
                owner_fd is not None and bool(select.select([owner_fd], [], [], 0)[0])),
                continuous=args.continuous)
        finally:
            try:
                service.close()
            finally:
                try:
                    power.close()
                finally:
                    if not backend.close():
                        raise RuntimeError('Backend shutdown recovery failed')
        return 0
    except Exception as error:
        # Do not expose private configuration, UUID or underlying driver messages.
        print(f'Service failed: {type(error).__name__}', flush=True)
        return 1
    finally:
        if peer is not None:
            peer.close()
        if listener is not None:
            listener.close()
        if owner_fd is not None:
            os.close(owner_fd)
        if lock is not None:
            os.close(lock)


if __name__ == '__main__':
    raise SystemExit(main())
