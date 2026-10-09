# SPDX-License-Identifier: GPL-3.0-or-later
"""Service adapters with real processes and shared simulated device state."""
import multiprocessing
import os
import signal
import time

import pytest
from gwe.fan_curve import FanCurve
from gwe.fan_process import ProcessBackend
from gwe.fan_service import Lease, boot_time
from test_fan_supervisor import SharedNvml


class Device(SharedNvml):
    def __init__(self, context):
        super().__init__(context)
        self.reset_mode=context.Value('i',0)
        self.lost=context.Value('i',0)
    def nvmlInit(self):pass
    def nvmlShutdown(self):pass
    def nvmlDeviceGetUUID(self,handle):return 'GPU-other' if self.lost.value else 'GPU-test'
    def nvmlDeviceSetDefaultFanSpeed_v2(self,handle,fan):
        if self.reset_mode.value==1:raise PermissionError()
        if self.reset_mode.value==2:time.sleep(30)
        super().nvmlDeviceSetDefaultFanSpeed_v2(handle,fan)


class Factory:
    def __init__(self,device):self.device=device
    def __call__(self):return self.device


def until(backend, predicate, timeout=5):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        backend.poll()
        if predicate():return
        time.sleep(.01)
    raise AssertionError(f'Timed out in {backend.state}')


@pytest.fixture
def setup():
    device=Device(multiprocessing.get_context('spawn'))
    backend=ProcessBackend('GPU-test',factory=Factory(device),heartbeat=.5,recovery_timeout=.5)
    yield device,backend
    backend.close()


def start(backend):
    backend.start(FanCurve(((40,30),(60,70))))
    until(backend,lambda:backend.state=='active')


def test_release_is_asynchronous_and_verified(setup):
    device,backend=setup
    start(backend)
    assert list(device.policies)==[1,1]
    backend.stop()
    assert backend.state=='stopping'
    with pytest.raises(RuntimeError):backend.start(FanCurve(((40,30),)))
    until(backend,lambda:backend.state=='idle')
    assert list(device.policies)==[0,0]


def test_supervisor_suspend_recovers_then_allows_fresh_acquisition(setup, monkeypatch):
    device, backend = setup
    start(backend)
    assert list(device.policies) == [1, 1]
    monkeypatch.setattr('gwe.fan_process.boot_time', lambda: boot_time() + 60)
    backend.poll()
    until(backend, lambda: backend.state == 'idle')
    assert not backend.failure and list(device.policies) == [0, 0]
    start(backend)
    assert list(device.policies) == [1, 1]
    backend.stop()
    until(backend, lambda: backend.state == 'idle')
    assert list(device.policies) == [0, 0]


@pytest.mark.parametrize('fault',[signal.SIGKILL,signal.SIGSTOP])
def test_worker_fault_latches_after_verified_recovery(setup,fault):
    device,backend=setup
    start(backend)
    os.kill(backend.worker.pid,fault)
    until(backend,lambda:backend.state=='fault')
    assert list(device.policies)==[0,0]
    with pytest.raises(RuntimeError):backend.start(FanCurve(((40,30),)))


def test_parent_connection_loss_restores_without_polling(setup):
    device,backend=setup
    start(backend)
    process=backend.worker
    backend.channel.close()
    process.join(3)
    assert not process.is_alive()
    assert list(device.policies)==[0,0]
    # Close the dead process through the adapter's normal recovery path.


@pytest.mark.parametrize('mode',[1,2])
def test_failed_or_hung_recovery_blocks_reacquisition(setup,mode):
    device,backend=setup
    start(backend)
    device.reset_mode.value=mode
    backend.stop()
    until(backend,lambda:backend.state=='recovery_failed')
    with pytest.raises(RuntimeError):backend.start(FanCurve(((40,30),)))


def test_existing_manual_owner_is_not_reset(setup):
    device,backend=setup
    device.policies[0]=1
    backend.start(FanCurve(((40,30),)))
    until(backend,lambda:backend.state=='fault')
    assert list(device.policies)==[1,0]
    assert backend.fans==()


def test_service_disconnect_recovers_through_lease(setup):
    device,backend=setup
    lease=Lease(backend)
    owner=object()
    response=lease.request(owner,{'op':'acquire','curve':FanCurve(((40,30),(60,70)))})
    assert response['state']=='starting'
    until(backend,lambda:backend.state=='active')
    lease.disconnect(owner)
    assert lease.state=='stopping'
    until(backend,lambda:backend.state=='idle')
    lease.expire()
    assert lease.state=='idle'
    assert list(device.policies)==[0,0]


def test_late_renewal_cannot_restart_worker(setup):
    device,backend=setup
    now=[boot_time()]
    lease=Lease(backend,clock=lambda:now[0])
    owner=object()
    lease.request(owner,{'op':'acquire','curve':FanCurve(((40,30),(60,70)))})
    until(backend,lambda:backend.state=='active')
    now[0]+=6
    assert not lease.request(owner,{'op':'renew'})['ok']
    until(backend,lambda:backend.state=='idle')
    assert list(device.policies)==[0,0]


def test_record_failure_prevents_manual_control(setup):
    device,backend=setup
    def record(fans):raise OSError('cannot persist ownership')
    backend.record=record
    backend.start(FanCurve(((40,30),)))
    until(backend,lambda:backend.state=='fault')
    assert list(device.targets)==[0,0]


def test_service_poll_surfaces_worker_failure(setup):
    device,backend=setup
    lease=Lease(backend)
    owner=object()
    lease.request(owner,{'op':'acquire','curve':FanCurve(((40,30),))})
    until(backend,lambda:backend.state=='active')
    os.kill(backend.worker.pid,signal.SIGKILL)
    until(backend,lambda:backend.state=='fault')
    response=lease.request(owner,{'op':'status'})
    assert response=={'ok':True,'state':'fault','owned':False}


def test_real_socket_client_disconnect_waits_for_recovery(tmp_path):
    import threading
    from gwe.fan_service import FanService, FanClient
    device=Device(multiprocessing.get_context('spawn'))
    backend=ProcessBackend('GPU-test',factory=Factory(device))
    tmp_path.chmod(0o700)
    service=FanService(tmp_path/'control.sock',backend,allowed_uid=os.getuid())
    stop=threading.Event();errors=[]
    def run():
        try:
            while not stop.is_set():service.step(.01)
        except BaseException as error:errors.append(error)
    thread=threading.Thread(target=run);thread.start()
    client=FanClient(service.path)
    try:
        response=client.request('acquire',points=[[40,30],[60,70]],hysteresis=2,vbios_silent=False)
        assert response['state']=='starting'
        end=time.monotonic()+5
        while time.monotonic()<end and client.request('status')['state']!='active':time.sleep(.01)
        assert list(device.policies)==[1,1]
        assert client.request('renew')['ok']
        client.close()
        end=time.monotonic()+5
        while time.monotonic()<end and backend.state!='idle':time.sleep(.01)
        assert backend.state=='idle'
        assert list(device.policies)==[0,0]
    finally:
        client.close();stop.set();thread.join(2);service.close();backend.close()
    assert not errors


def parent_service(ready, device):
    backend=ProcessBackend('GPU-test',factory=Factory(device))
    try:
        start(backend)
        ready.send('active')
        end=time.monotonic()+15
        while time.monotonic()<end and backend.state in ('starting','active'):
            backend.renew(boot_time()+5)
            backend.poll()
            time.sleep(.05)
    finally:
        backend.close()
        ready.close()


@pytest.mark.parametrize('fault',[signal.SIGKILL,signal.SIGSTOP])
def test_dead_or_frozen_service_worker_restores_independently(fault):
    context=multiprocessing.get_context('spawn')
    device=Device(context)
    receiver,sender=context.Pipe(duplex=False)
    parent=context.Process(target=parent_service,args=(sender,device))
    parent.start();sender.close()
    try:
        assert receiver.poll(5) and receiver.recv()=='active'
        assert list(device.policies)==[1,1]
        os.kill(parent.pid,fault)
        end=time.monotonic()+7
        while time.monotonic()<end and list(device.policies)!=[0,0]:time.sleep(.02)
        assert list(device.policies)==[0,0]
    finally:
        if fault==signal.SIGSTOP and parent.is_alive():os.kill(parent.pid,signal.SIGCONT)
        parent.join(5)
        if parent.is_alive():parent.kill();parent.join(2)
        receiver.close()


@pytest.mark.parametrize('scenario',['normal','disconnect','expire'])
def test_unprivileged_trial_client_end_to_end(tmp_path,scenario):
    import threading
    from gwe.fan_service import FanService
    from gwe.fan_client_trial import run
    device=Device(multiprocessing.get_context('spawn'))
    backend=ProcessBackend('GPU-test',factory=Factory(device))
    tmp_path.chmod(0o700)
    service=FanService(tmp_path/'control.sock',backend,allowed_uid=os.getuid())
    stopping=threading.Event();errors=[]
    def serve():
        try:
            while not stopping.is_set():service.step(.01)
        except BaseException as error:errors.append(error)
    thread=threading.Thread(target=serve);thread.start()
    try:
        run(service.path,scenario)
        assert backend.state=='idle'
        assert list(device.policies)==[0,0]
    finally:
        stopping.set();thread.join(2);service.close();backend.close()
    assert not errors
