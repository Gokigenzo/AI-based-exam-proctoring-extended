import pytest
from examwatch.rules import Sustained, classify_posture, posture_signal


@pytest.mark.parametrize('seconds', [5,20])
def test_threshold_and_one_alert_per_continuous_episode(seconds):
    rule = Sustained(seconds)
    assert not rule.update(True, 0)
    for t in range(1, seconds):
        assert not rule.update(True, t)
    assert rule.update(True, seconds)
    assert not rule.update(True, seconds+1)
    assert not rule.update(False, seconds+2)
    for t in range(seconds+3, seconds*2+3):
        assert not rule.update(True, t)
    assert rule.update(True, seconds*2+3)


def test_lost_observation_breaks_timer():
    rule = Sustained(5)
    for t in (0,1,2,3,4):
        assert not rule.update(True,t)
    assert not rule.update(True,8)
    assert rule.elapsed(8) == 0
    assert not rule.update(False,9)
    assert not rule.update(True,10)


def test_occluded_shoulders_do_not_become_standing():
    assert posture_signal(None,[0,0,.1,.1]) is None
    landmarks = [[.5,.5,0,.9] for _ in range(33)]
    landmarks[11] = [.4,.6,0,.2]
    landmarks[12] = [.6,.6,0,.9]
    assert posture_signal(landmarks,[.4,.3,.1,.1]) is None


def test_upper_body_requires_calibration_and_coherent_rise():
    seated = dict(nose_y=.4,shoulder_y=.6,shoulder_x=.5,scale=.1,shoulder_width=.2)
    standing = {**seated,'nose_y':.26,'shoulder_y':.46}
    assert classify_posture(None,standing) == 'uncalibrated'
    assert classify_posture(seated,None) == 'insufficient'
    assert classify_posture(seated,seated) == 'seated'
    assert classify_posture(seated,standing) == 'standing'
    assert classify_posture(seated,{**seated,'nose_y':.2}) == 'seated'
    assert classify_posture(seated,{**standing,'shoulder_x':.8}) == 'insufficient'
