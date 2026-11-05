from types import SimpleNamespace
import numpy as np
from examwatch.config import Settings
from examwatch.tracking import Tracker
from examwatch.vision import Vision


def test_visible_shoulders_continue_posture_when_face_detector_misses():
    settings = Settings()
    vision = Vision.__new__(Vision)
    vision.settings = settings
    vision.tracker = Tracker(settings)
    vision.last_timestamp = 0
    vision.faces = lambda frame: []
    vision.mp = SimpleNamespace(Image=lambda **kw: kw,ImageFormat=SimpleNamespace(SRGB=1))
    landmarks = [[.5,.35,0,1] for _ in range(33)]
    landmarks[11] = [.4,.5,0,1]
    landmarks[12] = [.6,.5,0,1]
    pose = [SimpleNamespace(x=p[0],y=p[1],z=p[2],visibility=p[3]) for p in landmarks]
    vision.pose = SimpleNamespace(detect_for_video=lambda *args: SimpleNamespace(pose_landmarks=[pose]))
    track = vision.tracker.update([[.425,.5,.15,.15]],0)[0]
    track.signal = dict(nose_y=.55,shoulder_y=.7,shoulder_x=.5,scale=.15,shoulder_width=.2)
    track.baseline = track.signal.copy()
    track.standing_rule.update(True,0)
    frame = np.zeros((480,640,3),np.uint8)
    for second in range(1,6):
        tracks,_ = vision.process(frame,[],now=second)
        assert len(tracks) == 1 and tracks[0].id == track.id
        assert tracks[0].posture == 'standing'
        assert tracks[0].baseline['nose_y'] == .55
        fired = track.standing_rule.update(True,second)
    assert fired
    assert track.mouth_points == [] and track.emotion == 'unknown'
    # Reliable body observations remain usable even for longer standing thresholds.
    assert vision.process(frame,[],now=9)[0][0].id == track.id
    vision.pose = SimpleNamespace(detect_for_video=lambda *args: SimpleNamespace(pose_landmarks=[]))
    assert vision.process(frame,[],now=10)[0] == []
    assert track.standing_rule.since is None
    assert vision.process(frame,[],now=18)[0] == []
    assert not vision.tracker.tracks
