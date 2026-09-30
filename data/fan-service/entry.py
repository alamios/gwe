# SPDX-License-Identifier: GPL-3.0-or-later
"""Installed entry point; use with /usr/bin/python3 -I -B."""
import os
from pathlib import Path
import sys

base = Path(__file__).absolute().parent
if base != Path('/opt/gwe-fan-service') or os.geteuid() != 0:
    raise SystemExit('Run only from the reviewed root-owned installation')
for path in (base, *base.parents, *base.rglob('*')):
    if path.is_symlink() or path.stat().st_uid != 0 or path.stat().st_mode & 0o022:
        raise SystemExit('Untrusted service installation')
sys.path.insert(0, str(base / 'lib'))
from gwe.fan_daemon import main

if __name__ == '__main__':
    raise SystemExit(main())
