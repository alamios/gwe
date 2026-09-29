# SPDX-License-Identifier: GPL-3.0-or-later
"""Standalone read-only NVML diagnostics; never imports the GWE application."""

import argparse
import importlib
import json
import platform
from importlib.metadata import version


from gwe.nvml_backend import _READS, collect_report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read NVIDIA telemetry as JSON without changing GPU settings.")
    parser.parse_args(argv)
    try:
        nvml = importlib.import_module("pynvml")
    except ModuleNotFoundError as error:
        if error.name != "pynvml":
            raise
        print(json.dumps({"status": "error", "message": "Install nvidia-ml-py in this Python environment."}))
        return 1
    report = collect_report(nvml)
    report["python_version"] = platform.python_version()
    report["binding_version"] = version("nvidia-ml-py")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
