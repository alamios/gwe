# SPDX-License-Identifier: GPL-3.0-or-later
import pytest
from gwe.fan_curve import FanCurve


@pytest.mark.parametrize('temperature,duty', [(0,30),(40,30),(50,50),(60,70),(80,100),(100,100)])
def test_interpolation_and_endpoints(temperature, duty):
    assert FanCurve(((40,30),(60,70),(80,100))).target(temperature) == duty


def test_cooling_hysteresis_boundary_and_warming():
    curve = FanCurve(((40,30),(60,70)), hysteresis=2)
    assert curve.demand(59,70,60) == 70
    assert curve.demand(58,70,60) == 70
    assert curve.demand(57,70,60) == 64
    assert curve.demand(60,64,57) == 70


def test_silent_mode_is_automatic_below_first_point():
    curve = FanCurve(((40,30),(60,70)), vbios_silent=True)
    assert curve.demand(39,30,40) is None
    assert curve.demand(40,None,None) == 30


def test_zero_hysteresis_and_python_rounding():
    curve=FanCurve(((40,30),(60,70)), hysteresis=0)
    assert curve.demand(59,70,60)==68
    assert curve.target(40.25)==30
    assert curve.target(40.75)==32


@pytest.mark.parametrize('points', [(),((40,30),(40,40)),((60,30),(40,40)),((40,70),(60,30)),((40,-1),),((40,101),),((None,30),),((40,float('nan')),),((40,30,1),)])
def test_invalid_curves(points):
    with pytest.raises(ValueError):
        FanCurve(points)


def test_source_points_cannot_mutate_curve():
    points=[[40,30],[60,70]]
    curve=FanCurve(points)
    points[0][1]=100
    assert curve.target(40)==30


def test_out_of_range_profile_is_not_silently_clamped():
    with pytest.raises(ValueError):
        FanCurve(((40,0),(60,70)),vbios_silent=True).validate_limits(30,100)
