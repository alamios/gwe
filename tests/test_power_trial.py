# SPDX-License-Identifier: GPL-3.0-or-later
"""Fixed power-trial guard and journal recovery with simulated NVML only."""
import pytest

from gwe.nvml_power import PowerError, recover
from gwe.power_trial import TrialRecord, prepare


GPU = 'GPU-trial-test'
LOW = 240000
HIGH = 300000
BEFORE = 250000
REQUESTED = 240000


class FakeNvml:
    NVML_TEMPERATURE_GPU = 0

    def __init__(self):
        self.uuid = GPU
        self.name = 'NVIDIA GeForce RTX 3090 Ti'
        self.fans = 2
        self.policies = [0, 0]
        self.low, self.high = LOW, HIGH
        self.current = BEFORE
        self.temperature = 64
        self.setter_calls = []
        self.initialized = 0
        self.shutdowns = 0

    def nvmlInit(self):
        self.initialized += 1

    def nvmlShutdown(self):
        self.shutdowns += 1

    def nvmlDeviceGetHandleByUUID(self, uuid):
        assert uuid == GPU
        return 'handle'

    def nvmlDeviceGetUUID(self, handle):
        return self.uuid

    def nvmlDeviceGetName(self, handle):
        return self.name

    def nvmlDeviceGetNumFans(self, handle):
        return self.fans

    def nvmlDeviceGetFanControlPolicy_v2(self, handle, fan):
        return self.policies[fan]

    def nvmlDeviceGetPowerManagementLimitConstraints(self, handle):
        return self.low, self.high

    def nvmlDeviceGetPowerManagementLimit(self, handle):
        return self.current

    def nvmlDeviceGetTemperature(self, handle, sensor):
        assert sensor == self.NVML_TEMPERATURE_GPU
        return self.temperature

    def nvmlDeviceSetPowerManagementLimit(self, handle, value):
        self.setter_calls.append(value)
        self.current = value


@pytest.fixture
def setup(tmp_path):
    directory = tmp_path / 'power-trial-state'
    directory.mkdir(mode=0o700)
    directory.chmod(0o700)
    return directory, TrialRecord(directory), FakeNvml()


def test_prepare_records_fixed_guard_without_writing_gpu(setup):
    directory, record, nvml = setup

    prepare(nvml, directory, GPU)

    assert record.read(record.pending) == {
        'version': 1, 'gpu_uuid': GPU, 'previous_mw': BEFORE,
        'requested_mw': REQUESTED, 'outcome': 'pending',
    }
    assert nvml.setter_calls == []
    assert nvml.initialized == nvml.shutdowns == 1


@pytest.mark.parametrize('change', [
    lambda nvml: setattr(nvml, 'uuid', 'GPU-other'),
    lambda nvml: setattr(nvml, 'name', 'NVIDIA GeForce RTX 3090'),
    lambda nvml: setattr(nvml, 'fans', 1),
    lambda nvml: nvml.policies.__setitem__(0, 1),
    lambda nvml: setattr(nvml, 'current', 240000),
    lambda nvml: setattr(nvml, 'low', 240001),
    lambda nvml: setattr(nvml, 'high', 249999),
    lambda nvml: setattr(nvml, 'temperature', 65),
])
def test_prepare_refuses_baseline_mismatch_without_setter(tmp_path, change):
    directory = tmp_path / 'power-trial-state'
    directory.mkdir(mode=0o700)
    nvml = FakeNvml()
    change(nvml)
    record = TrialRecord(directory)

    with pytest.raises(PowerError):
        prepare(nvml, directory, GPU)

    assert nvml.setter_calls == []
    assert not record.pending.exists()
    assert nvml.initialized == nvml.shutdowns == 1


def test_prepare_refuses_other_pending_power_journal(setup):
    directory, record, nvml = setup
    from gwe.nvml_power import PowerRecord
    PowerRecord(directory).begin(GPU, BEFORE, REQUESTED)

    with pytest.raises(PowerError, match='recovery_pending'):
        prepare(nvml, directory, GPU)

    assert nvml.initialized == 0
    assert nvml.setter_calls == []
    assert not record.pending.exists()


def test_recover_trial_restores_original_250000_from_trial_value(setup):
    directory, record, nvml = setup
    row = record.begin(GPU, BEFORE, REQUESTED)
    nvml.current = REQUESTED

    result = recover(nvml, record, GPU)

    assert result == {'state': 'rolled_back', 'previous_mw': BEFORE, 'applied_mw': BEFORE}
    assert nvml.setter_calls == [BEFORE]
    assert nvml.current == BEFORE
    assert not record.pending.exists()
    assert record.read(record.last) == {**row, 'outcome': 'rolled_back'}


def test_committed_trial_record_is_preserved_by_recovery(setup):
    directory, record, nvml = setup
    row = record.begin(GPU, BEFORE, REQUESTED)
    record.finish(row, 'applied')
    committed = record.read(record.last)
    nvml.current = REQUESTED

    assert recover(nvml, record, GPU) == {'state': 'idle'}

    assert nvml.setter_calls == []
    assert nvml.current == REQUESTED
    assert record.read(record.last) == committed


def test_external_third_power_value_leaves_guard_pending_as_fault(setup):
    directory, record, nvml = setup
    record.begin(GPU, BEFORE, REQUESTED)
    nvml.current = 300000

    with pytest.raises(PowerError, match='external_power_change'):
        recover(nvml, record, GPU)

    assert nvml.setter_calls == []
    assert nvml.current == 300000
    assert record.pending.exists()
