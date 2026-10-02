#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Install or update a separate user-owned snapshot without starting GPU control."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ('run_control_session.sh', 'run_service_gui.py', 'run_monitor.py', 'check_controllers.py')


def atomic_file(path, content, mode=0o600):
    descriptor, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            stream.write(content)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def select(prefix, name, release):
    if release.parent != prefix / 'releases' or not release.is_dir():
        raise RuntimeError('Invalid local release selection')
    temporary = prefix / (name + '.next')
    if temporary.exists() or temporary.is_symlink():
        raise RuntimeError('Unfinished local update; inspect the temporary selection')
    temporary.symlink_to(release.relative_to(prefix))
    os.replace(temporary, prefix / name)


def verify_release(prefix, release):
    if release.parent != prefix / 'releases' or not release.is_dir():
        raise RuntimeError('Invalid local release selection')
    for entry in (release / 'SHA256SUMS').read_text().splitlines():
        digest, name = entry.split('  ', 1)
        path = release / name
        if Path(name).is_absolute() or '..' in Path(name).parts or path.is_symlink():
            raise RuntimeError('Invalid snapshot manifest path')
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError('Existing release has changed; refusing reuse')


def desktop_quote(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%') + '"'


def install(prefix, applications, python=None, database=None, *, rollback=False, source=ROOT,
            startup_profile=None):
    prefix = prefix.absolute()
    if prefix.is_symlink():
        raise RuntimeError('Installation directory must not be a symlink')
    if prefix.exists() and not (prefix / 'config.json').is_file():
        raise RuntimeError('Refusing an unrecognized installation directory')
    if prefix.exists() and json.loads((prefix / 'config.json').read_text()).get('version') != 1:
        raise RuntimeError('Unsupported local installation configuration')
    if not prefix.exists() and (applications / 'gwe-nvml-local.desktop').exists():
        raise RuntimeError('Refusing to overwrite an existing desktop entry')
    if any(character in str(prefix) for character in '\n\r'):
        raise RuntimeError('Installation path contains a line break')
    prefix.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (prefix / 'install.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        current = prefix / 'current'
        old = current.resolve(strict=True) if current.is_symlink() else None
        if current.exists() and not current.is_symlink():
            raise RuntimeError('Invalid current release entry')
        if rollback:
            previous = (prefix / 'previous').resolve(strict=True)
            verify_release(prefix, previous)
            if old:
                verify_release(prefix, old)
            select(prefix, 'current', previous)
            if old:
                select(prefix, 'previous', old)
            return
        python = Path(python).absolute()
        database = Path(database).absolute()
        if not python.is_file() or not os.access(python, os.X_OK) or not database.is_file():
            raise RuntimeError('Provide an executable prepared interpreter and existing backup')
        (prefix / 'releases').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=prefix / 'releases', prefix='.stage-') as temporary:
            stage = Path(temporary)
            # Copy only public application sources/resources; never build output or private profiles.
            shutil.copytree(source / 'gwe', stage / 'gwe', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            shutil.copytree(source / 'data', stage / 'data', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            shutil.copyfile(source / 'COPYING.txt', stage / 'COPYING.txt')
            (stage / 'scripts').mkdir()
            for name in SCRIPTS:
                shutil.copyfile(source / 'scripts' / name, stage / 'scripts' / name)
            entries = []
            for path in sorted(stage.rglob('*')):
                if path.is_symlink():
                    raise RuntimeError('Snapshot must not contain symlinks')
                if path.is_file():
                    entries.append(hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + str(path.relative_to(stage)))
            manifest = '\n'.join(entries) + '\n'
            (stage / 'SHA256SUMS').write_text(manifest)
            release = prefix / 'releases' / hashlib.sha256(manifest.encode()).hexdigest()[:16]
            if release.exists():
                if (release / 'SHA256SUMS').read_text() != manifest:
                    raise RuntimeError('Existing release manifest differs')
                verify_release(prefix, release)
            else:
                shutil.copytree(stage, release)
        launcher = prefix / 'launch.py'
        desktop = ('[Desktop Entry]\nType=Application\nName=GreenWithEnvy (NVML)\n'
                   'Comment=Explicit local NVIDIA fan and power control\nTerminal=true\n'
                   'Categories=System;\nStartupNotify=false\n'
                   f'Exec=/usr/bin/python3 {desktop_quote(launcher)}\n'
                   f'Icon={prefix}/current/data/icons/hicolor/256x256/apps/com.leinardi.gwe.png\n')
        applications.mkdir(parents=True, exist_ok=True)
        atomic_file(prefix / 'launch.py', (source / 'scripts/launch_local.py').read_text(), 0o700)
        config = {'version': 1, 'python': str(python), 'database': str(database)}
        if startup_profile is None and (prefix / 'config.json').exists():
            startup_profile = json.loads((prefix / 'config.json').read_text()).get('startup_profile')
        if startup_profile:
            config['startup_profile'] = startup_profile
        atomic_file(prefix / 'config.json', json.dumps(config) + '\n')
        if old and old != release:
            select(prefix, 'previous', old)
        select(prefix, 'current', release)
        atomic_file(applications / 'gwe-nvml-local.desktop', desktop, 0o644)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', type=Path)
    parser.add_argument('--database', type=Path)
    parser.add_argument('--rollback', action='store_true')
    parser.add_argument('--startup-profile', help='Named saved curve to apply once at application startup')
    args = parser.parse_args()
    if not args.rollback and (args.python is None or args.database is None):
        parser.error('--python and --database are required for install/update')
    data = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share')))
    if not data.is_absolute():
        parser.error('XDG_DATA_HOME must be absolute')
    install(data / 'gwe-nvml', data / 'applications', args.python, args.database,
            rollback=args.rollback, startup_profile=args.startup_profile)
    print('Local launcher prepared; no service started or GPU settings changed')


if __name__ == '__main__':
    main()
