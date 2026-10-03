#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Start the installed desktop through its authorized socket; no sudo or terminal."""
import argparse
import fcntl
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'vendor'))
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hide-window', action='store_true')
    parser.add_argument('--delay', action='store_true')
    args = parser.parse_args()
    from check_controllers import main as check_controllers
    from gwe.fan_service import FanClient
    from gwe.native_configuration import prepare
    if check_controllers():
        raise RuntimeError('Another GWE controller is running or desktop inspection failed')
    base = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'gwe-nvml'
    state = base / 'state'
    state.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(state / 'control-session.lock', os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    os.set_inheritable(descriptor, True)
    config = prepare(base)
    # Keep the same process identity across exec so root pidfd supervision follows the GUI.
    client = FanClient('/run/gwe-fan-service/control.sock')
    try:
        client.socket.settimeout(15)
        response = client.request('status')
        if not response.get('ok') or response.get('state') != 'idle':
            raise RuntimeError('Control service is unavailable or requires recovery')
    finally:
        client.close()
    environment = dict(os.environ, GWE_STATE_HOME=str(state))
    environment.pop('GWE_STARTUP_PROFILE', None)
    if config.get('startup_profile'):
        environment['GWE_STARTUP_PROFILE'] = config['startup_profile']
    os.execve('/usr/bin/python3', ['python3', str(ROOT / 'scripts/run_service_gui.py'),
                                 '--native', '--allow-control',
                                 '--allow-power-control', '--continuous'] +
              (['--hide-window'] if args.hide_window else []) +
              (['--delay'] if args.delay else []), environment)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # A desktop launch has no terminal. Use the application's ordinary error dialog.
        import gi
        gi.require_version('Gtk', '3.0')
        from gi.repository import Gtk
        dialog = Gtk.MessageDialog(message_type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.CLOSE,
                                   text='GreenWithEnvy could not start')
        dialog.format_secondary_text(f'Control session setup failed ({type(error).__name__}). '
                                     'Close other GPU controllers and check the installed service.')
        dialog.run()
        dialog.destroy()
        raise SystemExit(1)
