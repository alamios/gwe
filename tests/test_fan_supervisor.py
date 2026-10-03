# SPDX-License-Identifier: GPL-3.0-or-later
"""Real child-process faults, with no NVML import or hardware access."""
import os
import signal
import time

import pytest
from gwe.fan_supervisor import SupervisorError, supervise


def simulated_worker(sender, scenario):
    sender.send({'event':'tick','pid':os.getpid()})
    time.sleep(0.05)
    sender.send({'event':'tick','pid':os.getpid()})
    if scenario == 'done':
        sender.send({'event':'done'})
    elif scenario == 'crash':
        raise SystemExit(7)
    else:
        time.sleep(10)
    sender.close()


def recovery_recorder(pids, calls):
    def recover():
        for pid in pids:
            with pytest.raises(ProcessLookupError):os.kill(pid,0)
        calls.append('restored')
    return recover


def test_normal_exit_recovers_after_worker_stops():
    pids=set();calls=[]
    result=supervise(simulated_worker,('done',),recovery_recorder(pids,calls),
                     heartbeat_seconds=2,total_seconds=5,emit=lambda m:pids.add(m['pid']))
    assert result['outcome']=='completed'
    assert calls==['restored']


@pytest.mark.parametrize('fault',[signal.SIGTERM,signal.SIGKILL,signal.SIGSTOP])
def test_real_process_faults_recover_after_worker_stops(fault):
    pids=set();calls=[]
    result=supervise(simulated_worker,('wait',),recovery_recorder(pids,calls),
                     heartbeat_seconds=0.5,total_seconds=5,inject_signal=fault,
                     emit=lambda m:pids.add(m['pid']))
    assert result['injected']
    assert result['outcome'] in ('terminated_worker_detected','stalled_worker_detected')
    assert calls==['restored']


@pytest.mark.parametrize('scenario',['crash','wait'])
def test_unexpected_exit_or_heartbeat_loss_is_failure(scenario):
    pids=set();calls=[]
    with pytest.raises(SupervisorError):
        supervise(simulated_worker,(scenario,),recovery_recorder(pids,calls),
                  heartbeat_seconds=0.5,total_seconds=5,emit=lambda m:pids.add(m['pid']))
    assert calls==['restored']


def test_recovery_failure_is_not_reported_as_success():
    def recover():raise RuntimeError('reset denied')
    with pytest.raises(RuntimeError,match='reset denied'):
        supervise(simulated_worker,('done',),recover,heartbeat_seconds=2,total_seconds=5)


class SharedNvml:
    """Process-shared simulated policies, proving recovery after actual child death."""
    NVML_TEMPERATURE_GPU=0
    NVML_FAN_POLICY_MANUAL=1
    NVML_FAN_POLICY_TEMPERATURE_CONTINOUS_SW=0

    def __init__(self,context):
        self.policies=context.Array('i',[0,0])
        self.targets=context.Array('i',[0,0])

    def nvmlDeviceGetHandleByUUID(self,uuid):return 'handle'
    def nvmlDeviceGetUUID(self,handle):return 'GPU-test'
    def nvmlDeviceGetNumFans(self,handle):return 2
    def nvmlDeviceGetMinMaxFanSpeed(self,handle):return (30,100)
    def nvmlDeviceGetTemperature(self,handle,sensor):return 50
    def nvmlDeviceGetFanControlPolicy_v2(self,handle,fan):return self.policies[fan]
    def nvmlDeviceGetTargetFanSpeed(self,handle,fan):return self.targets[fan]
    def nvmlDeviceSetDefaultFanSpeed_v2(self,handle,fan):self.policies[fan]=0
    def nvmlDeviceSetFanSpeed_v2(self,handle,fan,duty):
        self.policies[fan]=1
        self.targets[fan]=duty


def shared_curve_worker(sender,nvml,wait):
    from gwe.fan_curve import FanCurve
    from gwe.nvml_fan_control import NvmlFanController
    controller=NvmlFanController(nvml,'GPU-test',FanCurve(((40,30),(60,70))))
    try:
        controller.start()
        for _ in range(2):
            sender.send({'event':'tick',**controller.tick()})
            time.sleep(0.05)
        if wait:time.sleep(10)
        controller.stop()
        sender.send({'event':'done'})
    finally:
        controller.stop()
        sender.close()


@pytest.mark.parametrize('fault',[None,signal.SIGTERM,signal.SIGKILL,signal.SIGSTOP])
def test_curve_and_supervisor_restore_shared_device_after_process_failure(fault):
    import multiprocessing
    from gwe.nvml_fan_trial import restore
    nvml=SharedNvml(multiprocessing.get_context('spawn'))
    samples=[]
    result=supervise(shared_curve_worker,(nvml,fault is not None),lambda:restore(nvml,'GPU-test'),
                     heartbeat_seconds=0.5,total_seconds=5,inject_signal=fault,emit=samples.append)
    assert result['injected']==(fault is not None)
    assert all(sample['duty_percent']==50 for sample in samples)
    assert list(nvml.targets)==[50,50]
    assert list(nvml.policies)==[0,0]
