#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Owner-invoked migration of the reviewed manual helper to pinned local packages."""
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

VERSION = '0.15.9+nvml20261003.4'
HASHES = {
    'client': '2046129d9feafd4f0da53deff52acd6eb4c675174951cc183529208d98426b2f',
    'service': '1336327048692d766ee43b0ff04f57d5e77405664fbce33c372d9c8cb126d298',
}
DEPENDENCIES = set('''fonts-lyx liblbfgsb0 libqhull-r8.0 python-matplotlib-data
python3-appdirs python3-attr python3-contourpy python3-cycler python3-decorator
python3-fonttools python3-fs python3-kiwisolver python3-lxml python3-lz4
python3-matplotlib python3-mpmath python3-numpy python3-pil.imagetk python3-scipy
python3-sympy python3-tz python3-ufolib2 python3-unicodedata2 python3-xlib unicode-data'''.split())
UNIT = Path('/etc/systemd/system/gwe-fan-service.service')
HELPER = Path('/opt/gwe-fan-service')
CONFIG = Path('/etc/gwe-fan-service.json')
GUARD = '''set -eu
state=$(systemctl show gwe-fan-service.service -p ActiveState --value)
case "$state" in inactive|failed) ;; *) echo 'Close GWE and recover the service first'; exit 1 ;; esac
for marker in owned.json power-pending.json power-trial.json session.json; do
    test ! -e "/run/gwe-fan-service/$marker" && test ! -L "/run/gwe-fan-service/$marker"
done
override=/run/systemd/system/gwe-fan-service.service.d/90-gwe-continuous.conf
test ! -e "$override" && test ! -L "$override"
'''


def run(*args, capture=False):
    return subprocess.run(args, check=True, text=True,
                          stdout=subprocess.PIPE if capture else None,
                          env={**os.environ, 'LC_ALL': 'C', 'PATH': '/usr/sbin:/usr/bin:/sbin:/bin'})


def approved_dependencies(output):
    """Reject unrelated changes, including upgrades or deferred broken packages."""
    installs = []
    for line in output.splitlines():
        if line.startswith(('Remv ', 'Purg ')):
            raise RuntimeError('Package removal refused')
        if line.startswith(('Inst ', 'Conf ')):
            match = re.match(r'^(Inst|Conf) (\S+) \((\S+) ', line)
            if not match or match[2] not in DEPENDENCIES:
                raise RuntimeError('Unreviewed package change refused')
            if match[1] == 'Inst':
                installs.append(f'{match[2]}={match[3]}')
    return installs


def trusted(path):
    for item in [path, *path.rglob('*')] if path.is_dir() else [path]:
        info = item.lstat()
        if item.is_symlink() or info.st_uid != 0 or info.st_mode & 0o022:
            raise RuntimeError('Existing installation has unsafe ownership or permissions')


def restore_script():
    return '#!/bin/sh\n' + GUARD + '''
cd -- "$(dirname -- "$0")"
test -d manual-helper && test -f manual.service
dpkg --remove gwe-nvml-client gwe-nvml-service
test ! -e /opt/gwe-fan-service && test ! -L /opt/gwe-fan-service
test ! -e /etc/systemd/system/gwe-fan-service.service
mv -- manual-helper /opt/gwe-fan-service
mv -- manual.service /etc/systemd/system/gwe-fan-service.service
systemctl daemon-reload
echo 'Manual helper restored, inactive. Private configuration was preserved.'
'''


def main():
    if os.geteuid() != 0:
        raise RuntimeError('Run through install_native.sh for desktop checks and sudo authentication')
    os.umask(0o077)
    run('sh', '-c', GUARD)
    for path in (HELPER, UNIT, CONFIG):
        trusted(path)
    for package in ('gwe-nvml-client', 'gwe-nvml-service'):
        result = subprocess.run(['dpkg-query', '-W', '-f=${db:Status-Abbrev}', package],
                                capture_output=True, text=True)
        if result.returncode == 0 and result.stdout[:2] != 'un':
            raise RuntimeError('This first-install migration refuses an existing package record')
    run('/usr/bin/python3', '-I', '-B', str(HELPER / 'entry.py'), 'check')
    source = Path(__file__).resolve().parents[1] / 'build/native-debs-v4'
    # Root-owned copies prevent artifact changes between verification and installation.
    with tempfile.TemporaryDirectory(prefix='gwe-native-', dir='/var/tmp') as temporary:
        packages = []
        for component, expected in HASHES.items():
            name = f'gwe-nvml-{component}_{VERSION}_all.deb'
            target = Path(temporary) / name
            shutil.copyfile(source / name, target)
            if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
                raise RuntimeError('Candidate checksum mismatch')
            packages.append(str(target))
        apt = ('apt-get', '--no-remove', '--no-upgrade', '--no-install-recommends')
        plan = run(*apt, '-s', 'install', 'python3-matplotlib', 'python3-xlib', capture=True)
        dependencies = approved_dependencies(plan.stdout)
        if dependencies:
            # Install dependencies before moving the working manual helper.
            run(*apt, '-y', 'install', *dependencies)
        # Check all package dependencies before changing the helper, then recheck quiescence.
        run('dpkg', '--no-act', '--install', *packages)
        run('sh', '-c', GUARD)
        archive = Path(tempfile.mkdtemp(prefix='gwe-native-', dir='/var/backups'))
        shutil.copy2(CONFIG, archive / 'private-config.json')
        if (archive / 'private-config.json').read_bytes() != CONFIG.read_bytes():
            raise RuntimeError('Configuration backup verification failed')
        (archive / 'restore.sh').write_text(restore_script())
        print(f'Recovery archive: {archive}', flush=True)
        print(f'Rollback command: sudo sh {archive}/restore.sh', flush=True)
        # Retain the trusted original code and unit, including ownership and modes.
        shutil.move(str(HELPER), str(archive / 'manual-helper'))
        try:
            shutil.move(str(UNIT), str(archive / 'manual.service'))
        except BaseException:
            shutil.move(str(archive / 'manual-helper'), str(HELPER))
            raise
        try:
            run('systemctl', 'daemon-reload')
            run('dpkg', '--install', *packages)
            run('/usr/bin/python3', '-I', '-B', str(HELPER / 'entry.py'), 'check')
            run('sh', '-c', GUARD)
        except BaseException:
            print(f'Installation incomplete; retain {archive}. Do not launch GWE. '
                  f'Recovery: sudo sh {archive}/restore.sh', file=sys.stderr)
            raise
    print('Native packages installed. Service inactive; no GPU settings changed.')


if __name__ == '__main__':
    main()
