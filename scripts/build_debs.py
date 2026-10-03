#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the combined native package (or historical split artifacts for rollback checks)."""
import argparse
import hashlib
from importlib import metadata
import os
from pathlib import Path
import re
import shutil
import subprocess

from stage_fan_service import stage
from install_local import SCRIPTS
from run_monitor import prepare_resources

ROOT = Path(__file__).resolve().parents[1]
VENDORS = {
    'injector': ('0.21.0', 'injector'), 'peewee': ('3.17.0', ('peewee.py', 'playhouse')),
    'reactivex': ('4.0.4', 'reactivex'), 'typing-extensions': ('4.16.0', 'typing_extensions.py'),
    'nvidia-ml-py': ('13.615.71', 'pynvml.py'), 'py3nvml': ('0.2.7', 'py3nvml'),
    'xmltodict': ('1.0.4', 'xmltodict.py'),
}
GUARD = '''#!/bin/sh
set -eu
if ! state=$(systemctl show gwe-fan-service.service -p ActiveState --value 2>/dev/null); then
    [ ! -e /opt/gwe-fan-service ] && [ ! -L /opt/gwe-fan-service ] || {
        echo 'Cannot inspect existing helper state' >&2; exit 1;
    }
    state=''
fi
case "$state" in ''|inactive|failed) ;; *) echo 'Close and recover GWE before changing packages' >&2; exit 1 ;; esac
for marker in owned.json power-pending.json power-trial.json session.json; do
    [ ! -e "/run/gwe-fan-service/$marker" ] && [ ! -L "/run/gwe-fan-service/$marker" ] || {
        echo 'Recovery pending; refusing package change' >&2; exit 1;
    }
done
override=/run/systemd/system/gwe-fan-service.service.d/90-gwe-continuous.conf
[ ! -e "$override" ] && [ ! -L "$override" ] || { echo 'Session override remains' >&2; exit 1; }
'''


def write(path, content, executable=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(0o755 if executable else 0o644)


def vendor(destination):
    versions = []
    for name, (expected, component) in VENDORS.items():
        components = (component,) if isinstance(component, str) else component
        distribution = metadata.distribution(name)
        if distribution.version != expected:
            raise RuntimeError(f'Review the changed {name} version before bundling')
        licenses = []
        for entry in distribution.files or ():
            relative = Path(str(entry))
            if relative.is_absolute() or '..' in relative.parts:
                continue
            module = relative.parts[0] in components
            info = relative.parts[0].endswith('.dist-info')
            legal = any('license' in part.lower() or 'copying' in part.lower() for part in relative.parts[1:])
            if (module and relative.suffix in ('.py', '.typed')) or (info and (relative.name == 'METADATA' or legal)):
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(distribution.locate_file(entry), target)
                if legal:
                    licenses.append(relative)
        # NVIDIA keeps the full license in pynvml.py itself.
        if not licenses and name != 'nvidia-ml-py':
            raise RuntimeError(f'Missing bundled license for {name}')
        versions.append(f'{name}=={expected}')
    write(destination / 'BUNDLED_VERSIONS', '\n'.join(versions) + '\n')


def finish(tree, destination, name, version, dependencies, epoch, *, relationships=''):
    write(tree / 'DEBIAN/control', f'''Package: {name}
Version: {version}
Architecture: all
Maintainer: GWE local maintenance <noreply@example.invalid>
Section: utils
Priority: optional
Depends: {dependencies}
{relationships}Homepage: https://github.com/alamios/gwe
Description: Local experimental NVML GreenWithEnvy maintenance
 Unprivileged desktop and privileged host helper; manual sessions only.
 No driver or CUDA changes.
''')
    checksum = []
    for file in sorted(tree.rglob('*')):
        if file.is_symlink():
            raise RuntimeError('Package payload must not contain symlinks')
        if file.is_dir():
            file.chmod(0o755)
        elif file.is_file():
            executable = file.parent == tree / 'DEBIAN' and file.name in ('preinst', 'postinst', 'prerm', 'postrm')
            executable = executable or file.parent == tree / 'usr/bin'
            file.chmod(0o755 if executable else 0o644)
        if file.is_file() and 'DEBIAN' not in file.relative_to(tree).parts:
            checksum.append(hashlib.md5(file.read_bytes()).hexdigest() + '  ' + str(file.relative_to(tree)))
    write(tree / 'DEBIAN/md5sums', '\n'.join(checksum) + '\n')
    for path in sorted(tree.rglob('*'), reverse=True):
        if path.is_symlink():
            raise RuntimeError('Package payload must not contain symlinks')
        os.utime(path, (epoch, epoch))
    os.utime(tree, (epoch, epoch))
    tree.chmod(0o755)
    artifact = destination / f'{name}_{version}_all.deb'
    subprocess.run(['dpkg-deb', '--root-owner-group', '--uniform-compression', '-Zxz',
                    '--build', str(tree), str(artifact)],
                   env={**os.environ, 'SOURCE_DATE_EPOCH': str(epoch)}, check=True)
    return artifact


def build(destination, version, epoch, *, split=False):
    if not re.fullmatch(r'[0-9][A-Za-z0-9.+~:-]*', version) or epoch < 0:
        raise ValueError('Invalid package version or source epoch')
    destination = Path(destination).absolute()
    destination.mkdir(parents=True, exist_ok=False)
    helper = destination / ('service-tree' if split else 'package-tree')
    bundle = stage(destination / 'reviewed-service')
    shutil.copytree(bundle, helper / 'opt/gwe-fan-service')
    # Bundle scripts stay review material, not alternate unmanaged system installers.
    for name in ('install.sh', 'update.sh', 'uninstall.sh', 'gwe-fan-service.service', 'SHA256SUMS'):
        (helper / 'opt/gwe-fan-service' / name).unlink()
    unit = helper / 'usr/lib/systemd/system/gwe-fan-service.service'
    unit.parent.mkdir(parents=True)
    shutil.copyfile(bundle / 'gwe-fan-service.service', unit)
    if not split:
        content = unit.read_text().replace(' (60 second trial)', ' (desktop session)')
        content = content.replace('entry.py run\n', 'entry.py run --desktop\n')
        content = content.replace('RuntimeMaxSec=60s', 'RuntimeMaxSec=infinity')
        content = content.replace('TimeoutStartSec=10s', 'TimeoutStartSec=25s')
        content = content.replace('TimeoutStopSec=25s', 'TimeoutStopSec=50s').replace('KillMode=control-group', 'KillMode=mixed')
        write(unit, content)
        write(helper / 'usr/lib/systemd/system/gwe-fan-service.socket', '''[Unit]
Description=GreenWithEnvy authorized desktop control socket

[Socket]
ListenSequentialPacket=/run/gwe-fan-service/control.sock
SocketMode=0600
DirectoryMode=0711
RemoveOnStop=yes
Service=gwe-fan-service.service

[Install]
WantedBy=sockets.target
''')
    write(helper / 'DEBIAN/preinst', GUARD + '''
if [ -L /opt/gwe-fan-service ]; then echo 'Untrusted helper symlink' >&2; exit 1; fi
if [ "${1:-}" = install ] && [ -e /opt/gwe-fan-service ]; then
    dpkg-query -S /opt/gwe-fan-service/entry.py >/dev/null 2>&1 || {
        echo 'Unmanaged helper exists; preserve it and migrate explicitly before installing' >&2; exit 1;
    }
fi
''', True)
    write(helper / 'DEBIAN/prerm', GUARD, True)
    write(helper / 'DEBIAN/postinst', '#!/bin/sh\nset -eu\nsystemctl daemon-reload\n', True)
    write(helper / 'DEBIAN/postrm', '#!/bin/sh\nsystemctl daemon-reload || true\n', True)
    if not split:
        # Stop only activation; recheck that no connection activated a session in the meantime.
        quiesce = GUARD + '''if [ "$(systemctl show gwe-fan-service.socket -p LoadState --value)" = loaded ]; then
    systemctl stop gwe-fan-service.socket
fi
''' + GUARD.split('set -eu\n', 1)[1]
        original = (helper / 'DEBIAN/preinst').read_text()
        write(helper / 'DEBIAN/preinst', original.replace(GUARD, quiesce, 1), True)
        write(helper / 'DEBIAN/prerm', quiesce, True)
        write(helper / 'DEBIAN/postinst', '''#!/bin/sh
set -eu
if [ "${1:-}" = configure ]; then
    uid=${SUDO_UID:-${PKEXEC_UID:-}}
    if [ -n "$uid" ]; then
        /usr/bin/python3 -I -B /opt/gwe-fan-service/entry.py setup --allowed-uid "$uid"
    else
        /usr/bin/python3 -I -B /opt/gwe-fan-service/entry.py setup
    fi
    systemctl daemon-reload
    systemctl enable --now gwe-fan-service.socket
fi
''', True)
        write(helper / 'DEBIAN/postrm', '''#!/bin/sh
if [ "${1:-}" = remove ] || [ "${1:-}" = purge ]; then
    systemctl disable gwe-fan-service.socket 2>/dev/null || true
fi
systemctl daemon-reload || true
''', True)

    client = destination / 'client-tree' if split else helper
    application = client / 'usr/share/gwe-nvml'
    shutil.copytree(ROOT / 'gwe', application / 'gwe', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copytree(ROOT / 'data', application / 'data')
    (application / 'scripts').mkdir()
    for name in SCRIPTS:
        shutil.copyfile(ROOT / 'scripts' / name, application / 'scripts' / name)
    if not split:
        shutil.copyfile(ROOT / 'scripts/run_native.py', application / 'scripts/run_native.py')
    (application / 'resources').mkdir()
    prepare_resources(application, application / 'resources')
    vendor(application / 'vendor')
    write(application / 'scripts/vendor_imports.py', "import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vendor'))\n")
    for name in ('run_service_gui.py', 'run_monitor.py', 'check_controllers.py'):
        path = application / 'scripts' / name
        content = path.read_text()
        # Insert after the module docstring and before dependency imports.
        marker = '\nimport '
        position = content.index(marker)
        path.write_text(content[:position] + '\nimport vendor_imports' + content[position:])
    write(client / 'usr/bin/gwe-nvml', '''#!/usr/bin/python3
import json, os
from pathlib import Path
base = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'gwe-nvml'
config = json.loads((base / 'config.json').read_text())
if config.get('version') != 1:
    raise SystemExit('Unsupported local configuration')
environment = dict(os.environ, GWE_STATE_HOME=str(base / 'state'))
environment.pop('GWE_STARTUP_PROFILE', None)
if config.get('startup_profile'):
    environment['GWE_STARTUP_PROFILE'] = config['startup_profile']
os.execve('/bin/bash', ['bash', '/usr/share/gwe-nvml/scripts/run_control_session.sh',
                      '/usr/bin/python3', config['database'], '--installed'], environment)
''', True)
    if not split:
        write(client / 'usr/bin/gwe-nvml', '''#!/usr/bin/python3
import os
os.execv('/usr/bin/python3', ['python3', '/usr/share/gwe-nvml/scripts/run_native.py'])
''', True)
    write(client / 'usr/share/applications/gwe-nvml-native.desktop', '''[Desktop Entry]
Type=Application
Name=GreenWithEnvy (NVML native)
Exec=gwe-nvml
Icon=/usr/share/gwe-nvml/data/icons/hicolor/256x256/apps/com.leinardi.gwe.png
Terminal=true
Categories=System;
StartupNotify=false
''')
    if not split:
        desktop_entry = client / 'usr/share/applications/gwe-nvml-native.desktop'
        desktop_entry.write_text(desktop_entry.read_text().replace('Terminal=true', 'Terminal=false'))
    if split:
        write(client / 'DEBIAN/preinst', GUARD, True)
        write(client / 'DEBIAN/prerm', GUARD, True)
    dependencies = ('python3 (>= 3.12), python3-gi, python3-gi-cairo, python3-cairo, '
                    'python3-matplotlib (>= 3.6), python3-xlib, python3-xdg, python3-requests, '
                    'gir1.2-gtk-3.0, gir1.2-dazzle-1.0, gir1.2-notify-0.7, '
                    'gir1.2-ayatanaappindicator3-0.1, sudo, util-linux, systemd')
    if split:
        dependencies += f', gwe-nvml-service (= {version})'
    documents = ((helper, 'gwe-nvml-service'), (client, 'gwe-nvml-client')) if split else ((helper, 'gwe-nvml'),)
    for tree, package in documents:
        copyright = tree / f'usr/share/doc/{package}/copyright'
        copyright.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / 'COPYING.txt', copyright)
        shutil.copyfile(ROOT / 'docs/packaging-plan.md', copyright.parent / 'README.Debian')
    if split:
        service = finish(helper, destination, 'gwe-nvml-service', version, 'python3 (>= 3.12), systemd', epoch)
        desktop = finish(client, destination, 'gwe-nvml-client', version, dependencies, epoch)
        artifacts = (desktop, service)
    else:
        # Complete replacement: the old packages must not coexist with shared payload paths.
        artifacts = (finish(helper, destination, 'gwe-nvml', version, dependencies, epoch,
                            relationships='Conflicts: gwe-nvml-client, gwe-nvml-service\n'
                                          'Replaces: gwe-nvml-client, gwe-nvml-service\n'),)
    write(destination / 'SHA256SUMS', '\n'.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name
                                              for p in artifacts) + '\n')
    return artifacts


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--version', required=True)
    parser.add_argument('--epoch', type=int, required=True)
    parser.add_argument('--split', action='store_true', help='Build historical two-package layout for rollback validation')
    args = parser.parse_args()
    for artifact in build(args.destination, args.version, args.epoch, split=args.split):
        print(artifact.name)
