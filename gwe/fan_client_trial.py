# SPDX-License-Identifier: GPL-3.0-or-later
"""Unprivileged, bounded client for a separately installed experimental service."""
import argparse
import time
from gwe.fan_service import FanClient


def wait_state(client, target, timeout=10, renew=False):
    expires = time.monotonic() + timeout
    last_renewal = 0
    while time.monotonic() < expires:
        status = client.request('status')
        if not status.get('ok') or status.get('state') in ('fault', 'recovery_failed'):
            raise RuntimeError('Service reported a control or recovery failure')
        if status['state'] == target:
            return status
        if renew and time.monotonic() - last_renewal >= 1:
            if not client.request('renew').get('ok'):
                raise RuntimeError('Lease renewal failed')
            last_renewal = time.monotonic()
        time.sleep(.1)
    raise RuntimeError('Service state deadline exceeded')


def run(path, scenario):
    client = FanClient(path)
    observer = None
    try:
        response = client.request('acquire', points=[[0,40],[50,40],[60,50],[80,100]],
                                  hysteresis=2, vbios_silent=False)
        if not response.get('ok'):
            raise RuntimeError('Service refused acquisition')
        wait_state(client, 'active', renew=True)
        print('Curve active; service owns fan writes', flush=True)
        for _ in range(3):
            if not client.request('renew').get('ok'):
                raise RuntimeError('Lease renewal failed')
            time.sleep(1)
        if scenario == 'disconnect':
            observer = FanClient(path)
            client.close()
            wait_state(observer, 'idle')
        elif scenario == 'expire':
            wait_state(client, 'idle')  # Status requests deliberately do not renew ownership.
        else:
            response = client.request('release')
            if not response.get('ok'):
                raise RuntimeError('Service refused release')
            wait_state(client, 'idle')
        print('Service reports idle after verified automatic recovery', flush=True)
    finally:
        client.close()
        if observer is not None:
            observer.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--socket', default='/run/gwe-fan-service/control.sock')
    parser.add_argument('--scenario', choices=('normal', 'disconnect', 'expire'), default='normal')
    args = parser.parse_args(argv)
    try:
        run(args.socket, args.scenario)
    except Exception as error:
        print(f'Client trial failed: {type(error).__name__}: {error}', flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
