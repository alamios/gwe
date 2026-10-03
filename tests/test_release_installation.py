# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise the grouped install command with fake APT/sudo and no system mutation."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize('transaction,allowed', [
    ('Remv gwe-nvml-client [old]\nRemv gwe-nvml-service [old]\nInst gwe-nvml (candidate local-deb [all])\nConf gwe-nvml (candidate local-deb [all])', True),
    ('Inst nvidia-driver-615 (candidate system [amd64])', False),
    ('Remv unrelated-library [old]', False),
])
def test_grouped_installer_only_authorizes_reviewed_gwe_transition(tmp_path, transaction, allowed):
    if os.geteuid() == 0:
        pytest.skip('The installer deliberately rejects root desktop execution')
    root = tmp_path / 'fixture'
    scripts = root / 'scripts'
    scripts.mkdir(parents=True)
    shutil.copyfile(Path(__file__).resolve().parents[1] / 'scripts/install_release_candidate.sh',
                    scripts / 'install_release_candidate.sh')
    (scripts / 'check_controllers.py').write_text('raise SystemExit(0)\n')
    (scripts / 'check_installed_session.py').write_text("print('synthetic acceptance completed')\n")
    directory = root / 'build/release-rc1'
    directory.mkdir(parents=True)
    candidate = directory / 'gwe-nvml_1.0.0~rc1_all.deb'
    candidate.write_bytes(b'synthetic package; never installed')
    (directory / 'SHA256SUMS').write_text(hashlib.sha256(candidate.read_bytes()).hexdigest() + '  ' + candidate.name + '\n')
    binary = tmp_path / 'bin'
    binary.mkdir()
    (binary / 'apt-get').write_text(
        '#!/bin/sh\nif [ "$1" = --simulate ]; then printf "%s\\n" "$GWE_TEST_TRANSACTION"; '
        'else echo simulated-install >> "$GWE_TEST_LOG"; fi\n')
    (binary / 'sudo').write_text('#!/bin/sh\necho sudo-invoked >> "$GWE_TEST_LOG"\nexec "$@"\n')
    for path in binary.iterdir():
        path.chmod(0o755)
    log = tmp_path / 'operations'
    environment = {**os.environ, 'PATH': str(binary) + ':/usr/bin:/bin',
                   'GWE_INSTALL_PYTHON': '/usr/bin/python3',
                   'GWE_TEST_TRANSACTION': transaction, 'GWE_TEST_LOG': str(log)}
    result = subprocess.run(['bash', str(scripts / 'install_release_candidate.sh')],
                            env=environment, capture_output=True, text=True)
    assert (result.returncode == 0) == allowed
    assert log.exists() == allowed
    if allowed:
        assert log.read_text() == 'sudo-invoked\nsimulated-install\n'
        assert 'synthetic acceptance completed' in result.stdout
