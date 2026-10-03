# SPDX-License-Identifier: GPL-3.0-or-later
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest

spec=importlib.util.spec_from_file_location('configure_fan_service',Path(__file__).resolve().parents[1]/'scripts/configure_fan_service.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def binding():
    calls=[]
    return SimpleNamespace(calls=calls,nvmlInit=lambda:calls.append('init'),nvmlShutdown=lambda:calls.append('shutdown'),
        nvmlDeviceGetCount=lambda:1,nvmlDeviceGetHandleByIndex=lambda index:object(),
        nvmlDeviceGetName=lambda handle:'NVIDIA GeForce RTX 3090 Ti',nvmlDeviceGetNumFans=lambda handle:2,
        nvmlDeviceGetUUID=lambda handle:'GPU-test')


def test_placeholder_is_replaced_using_reads_only():
    nvml=binding()
    result=module.configuration(module.PLACEHOLDER,1000,nvml)
    assert result=={'version':1,'allowed_uid':1000,'gpu_uuid':'GPU-test'}
    assert nvml.calls==['init','shutdown']


def test_existing_configuration_never_initializes_nvml():
    nvml=binding()
    with pytest.raises(ValueError):module.configuration({'gpu_uuid':'keep'},1000,nvml)
    assert nvml.calls==[]


def test_root_account_is_rejected_before_device_access():
    nvml=binding()
    with pytest.raises(ValueError):module.configuration(module.PLACEHOLDER,0,nvml)
    assert nvml.calls==[]


def test_unexpected_gpu_still_shuts_down():
    nvml=binding();nvml.nvmlDeviceGetCount=lambda:2
    with pytest.raises(ValueError):module.configuration(module.PLACEHOLDER,1000,nvml)
    assert nvml.calls==['init','shutdown']
