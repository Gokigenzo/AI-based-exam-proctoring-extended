from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import numpy as np
from examwatch.config import Settings
from examwatch.tracking import Tracker
from examwatch.vision import Vision


def test_second_person_uses_multi_on_same_frame_and_keeps_occluded_track_capacity():
    v=Vision.__new__(Vision)
    v.settings=Settings()
    v.tracker=Tracker(v.settings)
    v.last_timestamp=0
    v.previous_face_count=0
    v.face_worker=ThreadPoolExecutor(max_workers=1)
    v.multi_pose=None
    calls=[]
    def engine(count):
        return SimpleNamespace(detect_for_video=lambda image,t:(calls.append((count,t)) or SimpleNamespace(pose_landmarks=[])),close=lambda:None)
    v.pose=engine(1)
    loaded=[]
    v.make_pose=lambda count:(loaded.append(count) or engine(count))
    v.mp=SimpleNamespace(Image=lambda **kw:kw,ImageFormat=SimpleNamespace(SRGB=1))
    faces=[np.array([10,10,30,40,15,20,30,20,23,25,17,35,28,35,1.]),
           np.array([160,10,30,40,165,20,180,20,173,25,167,35,178,35,1.])]
    v.faces=lambda frame:faces
    v.predict_emotion=lambda *args:None
    frame=np.zeros((240,320,3),np.uint8)
    try:
        tracks,_=v.process(frame,[],now=1)
        assert len(tracks)==2 and loaded==[3]
        assert [n for n,_ in calls]==[1,3]
        faces=faces[:1]
        v.process(frame,[],now=1.1)
        assert calls[-1][0]==3  # missed face must not silently disable multi-person pose
        v.process(frame,[],now=10)
        v.process(frame,[],now=10.1)
        assert calls[-1][0]==1
        assert loaded==[3]  # model is reused, not loaded for every image
    finally:
        v.close()
