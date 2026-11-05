import math
from examwatch.rules import body_angles, AngleWatch


def pose(lean=0, arm=0, width=640, height=480, hips=True):
    points=[[0,0,0,0] for _ in range(33)]
    angle=math.radians(lean)
    down=(-math.sin(angle),math.cos(angle))
    across=(math.cos(angle),math.sin(angle))
    def put(i,x,y): points[i]=[x/width,y/height,0,1]
    for i,sign in [(11,-1),(12,1)]:
        x,y=320+sign*60*across[0],180+sign*60*across[1]
        put(i,x,y)
        rad=math.radians(arm if i==11 else 0)
        dx=down[0]*math.cos(rad)-down[1]*math.sin(rad)
        dy=down[0]*math.sin(rad)+down[1]*math.cos(rad)
        put(i+2,x+60*dx,y+60*dy)
        if hips: put(i+12,x+120*down[0],y+120*down[1])
    return points


def test_pixel_angles_and_occluded_hips():
    for width,height in [(640,480),(960,540)]:
        for hips in [True,False]:
            result=body_angles(pose(35,60,width,height,hips),width,height)
            if hips:
                assert abs(result['lean']-35)<1e-5
            else:
                assert result['lean'] is None
            assert abs(result['left_arm']-60)<1e-5
            assert abs(result['right_arm'])<1e-5
            assert result['lean_source']==('abdomen_hips' if hips else 'abdomen_uncalibrated')


def test_hidden_and_invalid_points_not_used():
    p=pose()
    p[13][3]=.1
    assert body_angles(p,640,480)['left_arm'] is None
    p[11][0]=float('nan')
    assert body_angles(p,640,480)['lean'] is None
    assert body_angles([],640,480)['lean'] is None


def test_arm_flags_then_growth_once_not_constant_angle():
    rule=AngleWatch(45.000001)
    assert not rule.update(45,0) and not rule.flagged
    assert not rule.update(50,1) and rule.flagged
    assert not rule.update(50,2)
    assert rule.update(70,3)
    assert not rule.update(80,4)
    rule.update(None,5)
    assert not rule.flagged and rule.value is None


def test_lean_hold_growth_and_gap_reset():
    rule=AngleWatch(20,2)
    assert not rule.update(20,0) and rule.flagged
    assert not rule.update(20,1)
    assert rule.update(20,2)
    assert not rule.update(40,3)
    assert not rule.update(40,7)  # gap starts fresh
    assert not rule.update(None,8) and not rule.flagged
    assert not rule.update(31,9)
    assert rule.update(50,10)


def test_abdomen_pivot_detects_lateral_lean_with_level_shoulders():
    for width,height in [(640,480),(960,540)]:
        seated=pose(width=width,height=height,hips=False)
        seed=body_angles(seated,width,height)['lean_origin']
        shifted=[p[:] for p in seated]
        for i in (11,12,13,14):
            shifted[i][0]+=math.tan(math.radians(22))*120/width
        result=body_angles(shifted,width,height,seed)
        assert abs(result['lean']-22)<1e-5
        assert result['lean_origin']==seed
        assert result['lean_source']=='abdomen_calibrated'
        assert abs(result['left_arm'])<1e-5
        from examwatch.tracking import Track
        track=Track(1,[0,0,.1,.1],0)
        assert track.lean_rule.threshold==20
        assert not track.lean_rule.update(result['lean'],0)
        assert track.lean_rule.flagged
        assert track.lean_rule.update(result['lean'],2)


def test_hip_abdomen_pivot_is_between_hips_and_shoulders():
    result=body_angles(pose(lean=25),640,480)
    origin=result['lean_origin']
    target=result['lean_target']
    assert origin[1]>target[1]
    assert abs(math.hypot((origin[0]-target[0])*640,(origin[1]-target[1])*480)-90)<1e-5


def test_calibrated_pivot_does_not_jump_when_hips_reappear():
    seed=body_angles(pose(hips=False),640,480)['lean_origin']
    for hips in [False,True,False,True]:
        result=body_angles(pose(lean=25,hips=hips),640,480,seed)
        assert result['lean_source']=='abdomen_calibrated'
        assert result['lean_origin']==seed
