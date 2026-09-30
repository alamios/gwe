# SPDX-License-Identifier: GPL-3.0-or-later
"""Real local socket transport, simulated backend; no GPU or root required."""
import json
import os
import socket
import threading

import pytest
from gwe.fan_service import FanService, FanClient, Lease, decode


class Backend:
    def __init__(self):
        self.starts=[]
        self.stops=0
        self.fail_start=False
        self.fail_stop=False
    def start(self,curve):
        self.starts.append(curve)
        if self.fail_start:raise RuntimeError('private backend error')
    def stop(self):
        self.stops+=1
        if self.fail_stop:raise RuntimeError('private recovery error')


def acquire():
    return {'version':1,'op':'acquire','points':[[40,30],[80,100]],'hysteresis':2,'vbios_silent':False}


def test_lease_expiry_rejects_late_renewal():
    now=[0];backend=Backend();lease=Lease(backend,lambda:now[0]);owner=object()
    assert lease.request(owner,decode(json.dumps(acquire()).encode()))['ok']
    now[0]=5
    assert lease.request(owner,{'op':'renew'})['error']=='not_owner'
    assert backend.stops==1
    assert lease.state=='idle'


def test_foreign_connection_cannot_renew_or_release():
    lease=Lease(Backend());owner=object();other=object()
    lease.request(owner,decode(json.dumps(acquire()).encode()))
    assert lease.request(other,{'op':'renew'})['error']=='not_owner'
    assert lease.request(other,{'op':'release'})['error']=='not_owner'
    assert lease.request(other,decode(json.dumps(acquire()).encode()))['error']=='busy'
    lease.disconnect(other)
    assert lease.owner is owner


@pytest.mark.parametrize('stop_failure',[False,True])
def test_failed_start_latches_and_redacts_errors(stop_failure):
    backend=Backend();backend.fail_start=True;backend.fail_stop=stop_failure
    lease=Lease(backend);owner=object()
    response=lease.request(owner,decode(json.dumps(acquire()).encode()))
    assert response=={'ok':False,'error':'recovery_failed' if stop_failure else 'fault'}
    assert not lease.request(owner,decode(json.dumps(acquire()).encode()))['ok']
    assert len(backend.starts)==1


def test_recovery_failure_blocks_new_owner():
    backend=Backend();lease=Lease(backend);owner=object()
    lease.request(owner,decode(json.dumps(acquire()).encode()))
    backend.fail_stop=True
    assert not lease.request(owner,{'op':'release'})['ok']
    assert lease.state=='recovery_failed'
    assert not lease.request(object(),decode(json.dumps(acquire()).encode()))['ok']


@pytest.mark.parametrize('packet',[
 b'{}',b'[]',b'{"version":1,"version":1,"op":"status"}',
 b'{"version":true,"op":"status"}',b'{"version":1,"op":"power"}',
 b'{"version":1,"op":"status","uuid":"GPU-secret"}',b'x'*4097,
 b'{"version":1,"op":"acquire","points":[],"hysteresis":2,"vbios_silent":false}',
])
def test_strict_protocol(packet):
    with pytest.raises(ValueError):decode(packet)


@pytest.fixture
def server(tmp_path):
    tmp_path.chmod(0o700)
    backend=Backend();service=FanService(tmp_path/'fan.sock',backend,allowed_uid=os.getuid())
    stop=threading.Event();errors=[]
    def run():
        try:
            while not stop.is_set():service.step(0.01)
        except BaseException as error:errors.append(error)
    thread=threading.Thread(target=run);thread.start()
    yield service,backend
    stop.set();thread.join(2)
    service.close()
    assert not thread.is_alive()
    assert not errors


def test_client_protocol_over_real_socket(server):
    service,backend=server
    client=FanClient(service.path)
    other=FanClient(service.path)
    try:
        request=acquire();request.pop('version');op=request.pop('op')
        assert client.request(op,**request)['ok']
        assert other.request('renew')['error']=='not_owner'
        assert client.request('renew')['ok']
        assert client.request('status')=={'ok':True,'state':'active','owned':True}
        assert client.request('release')=={'ok':True,'state':'idle'}
        assert backend.stops==1
    finally:client.close();other.close()


def test_malformed_owner_packet_restores(server):
    service,backend=server;client=FanClient(service.path)
    try:
        data=acquire();data.pop('version');op=data.pop('op')
        client.request(op,**data)
        client.socket.send(b'not-json')
        assert json.loads(client.socket.recv(4096))['error']=='invalid_request'
        assert backend.stops==1
    finally:client.close()


def test_disconnect_releases_owner(tmp_path):
    tmp_path.chmod(0o700);backend=Backend()
    service=FanService(tmp_path/'fan.sock',backend,allowed_uid=os.getuid())
    client=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET)
    try:
        client.connect(str(service.path));service.step(0)
        client.send(json.dumps(acquire()).encode());service.step(.01)
        assert json.loads(client.recv(4096))['ok']
        client.close();service.step(.01)
        assert backend.stops==1
        assert service.lease.owner is None
    finally:client.close();service.close()


def test_kernel_credentials_reject_wrong_uid(tmp_path):
    tmp_path.chmod(0o700);backend=Backend()
    service=FanService(tmp_path/'fan.sock',backend,allowed_uid=os.getuid()+1)
    client=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET)
    try:
        client.connect(str(service.path));service.step(0)
        assert client.recv(1)==b''
        assert not backend.starts
    finally:client.close();service.close()


def test_existing_path_is_preserved(tmp_path):
    tmp_path.chmod(0o700);path=tmp_path/'fan.sock';path.write_text('preserve')
    with pytest.raises(OSError):FanService(path,Backend(),allowed_uid=os.getuid())
    assert path.read_text()=='preserve'
