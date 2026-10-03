# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit, supervised hardware experiment; never imported by the application."""

import argparse
import multiprocessing
import signal
import time


class TrialError(RuntimeError):
    """A precondition, observation or recovery failed."""


def selected(nvml, uuid):
    handle = nvml.nvmlDeviceGetHandleByUUID(uuid)
    if nvml.nvmlDeviceGetUUID(handle) != uuid:
        raise TrialError("GPU identity changed")
    return handle


def observe(nvml, handle, clock=time.monotonic):
    started = clock()
    temperature = nvml.nvmlDeviceGetTemperature(handle, nvml.NVML_TEMPERATURE_GPU)
    fans = [{"policy": nvml.nvmlDeviceGetFanControlPolicy_v2(handle, fan),
             "target": nvml.nvmlDeviceGetTargetFanSpeed(handle, fan),
             "speed": nvml.nvmlDeviceGetFanSpeed_v2(handle, fan)} for fan in range(2)]
    if clock() - started > 2:
        raise TrialError("Telemetry collection exceeded two seconds")
    if not isinstance(temperature, (int, float)) or not 0 <= temperature < 60:
        raise TrialError("Missing, invalid or excessive temperature")
    if any(not isinstance(f["speed"], int) or not 0 <= f["speed"] <= 100 for f in fans):
        raise TrialError("Invalid fan telemetry")
    return {"temperature_c": temperature, "fans": fans}


def preflight(nvml, handle):
    if nvml.nvmlDeviceGetNumFans(handle) != 2:
        raise TrialError("This experiment requires exactly two fans")
    low, high = nvml.nvmlDeviceGetMinMaxFanSpeed(handle)
    if not 0 <= low <= 40 <= high <= 100:
        raise TrialError("40 percent is outside the reported manual limits")
    state = observe(nvml, handle)
    if any(f["policy"] != nvml.NVML_FAN_POLICY_TEMPERATURE_CONTINOUS_SW for f in state["fans"]):
        raise TrialError("Both fans must already be automatic")
    if any(f["speed"] > 40 for f in state["fans"]):
        raise TrialError("Refusing to reduce an existing fan speed")
    return state


def restore(nvml, uuid):
    """Attempt every fan even after a failed reset; verify policy independently."""
    failures = []
    for fan in range(2):
        try:
            nvml.nvmlDeviceSetDefaultFanSpeed_v2(selected(nvml, uuid), fan)
        except Exception as error:
            failures.append(f"fan {fan} reset: {type(error).__name__}")
    for fan in range(2):
        try:
            policy = nvml.nvmlDeviceGetFanControlPolicy_v2(selected(nvml, uuid), fan)
            if policy != nvml.NVML_FAN_POLICY_TEMPERATURE_CONTINOUS_SW:
                raise TrialError("Policy is not automatic")
        except Exception as error:
            failures.append(f"fan {fan} verification: {type(error).__name__}")
    if failures:
        raise TrialError("; ".join(failures))


def exercise(nvml, uuid, emit=print, sleep=time.sleep):
    """Run fixed targets only; partial writes always enter recovery."""
    handle = selected(nvml, uuid)
    preflight(nvml, handle)
    try:
        for fan in range(2):
            # Recheck fresh telemetry before each individual write.
            observe(nvml, handle)
            nvml.nvmlDeviceSetFanSpeed_v2(handle, fan, 40)
        for _ in range(10):
            sleep(1)
            state = observe(nvml, handle)
            emit(state)
            if any(f["policy"] != nvml.NVML_FAN_POLICY_MANUAL or f["target"] != 40
                   for f in state["fans"]):
                raise TrialError("Manual policy/target readback differs from request")
        if any(not 30 <= f["speed"] <= 50 for f in state["fans"]):
            raise TrialError("Fan speed did not settle near the requested duty")
    finally:
        restore(nvml, uuid)


def interrupted(signum, _frame):
    raise TrialError(f"Interrupted by signal {signum}")


def worker(uuid):
    import pynvml as nvml
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    nvml.nvmlInit()
    try:
        exercise(nvml, uuid, emit=lambda state: print(state, flush=True))
    finally:
        nvml.nvmlShutdown()


def supervise(nvml, uuid, context=None):
    """Parent never sets manual duty and restores only after its worker exits.

    The worker also restores, so killing either process alone is recoverable
    while the other and driver remain responsive. This is not a system service.
    """
    context = context or multiprocessing.get_context("spawn")
    process = context.Process(target=worker, args=(uuid,))
    try:
        # Prove reset permission/support before allowing any manual setter.
        restore(nvml, uuid)
        process.start()
        process.join(20)
        if process.is_alive():
            raise TrialError("Manual worker exceeded its 20-second deadline")
        if process.exitcode != 0:
            raise TrialError("Manual worker failed")
    finally:
        # Prevent further manual writes before parent-side recovery.
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, signal.SIG_IGN)
        if process.pid is not None and process.is_alive():
            process.kill()
            process.join(3)
            if process.is_alive():
                raise TrialError("Worker could not stop; immediate operator recovery required")
        restore(nvml, uuid)
        print("Both fan policies verified automatic", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--run", action="store_true", help="Write 40 percent for ten seconds")
    actions.add_argument("--restore-only", action="store_true", help="Restore automatic policy only")
    parser.add_argument("--controllers-stopped", action="store_true",
                        help="Operator confirms no competing GPU fan controller")
    args = parser.parse_args(argv)
    if (args.run or args.restore_only) and not args.controllers_stopped:
        parser.error("Writes require --controllers-stopped after external inspection")
    import pynvml as nvml
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    nvml.nvmlInit()
    try:
        if nvml.nvmlDeviceGetCount() != 1:
            raise TrialError("This experiment requires a single GPU")
        handle = nvml.nvmlDeviceGetHandleByIndex(0)
        if nvml.nvmlDeviceGetName(handle) != "NVIDIA GeForce RTX 3090 Ti":
            raise TrialError("Unexpected GPU model")
        uuid = nvml.nvmlDeviceGetUUID(handle)  # Memory/IPC only; never log identity.
        if args.restore_only:
            if nvml.nvmlDeviceGetNumFans(handle) != 2:
                raise TrialError("Unexpected fan count")
            restore(nvml, uuid)
            print("Both fan policies verified automatic", flush=True)
        else:
            print("Preflight:", preflight(nvml, handle), flush=True)
            if args.run:
                supervise(nvml, uuid)
    except Exception as error:
        print(f"Trial failed: {type(error).__name__}: {error}", flush=True)
        return 1
    finally:
        nvml.nvmlShutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
