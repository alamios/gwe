# SPDX-License-Identifier: GPL-3.0-or-later
import pytest
from gwe.fan_curve import FanCurve
from gwe.nvml_fan_control import FanControlError, NvmlFanController
from test_nvml_fan_trial import fake


@pytest.fixture
def session(fake):
    clock=[0.0]
    fake.nvmlDeviceGetTemperature=lambda *args:45
    controller=NvmlFanController(fake,'GPU-test',FanCurve(((40,30),(60,70))),clock=lambda:clock[0])
    controller.start()
    fake.state['resets'].clear()
    return controller,clock


def test_curve_updates_both_fans_and_stops(fake,session):
    controller,clock=session
    assert controller.tick()['duty_percent']==40
    clock[0]=1
    fake.nvmlDeviceGetTemperature=lambda *args:50
    assert controller.tick()['duty_percent']==50
    controller.stop()
    assert fake.state['writes']==[(0,40),(1,40),(0,50),(1,50)]
    assert fake.state['policies']==[0,0]
    assert controller.state=='closed'
    controller.stop()
    assert fake.state['resets']==[0,1]


def test_hysteresis_keeps_anchor_until_duty_changes(fake,session):
    controller,clock=session
    controller.tick()
    for temperature in (44,43):
        clock[0]+=1
        fake.nvmlDeviceGetTemperature=lambda *args:temperature
        assert controller.tick()['duty_percent']==40
    clock[0]+=1
    fake.nvmlDeviceGetTemperature=lambda *args:42
    assert controller.tick()['duty_percent']==34
    assert len(fake.state['writes'])==4


@pytest.mark.parametrize('temperature',[None,float('nan'),float('inf'),-1,85,True])
def test_bad_temperature_recovers_and_latches(fake,session,temperature):
    controller,clock=session
    controller.tick()
    fake.nvmlDeviceGetTemperature=lambda *args:temperature
    with pytest.raises(FanControlError):controller.tick()
    assert fake.state['policies']==[0,0]
    assert controller.state=='fault'
    fake.nvmlDeviceGetTemperature=lambda *args:45
    with pytest.raises(FanControlError):controller.tick()
    with pytest.raises(FanControlError):controller.start()


@pytest.mark.parametrize('elapsed',[6,-1,float('nan')])
def test_missed_tick_recovers(fake,session,elapsed):
    controller,clock=session
    controller.tick()
    clock[0]=elapsed
    with pytest.raises(FanControlError):controller.tick()
    assert fake.state['policies']==[0,0]


def test_slow_telemetry_cannot_write(fake,session):
    controller,clock=session
    def temperature(*args):
        clock[0]+=3
        return 45
    fake.nvmlDeviceGetTemperature=temperature
    with pytest.raises(FanControlError):controller.tick()
    assert fake.state['writes']==[]
    assert fake.state['resets']==[0,1]


@pytest.mark.parametrize('failed_fan',[0,1])
def test_partial_write_recovers_every_fan(fake,session,failed_fan):
    controller,clock=session
    original=fake.nvmlDeviceSetFanSpeed_v2
    def write(handle,fan,duty):
        if fan==failed_fan:raise PermissionError()
        original(handle,fan,duty)
    fake.nvmlDeviceSetFanSpeed_v2=write
    with pytest.raises(PermissionError):controller.tick()
    assert fake.state['resets']==[0,1]
    assert fake.state['policies']==[0,0]
    assert controller.state=='fault'


def test_failed_reset_still_attempts_second_fan_and_can_retry(fake,session):
    controller,clock=session
    controller.tick()
    original=fake.nvmlDeviceSetDefaultFanSpeed_v2
    def reset(handle,fan):
        if fan==0:raise PermissionError()
        original(handle,fan)
    fake.nvmlDeviceSetDefaultFanSpeed_v2=reset
    with pytest.raises(FanControlError):controller.stop()
    assert controller.state=='recovery_failed'
    assert fake.state['policies']==[1,0]
    assert controller.recovery_errors
    fake.nvmlDeviceSetDefaultFanSpeed_v2=original
    controller.stop()
    assert controller.state=='closed'
    assert fake.state['policies']==[0,0]


def test_identity_change_never_writes_replacement(fake,session):
    controller,clock=session
    controller.tick()
    fake.nvmlDeviceGetUUID=lambda handle:'GPU-replacement'
    with pytest.raises(FanControlError):controller.tick()
    assert controller.state=='recovery_failed'
    assert fake.state['resets']==[]
    assert len(fake.state['writes'])==2


@pytest.mark.parametrize('change',['count','limits','policy','target'])
def test_capability_or_ownership_change_aborts(fake,session,change):
    controller,clock=session
    controller.tick()
    if change=='count':fake.nvmlDeviceGetNumFans=lambda handle:1
    elif change=='limits':fake.nvmlDeviceGetMinMaxFanSpeed=lambda handle:(35,100)
    elif change=='policy':fake.state['policies'][1]=0
    else:fake.state['speeds'][1]=80
    with pytest.raises(FanControlError):controller.tick()
    assert controller.state=='fault'
    assert fake.state['policies']==[0,0]


def test_silent_mode_restores_and_reenters_manual(fake):
    controller=NvmlFanController(fake,'GPU-test',FanCurve(((40,30),(60,70)),vbios_silent=True))
    controller.start()
    controller.tick()
    fake.nvmlDeviceGetTemperature=lambda *args:39
    assert controller.tick()['state']=='automatic'
    assert fake.state['policies']==[0,0]
    fake.nvmlDeviceGetTemperature=lambda *args:40
    assert controller.tick()['duty_percent']==30


def test_existing_manual_controller_is_not_reset(fake):
    fake.state['policies'][0]=1
    controller=NvmlFanController(fake,'GPU-test',FanCurve(((40,30),)))
    with pytest.raises(FanControlError):controller.start()
    assert fake.state['resets']==[]
    assert fake.state['writes']==[]


def test_bad_profile_is_rejected_before_reset(fake):
    controller=NvmlFanController(fake,'GPU-test',FanCurve(((40,20),)))
    with pytest.raises(FanControlError):controller.start()
    assert fake.state['resets']==[]


def test_success_without_actual_manual_policy_is_failure(fake,session):
    controller,clock=session
    fake.nvmlDeviceSetFanSpeed_v2=lambda *args:None
    with pytest.raises(FanControlError):controller.tick()
    assert controller.state=='fault'
    assert fake.state['resets']==[0,1]


def test_interrupt_during_write_restores(fake,session):
    controller,clock=session
    original=fake.nvmlDeviceSetFanSpeed_v2
    def write(handle,fan,duty):
        original(handle,fan,duty)
        raise KeyboardInterrupt()
    fake.nvmlDeviceSetFanSpeed_v2=write
    with pytest.raises(KeyboardInterrupt):controller.tick()
    assert fake.state['policies']==[0,0]
    assert controller.state=='fault'
