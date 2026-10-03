#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compare raw NVML and backend counters during a small synthetic video workload."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gwe.nvml_backend import NvmlBackend


def run_phase(command, log, nvml, uuid, engine, *, duration=10):
    maxima = {'raw_percent': 0, 'backend_percent': 0}
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=log)
    try:
        deadline = time.monotonic() + duration
        backend = NvmlBackend(nvml)
        while process.poll() is None:
            if time.monotonic() >= deadline:
                raise RuntimeError('Video diagnostic timeout')
            nvml.nvmlInit()
            try:
                handle = nvml.nvmlDeviceGetHandleByUUID(uuid)
                if nvml.nvmlDeviceGetTemperature(handle, 0) >= 80:
                    raise RuntimeError('Video diagnostic thermal stop')
                function = getattr(nvml, f'nvmlDeviceGet{engine.title()}Utilization')
                raw, period = function(handle)
            finally:
                nvml.nvmlShutdown()
            sample = backend.read_snapshot(uuid)['gpus'][0][engine + '_utilization']
            if sample['status'] != 'ok':
                raise RuntimeError('Backend video telemetry unavailable')
            maxima['raw_percent'] = max(maxima['raw_percent'], raw)
            maxima['backend_percent'] = max(maxima['backend_percent'], sample['value']['percent'])
            maxima['sampling_period_us'] = period
            time.sleep(.1)
        if process.returncode:
            raise RuntimeError('FFmpeg failed; review the private diagnostic log')
        return maxima
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exercise', action='store_true', required=True,
                        help='Authorize two six-second 1080p60 NVENC/NVDEC workloads; no GPU setting writes')
    parser.parse_args()
    import pynvml
    pynvml.nvmlInit()
    try:
        if pynvml.nvmlDeviceGetCount() != 1:
            raise RuntimeError('Diagnostic requires exactly one GPU')
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        uuid = pynvml.nvmlDeviceGetUUID(handle)
        if pynvml.nvmlDeviceGetTemperature(handle, 0) >= 80:
            raise RuntimeError('Video diagnostic thermal stop')
    finally:
        pynvml.nvmlShutdown()
    destination = (Path(__file__).resolve().parents[1] / 'build/video-diagnostic'
                   / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ'))
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    source = destination / 'synthetic.mp4'
    descriptor = os.open(destination / 'ffmpeg.log', os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, 'w') as log:
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi',
                        '-i', 'testsrc2=size=1920x1080:rate=60', '-t', '2', '-c:v', 'libx264',
                        '-threads', '2', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', str(source)],
                       stdout=subprocess.DEVNULL, stderr=log, check=True, timeout=15)
        result = {}
        for engine in ('encoder', 'decoder'):
            command = ['ffmpeg', '-hide_banner', '-loglevel', 'info', '-stream_loop', '-1', '-re']
            if engine == 'decoder':
                command += ['-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda', '-c:v', 'h264_cuvid']
            command += ['-i', str(source), '-t', '6']
            if engine == 'encoder':
                command += ['-c:v', 'h264_nvenc']
            command += ['-f', 'null', '-']
            result[engine] = run_phase(command, log, pynvml, uuid, engine)
        print(json.dumps(result))


if __name__ == '__main__':
    main()
