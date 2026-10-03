#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Launch the selected local snapshot using private, explicitly supplied paths."""
import json
import os
from pathlib import Path


def main():
    prefix = Path(__file__).resolve().parent
    config = json.loads((prefix / 'config.json').read_text())
    if config.get('version') != 1:
        raise RuntimeError('Unsupported local installation configuration')
    release = (prefix / 'current').resolve(strict=True)
    if release.parent != prefix / 'releases':
        raise RuntimeError('Invalid local release selection')
    environment = dict(os.environ, GWE_STATE_HOME=str(prefix / 'state'))
    environment.pop('GWE_STARTUP_PROFILE', None)
    if config.get('startup_profile'):
        environment['GWE_STARTUP_PROFILE'] = config['startup_profile']
    os.execve('/bin/bash', ['bash', str(release / 'scripts/run_control_session.sh'),
                           config['python'], config['database'], '--installed'], environment)


if __name__ == '__main__':
    main()
