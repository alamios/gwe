#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Preserve reviewed pure-Python build inputs without retaining an old interpreter environment."""
import argparse
import hashlib
from importlib import metadata
from pathlib import Path
import shutil

from build_debs import VENDORS


def stage(source, destination):
    source, destination = Path(source).resolve(strict=True), Path(destination)
    distributions = {d.metadata.get('Name', '').lower().replace('_', '-'): d
                     for d in metadata.distributions(path=[str(source)])}
    files = {}
    for name, (version, modules) in VENDORS.items():
        distribution = distributions.get(name)
        if distribution is None or distribution.version != version or not distribution.files:
            raise ValueError(f'Missing reviewed distribution metadata: {name}=={version}')
        modules = (modules,) if isinstance(modules, str) else modules
        for entry in distribution.files:
            relative = Path(str(entry))
            if relative.is_absolute() or '..' in relative.parts:
                continue
            if (relative.parts[0].endswith('.dist-info')
                    or (relative.parts[0] in modules and relative.suffix in ('.py', '.typed'))):
                origin = Path(distribution.locate_file(entry))
                if origin.is_symlink() or not origin.is_file() or not origin.resolve().is_relative_to(source):
                    raise ValueError('Unexpected dependency input file')
                files[relative] = origin
    destination.mkdir(parents=True, exist_ok=False)
    for relative, origin in files.items():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origin, target)
    manifest = ''.join(f'{hashlib.sha256((destination / p).read_bytes()).hexdigest()}  {p}\n'
                       for p in sorted(files))
    (destination / 'SHA256SUMS').write_text(manifest)
    print('Reviewed pure-Python modules, distribution metadata and licenses staged; no packages installed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='Existing reviewed site-packages directory')
    parser.add_argument('destination', type=Path, help='New preserved build-input directory')
    args = parser.parse_args()
    stage(args.source, args.destination)
