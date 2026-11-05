import numpy as np
from examwatch.config import Settings
from examwatch.tracking import Tracker, identify


def test_identity_unknown_and_close_runner_up():
    vector = np.array([1.,0.])
    gallery = [{'id':'A','embeddings':[[1.,0.]]},{'id':'B','embeddings':[[.99,.1]]}]
    assert identify(vector,gallery,.45,.06)[0] is None
    assert identify(vector,gallery[:1],.45,.06)[0]['id'] == 'A'
    assert identify(np.array([0.,1.]),gallery[:1],.45,.06)[0] is None


def test_tracks_do_not_share_id_and_missing_preserves_calibration():
    tracker = Tracker(Settings())
    initial = tracker.update([[.1,.2,.1,.1],[.6,.2,.1,.1]],0)
    first = initial[0]
    first.baseline = {'seated':True}
    first.standing_rule.update(True,0)
    active = tracker.update([[.61,.2,.1,.1]],.5)
    assert active[0].id == initial[1].id
    assert first.baseline == {'seated':True}
    new = tracker.update([[.1,.2,.1,.1]],2)
    assert new[0].id == first.id
    assert new[0].baseline == {'seated':True}
    assert tracker.update([[.1,.2,.1,.1]],11)[0].id != first.id


def test_calibration_cache_is_session_local_and_survives_track_expiry():
    tracker = Tracker(Settings())
    track = tracker.update([[.1,.2,.1,.1]],0)[0]
    track.student_id = 'A'
    track.baseline = {'nose_y': .3}
    tracker.update([],10)
    assert tracker.calibrations['A'] == {'nose_y': .3}
    assert Tracker(Settings()).calibrations == {}


def test_unknown_identity_does_not_destroy_baseline():
    track = Tracker(Settings()).update([[.1,.2,.1,.1]],0)[0]
    track.baseline = {'nose_y': .3}
    track.standing_rule.update(True,0)
    track.clear_identity(preserve_baseline=True)
    assert track.baseline == {'nose_y': .3}
    assert track.standing_rule.since == 0
    track.clear_identity()
    assert track.baseline is None


def test_rising_face_retains_calibration_without_bbox_overlap():
    tracker = Tracker(Settings())
    track = tracker.update([[.2,.5,.1,.1]],0)[0]
    track.baseline = {'nose_y': .55}
    rising = tracker.update([[.2,.3,.1,.1]],.5)[0]
    assert rising.id == track.id and rising.baseline == {'nose_y': .55}


def test_ambiguous_recovery_does_not_transfer_calibration():
    tracker = Tracker(Settings())
    original = tracker.update([[.2,.5,.1,.1],[.3,.5,.1,.1]],0)
    for track in original:
        track.baseline = {'nose_y': .55}
    recovered = tracker.update([[.25,.3,.1,.1]],.5)[0]
    assert recovered.id not in [t.id for t in original]
    assert recovered.baseline is None
