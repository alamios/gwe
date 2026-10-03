#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build local UI resources and run an isolated, GPU-read-only source instance."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def prepare_environment(root, directory="monitor", *, isolate=True):
    state = os.environ.get("GWE_STATE_HOME")
    if state and not Path(state).is_absolute():
        raise ValueError("GWE_STATE_HOME must be an absolute path")
    build = Path(state) / directory if state else root / "build" / directory
    build.mkdir(parents=True, exist_ok=True)
    os.environ["GWE_MONITOR_ONLY"] = "1"
    os.environ.pop("GWE_SERVICE_TRIAL", None)
    # Force local paths before imports can initialize the settings database.
    for variable, directory in (("XDG_CONFIG_HOME", "config"), ("XDG_CACHE_HOME", "cache"),
                                ("XDG_DATA_HOME", "data")):
        if not isolate:
            continue
        target = build / directory
        target.mkdir(exist_ok=True)
        os.environ[variable] = str(target)
    os.environ["GSETTINGS_SCHEMA_DIR"] = str(build)
    return build


def prepare_resources(root, build):
    compiled = root / 'resources'
    if (compiled / 'com.leinardi.gwe.gresource').is_file() and (compiled / 'gschemas.compiled').is_file():
        for name in ('com.leinardi.gwe.gresource', 'com.leinardi.gwe.gschema.xml', 'gschemas.compiled'):
            shutil.copyfile(compiled / name, build / name)
        return build / 'com.leinardi.gwe.gresource'
    for command in ("glib-compile-resources", "glib-compile-schemas"):
        if shutil.which(command) is None:
            raise RuntimeError(f"Missing {command}; install the native GUI prerequisites")
    data = root / "data"
    resource_path = build / "com.leinardi.gwe.gresource"
    subprocess.run(["glib-compile-resources", str(data / "com.leinardi.gwe.gresource.xml"),
                    f"--sourcedir={data}", f"--target={resource_path}"], check=True)
    shutil.copyfile(data / "com.leinardi.gwe.gschema.xml", build / "com.leinardi.gwe.gschema.xml")
    subprocess.run(["glib-compile-schemas", str(build)], check=True)
    return resource_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke-test", action="store_true", help="Check live UI telemetry and quit after 10 seconds")
    args = parser.parse_args()
    if not (ROOT / 'resources').is_dir():
        for command in ("glib-compile-resources", "glib-compile-schemas"):
            if shutil.which(command) is None:
                parser.error(f"Missing {command}; install the native GUI prerequisites")
    build = prepare_environment(ROOT)
    data = ROOT / "data"
    resource_path = prepare_resources(ROOT, build)
    sys.path.insert(0, str(ROOT))
    import gi
    for namespace, version in (("Gtk", "3.0"), ("Gdk", "3.0"), ("Dazzle", "1.0"), ("Notify", "0.7")):
        gi.require_version(namespace, version)
    from gi.repository import Gio, GLib, Gtk
    Gtk.IconTheme.get_default().append_search_path(str(data / "icons" / "hicolor"))
    resource = Gio.Resource.load(str(resource_path))
    resource._register()
    from gwe import __main__ as entry
    passed = []
    if args.smoke_test:
        def finish():
            app = entry.INJECTOR.get(entry.Application)
            presenter = app._presenter
            status = presenter._latest_status
            view = app._view
            valid = (status is not None and status.read_only
                     and status.gpu_status_list[0].info.name is not None
                     and status.gpu_status_list[0].temp.gpu is not None
                     and not view._fan_profile_frame.get_sensitive()
                     and not view._overclock_frame.get_sensitive()
                     and not view._power_limit_apply_button.get_sensitive())
            passed.append(valid)
            print("Monitor UI smoke test:", "PASS" if valid else "FAIL", flush=True)
            app.quit()
            return GLib.SOURCE_REMOVE
        GLib.timeout_add_seconds(10, finish)
    sys.argv = ["gwe-monitor"]
    try:
        entry.main()
    except SystemExit as error:
        return (0 if passed == [True] else 1) if args.smoke_test else error.code
    return 1 if args.smoke_test else 0


if __name__ == "__main__":
    raise SystemExit(main())
