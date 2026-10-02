#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Refuse competing GWE windows before preparing a privileged session."""
import subprocess


def check(names, flatpak_apps):
    competing = {'com.leinardi.gwe', 'com.leinardi.gwe.ServiceTrial'}
    if competing.intersection(names) or 'com.leinardi.gwe' in flatpak_apps:
        raise RuntimeError('Close the other GWE application before starting NVML control')


def main():
    try:
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        reply = bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
                              'org.freedesktop.DBus', 'ListNames', None,
                              GLib.VariantType.new('(as)'), Gio.DBusCallFlags.NONE, 3000, None)
        try:
            result = subprocess.run(['flatpak', 'ps', '--columns=application'],
                                    check=True, capture_output=True, text=True, timeout=5)
            apps = result.stdout.splitlines()
        except FileNotFoundError:
            apps = []
        check(reply.unpack()[0], apps)
    except RuntimeError as error:
        print(str(error), flush=True)
        return 1
    except Exception:
        print('Controller inspection unavailable; no service or GPU changes made', flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
