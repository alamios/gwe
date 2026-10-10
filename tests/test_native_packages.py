# SPDX-License-Identifier: GPL-3.0-or-later
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def builder(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'scripts'))
    spec = importlib.util.spec_from_file_location('native_builder', ROOT / 'scripts/build_debs.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('state,marker,success', [('inactive', None, True), ('active', None, False),
                                                ('failed', 'power-pending.json', False),
                                                ('inactive', 'session.json', False)])
def test_package_guard_refuses_active_or_pending_recovery(tmp_path, monkeypatch, state, marker, success):
    module = builder(monkeypatch)
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    if marker:
        (runtime / marker).write_text('{}')
    command = tmp_path / 'systemctl'
    command.write_text('#!/bin/sh\necho ' + state + '\n')
    command.chmod(0o755)
    script = module.GUARD.replace('/run/gwe-fan-service', str(runtime))
    script = script.replace('/run/systemd/system', str(tmp_path / 'systemd'))
    result = subprocess.run(['sh', '-c', script], env={'PATH': str(tmp_path) + ':/usr/bin:/bin'},
                            capture_output=True)
    assert (result.returncode == 0) == success


def test_package_guard_refuses_unknown_state_for_existing_helper(tmp_path, monkeypatch):
    module = builder(monkeypatch)
    helper = tmp_path / 'helper'
    helper.mkdir()
    command = tmp_path / 'systemctl'
    command.write_text('#!/bin/sh\nexit 1\n')
    command.chmod(0o755)
    script = module.GUARD.replace('/opt/gwe-fan-service', str(helper))
    result = subprocess.run(['sh', '-c', script], env={'PATH': str(tmp_path) + ':/usr/bin:/bin'},
                            capture_output=True)
    assert result.returncode != 0


def test_native_build_is_repeatable_and_keeps_private_data_out(tmp_path, monkeypatch):
    if shutil.which('dpkg-deb') is None:
        pytest.skip('Native builder requires dpkg-deb')
    module = builder(monkeypatch)
    def simulated_vendor(path):
        module.write(path / 'BUNDLED_VERSIONS', 'simulated test dependency\n')
    monkeypatch.setattr(module, 'vendor', simulated_vendor)
    first = module.build(tmp_path / 'first', '0.15.9+nvmltest1', 1700000000)
    old_mask = os.umask(0o077)
    try:
        second = module.build(tmp_path / 'second', '0.15.9+nvmltest1', 1700000000)
    finally:
        os.umask(old_mask)
    assert [hashlib.sha256(p.read_bytes()).digest() for p in first] == [hashlib.sha256(p.read_bytes()).digest() for p in second]
    for artifact in first:
        output = subprocess.check_output(['dpkg-deb', '-c', str(artifact)], text=True)
        assert 'gwe.db' not in output and '.local-backups' not in output and 'config.json' not in output
        assert 'root/root' in output
    assert len(first) == 1
    control = subprocess.check_output(['dpkg-deb', '-f', str(first[0])], text=True)
    assert 'Package: gwe-nvml\n' in control
    assert 'Conflicts: gwe-nvml-client, gwe-nvml-service\n' in control
    assert 'Replaces: gwe-nvml-client, gwe-nvml-service\n' in control
    assert 'gwe-nvml-service (=' not in control
    helper = tmp_path / 'first/package-tree'
    assert not list((helper / 'etc').glob('*')) if (helper / 'etc').exists() else True
    assert 'systemctl start' not in (helper / 'DEBIAN/postinst').read_text()
    assert '\n[Install]\n' not in (helper / 'usr/lib/systemd/system/gwe-fan-service.service').read_text()
    app = helper / 'usr/share/gwe-nvml'
    assert (app / 'resources/gschemas.compiled').is_file()
    assert 'vendor_imports' in (app / 'scripts/run_service_gui.py').read_text()
    assert 'Icon=io.github.alamios.gwe\n' in (helper / 'usr/share/applications/io.github.alamios.gwe.desktop').read_text()
    for name in ('com.leinardi.gwe', 'io.github.alamios.gwe'):
        for suffix in ('', '-symbolic'):
            assert (helper / f'usr/share/icons/hicolor/scalable/apps/{name}{suffix}.svg').is_file()
        assert (helper / f'usr/share/icons/hicolor/256x256/apps/{name}.png').is_file()


def test_precompiled_resources_need_no_runtime_compiler(tmp_path, monkeypatch):
    module = builder(monkeypatch)
    import run_monitor
    root, build = tmp_path / 'source', tmp_path / 'state'
    (root / 'resources').mkdir(parents=True)
    build.mkdir()
    for name in ('com.leinardi.gwe.gresource', 'com.leinardi.gwe.gschema.xml', 'gschemas.compiled'):
        (root / 'resources' / name).write_bytes(name.encode())
    monkeypatch.setattr(run_monitor.shutil, 'which', lambda _: None)
    result = run_monitor.prepare_resources(root, build)
    assert result.read_bytes() == b'com.leinardi.gwe.gresource'


def test_peewee_vendor_includes_playhouse_without_native_extensions(tmp_path, monkeypatch):
    module = builder(monkeypatch)
    monkeypatch.setattr(module, 'VENDORS', {'peewee': module.VENDORS['peewee']})
    files = ['peewee.py', 'playhouse/__init__.py', 'playhouse/signals.py',
             'playhouse/sqlite_ext.py', 'playhouse/migrate.py', 'playhouse/_sqlite_ext.so',
             'peewee-3.17.0.dist-info/METADATA', 'peewee-3.17.0.dist-info/LICENSE',
             'peewee-3.17.0.dist-info/direct_url.json']
    source = tmp_path / 'source'
    for name in files:
        module.write(source / name, '# test payload\n')
    module.write(source / 'playhouse/migrate.py', migration_fixture())
    class Distribution:
        version = '3.17.0'
        def locate_file(self, entry):
            return source / entry
    distribution = Distribution()
    distribution.files = files
    monkeypatch.setattr(module.metadata, 'distribution', lambda name: distribution)
    destination = tmp_path / 'vendor'
    module.vendor(destination)
    for name in files:
        assert (destination / name).exists() == (not name.endswith(('.so', 'direct_url.json')))


def migration_fixture():
    return ("class Migration:\n"
            "    column_re = re.compile('(.+?)\\((.+)\\)')\n"
            "    def match(self, column_to_update, column):\n"
            "        if True:\n"
            "            if re.match('%s(?:[\\'\"`\\]]?\\s|$)' % column_to_update, column):\n"
            "                return True\n")


def test_reviewed_peewee_patch_preserves_ast_and_eliminates_escape_warnings(tmp_path, monkeypatch):
    import ast
    import warnings
    module = builder(monkeypatch)
    path = tmp_path / 'migrate.py'
    original = migration_fixture()
    path.write_text(original)
    module.patch_peewee(path)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', (SyntaxWarning, DeprecationWarning))
        before = ast.dump(ast.parse(original))
    with warnings.catch_warnings():
        warnings.simplefilter('error', (SyntaxWarning, DeprecationWarning))
        corrected = path.read_text()
        assert ast.dump(ast.parse(corrected)) == before
        compile(corrected, str(path), 'exec')
    path.write_text(original.replace('column_re =', 'changed_column_re ='))
    with pytest.raises(RuntimeError):
        module.patch_peewee(path)


def test_real_dpkg_transition_and_rollback_preserve_private_config(tmp_path, monkeypatch):
    """Exercise dpkg ownership in a private root, without executing host maintainer scripts."""
    module = builder(monkeypatch)
    monkeypatch.setattr(module, 'vendor', lambda path: module.write(path / 'BUNDLED_VERSIONS', 'fixture\n'))
    old = module.build(tmp_path / 'split', '0.15.9+nvmltest1', 1700000000, split=True)
    new = module.build(tmp_path / 'combined', '1.0.0~rc1', 1700000000)
    root = tmp_path / 'root'
    database = root / 'var/lib/dpkg'
    database.mkdir(parents=True)
    (database / 'status').touch()
    config = root / 'etc/gwe-fan-service.json'
    config.parent.mkdir()
    config.write_text('private configuration fixture')
    # Guard scripts are tested separately. Strip scripts to keep this real dpkg test entirely
    # within its --root; dependencies use the host only in production, not this private database.
    def fixture(artifact, label):
        tree = tmp_path / label
        subprocess.run(['dpkg-deb', '-R', str(artifact), str(tree)], check=True, capture_output=True)
        for name in ('preinst', 'postinst', 'prerm', 'postrm'):
            (tree / 'DEBIAN' / name).unlink(missing_ok=True)
        result = tmp_path / (label + '.deb')
        subprocess.run(['dpkg-deb', '--build', str(tree), str(result)], check=True, capture_output=True)
        return str(result)
    previous = [fixture(p, 'old-' + str(i)) for i, p in enumerate(old)]
    combined = fixture(new[0], 'new')
    command = ['dpkg', '--root=' + str(root), '--force-not-root', '--force-depends']
    def dpkg(*args):
        subprocess.run([*command, *args], check=True, capture_output=True)
    def installed():
        text = subprocess.check_output(['dpkg-query', '--admindir=' + str(database), '-W',
                                        '-f=${Package} ${Status}\n'], text=True)
        return {line.split()[0] for line in text.splitlines() if line.endswith('install ok installed')}
    dpkg('--install', *previous)
    assert installed() == {'gwe-nvml-client', 'gwe-nvml-service'}
    dpkg('--install', combined)
    assert installed() == {'gwe-nvml'}
    for name in ('opt/gwe-fan-service/entry.py', 'usr/share/gwe-nvml/gwe/__main__.py',
                 'usr/lib/systemd/system/gwe-fan-service.service', 'usr/bin/gwe-nvml'):
        assert (root / name).is_file()
    assert config.read_text() == 'private configuration fixture'
    dpkg('--remove', 'gwe-nvml')
    dpkg('--install', *previous)
    assert installed() == {'gwe-nvml-client', 'gwe-nvml-service'}
    assert config.read_text() == 'private configuration fixture'
