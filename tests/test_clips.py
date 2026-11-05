import cv2
import numpy as np
from examwatch.clips import EvidenceClips


def test_clip_keeps_pre_and_post_roll_and_decodes_real_video(tmp_path):
    clips = EvidenceClips(tmp_path)
    for i in range(61):
        clips.push(np.full((120,160,3),i,np.uint8),i*.25)
        if i == 40:
            clips.trigger('evidence.webm',10,'Track 1 | standing')
    clips.close()
    cap = cv2.VideoCapture(str(tmp_path/'evidence.webm'))
    assert cap.isOpened()
    assert 14.5 <= cap.get(cv2.CAP_PROP_FRAME_COUNT)/cap.get(cv2.CAP_PROP_FPS) <= 15.5
    ok, frame = cap.read()
    assert ok and frame.shape[1] == 640
    cap.release()
    assert not list(tmp_path.glob('*.writing.webm'))


def test_stop_flushes_short_clip_and_new_session_has_no_old_frames(tmp_path):
    clips = EvidenceClips(tmp_path)
    clips.push(np.zeros((120,160,3),np.uint8),0)
    clips.trigger('short.webm',0,'Track 1')
    clips.reset()
    assert not clips.frames and not clips.pending
    clips.close()
    assert (tmp_path/'short.webm').is_file()
