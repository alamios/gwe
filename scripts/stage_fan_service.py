#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build a reviewable private service bundle. Never install or start it."""
import argparse
import hashlib
from importlib import metadata, util
from pathlib import Path
import shutil

MODULES = ('fan_curve', 'fan_service', 'fan_process', 'fan_daemon', 'nvml_fan_control')


def stage(destination):
    root = Path(__file__).resolve().parents[1]
    binding = metadata.distribution('nvidia-ml-py')
    if binding.version != '13.615.71':
        raise RuntimeError('Review a new NVML binding version before bundling')
    source = Path(util.find_spec('pynvml').origin)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    (destination / 'lib' / 'gwe').mkdir(parents=True)
    (destination / 'lib' / 'gwe' / '__init__.py').write_text('# Isolated fan-service package.\n')
    for name in MODULES:
        shutil.copyfile(root / 'gwe' / f'{name}.py', destination / 'lib' / 'gwe' / f'{name}.py')
    shutil.copyfile(source, destination / 'lib' / 'pynvml.py')  # Retain NVIDIA's complete license header.
    shutil.copyfile(root / 'COPYING.txt', destination / 'COPYING.txt')
    for name in ('entry.py', 'gwe-fan-service.service', 'config.example.json', 'install.sh', 'uninstall.sh'):
        shutil.copyfile(root / 'data' / 'fan-service' / name, destination / name)
    (destination / 'BINDING_VERSION').write_text(binding.version + '\n')
    lines = []
    for path in sorted(destination.rglob('*')):
        if path.is_file():
            lines.append(hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + str(path.relative_to(destination)))
    (destination / 'SHA256SUMS').write_text('\n'.join(lines) + '\n')
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination')
    args = parser.parse_args()
    print(stage(args.destination))
