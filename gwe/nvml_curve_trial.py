# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded synthetic curve/fault experiment, never a background fan service."""

import argparse
import signal
import time

from gwe.fan_curve import FanCurve
from gwe.fan_supervisor import supervise
from gwe.nvml_fan_control import NvmlFanController
from gwe.nvml_fan_trial import interrupted, preflight, restore


# Synthetic validation input, not a saved user profile. Trial aborts at 60 C.
TRIAL_CURVE = FanCurve(((0, 40), (50, 40), (60, 50), (80, 100)), hysteresis=2)


def curve_worker(sender, uuid):
    import pynvml as nvml
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, interrupted)
    nvml.nvmlInit()
    controller = NvmlFanController(nvml, uuid, TRIAL_CURVE, temperature_ceiling=60)
    try:
        controller.start()
        for _ in range(10):
            result = controller.tick()
            sender.send({"event": "tick", **result})
            time.sleep(1)
        controller.stop()
        sender.send({"event": "done"})
    finally:
        try:
            controller.stop()
        finally:
            nvml.nvmlShutdown()
            sender.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--controllers-stopped', action='store_true')
    parser.add_argument('--scenario', choices=('normal', 'term', 'kill', 'stall'), default='normal')
    args = parser.parse_args(argv)
    if args.run and not args.controllers_stopped:
        parser.error('Writing requires exclusive controller ownership')
    import pynvml as nvml
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, interrupted)
    nvml.nvmlInit()
    try:
        if nvml.nvmlDeviceGetCount() != 1:
            raise RuntimeError('This trial requires one GPU')
        handle = nvml.nvmlDeviceGetHandleByIndex(0)
        if nvml.nvmlDeviceGetName(handle) != 'NVIDIA GeForce RTX 3090 Ti':
            raise RuntimeError('Unexpected GPU model')
        uuid = nvml.nvmlDeviceGetUUID(handle)
        print('Preflight:', preflight(nvml, handle), flush=True)
        if args.run:
            restore(nvml, uuid)
            fault = {'normal':None, 'term':signal.SIGTERM, 'kill':signal.SIGKILL, 'stall':signal.SIGSTOP}[args.scenario]
            result = supervise(curve_worker, (uuid,), lambda: restore(nvml, uuid),
                               inject_signal=fault, emit=lambda message: print(message, flush=True))
            print(result, flush=True)
            print('Both fan policies verified automatic', flush=True)
    except Exception as error:
        print(f'Curve trial failed: {type(error).__name__}: {error}', flush=True)
        return 1
    finally:
        nvml.nvmlShutdown()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
