import base64
import threading
import time
import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from examwatch.config import Settings
from examwatch.main import create_app
from examwatch.runtime import Runtime
from examwatch.tracking import Track

OWNER = 'test-browser-123'


class FakeVision:
    def __init__(self, settings):
        self.track = Track(1,[.1,.1,.2,.2],time.monotonic())
        self.track.signal = dict(nose_y=.4,shoulder_y=.6,shoulder_x=.5,scale=.1,shoulder_width=.2)
        self.track.posture = 'standing'
        self.track.standing_rule.seconds = 0
        self.track.emotion_rule.seconds = 0
        self.track.emotion, self.track.emotion_score = 'sad',.9

    def reset(self):
        self.track.standing_rule.reset()
        self.track.emotion_rule.reset()

    def close(self):
        pass

    def process(self, frame, gallery):
        return [self.track],False

    def enrollment(self, frame):
        return [1.,0.,0.]


class FakeSpeech:
    def __init__(self, settings):
        self.release = threading.Event()

    def transcribe(self, samples, rate):
        self.release.wait(3)
        return [dict(start=0,end=.1,text='Nội dung thử nghiệm')]


@pytest.fixture
def client(tmp_path):
    settings = Settings(data=tmp_path/'data',models=tmp_path/'models')
    runtime = Runtime(settings,FakeVision,FakeSpeech)
    with TestClient(create_app(settings,runtime)) as client:
        yield client,runtime
        if runtime.speech:
            runtime.speech.release.set()


def jpeg():
    return cv2.imencode('.jpg', np.zeros((240,320,3),np.uint8))[1].tobytes()


def start(client):
    response = client.post('/api/sessions',json={'title':'Phiên thử','owner':OWNER})
    assert response.status_code == 201,response.text
    return response.json()


def test_configurable_standing_threshold_resets_active_timer_and_persists(client):
    client,runtime=client
    session=start(client)
    track=runtime.vision.track
    runtime.visible=[track]
    track.standing_rule.update(True,100)
    response=client.post('/api/settings/alerts',json={'standing_threshold_seconds':7})
    assert response.status_code==200
    assert runtime.status()['standing_threshold_seconds']==7
    assert track.standing_rule.seconds==7 and track.standing_rule.since is None
    for second in range(7):assert not track.standing_rule.update(True,200+second)
    assert track.standing_rule.update(True,207)
    # Posting the same threshold must not reset an ongoing timer.
    client.post('/api/settings/alerts',json={'standing_threshold_seconds':7})
    assert track.standing_rule.since==200
    client.post('/api/sessions/stop',json={'session_id':session['id']})
    other=Runtime(Settings(data=runtime.settings.data,models=runtime.settings.models),FakeVision,FakeSpeech)
    assert other.settings.standing_seconds==7
    other.close()


@pytest.mark.parametrize('value',[0,301,2.5,True,'5'])
def test_invalid_standing_threshold_rejected(client,value):
    client,runtime=client
    assert client.post('/api/settings/alerts',json={'standing_threshold_seconds':value}).status_code==422
    assert runtime.settings.standing_seconds==5


def test_registration_validation_and_duplicate_id(client):
    client,runtime=client
    image=base64.b64encode(jpeg()).decode()
    body={'student_id':'TS001','name':'Nguyễn An','images':[image]*3}
    assert client.post('/api/students',json=body).status_code==201
    assert client.post('/api/students',json=body).status_code==409
    rows=client.get('/api/students').json()
    assert rows[0]['samples']==3 and 'embeddings' not in rows[0]
    start(client)
    assert client.delete('/api/students/TS001').status_code==400


def test_alert_evidence_history_and_session_isolation(client):
    client,runtime=client
    row=start(client)
    suffix=f"?owner={OWNER}&capture_id={row['capture_id']}"
    assert client.post('/api/frames'+suffix,content=jpeg()).status_code==200
    data=client.get('/api/sessions/'+row['id']).json()
    assert {a['kind'] for a in data['alerts']}=={'standing','negative_emotion'}
    for alert in data['alerts']:
        if alert['kind'] == 'standing':
            assert alert['evidence_type'] == 'video'
            assert alert['evidence_status'] == 'pending'
            runtime.clips.finish(alert['image'])
        else:
            assert client.get(f"/api/alerts/{alert['id']}/image").headers['content-type']=='image/jpeg'
        assert alert['created_at'] and alert['offset_seconds']>=0
    assert client.post('/api/frames'+suffix,content=jpeg()).status_code==200
    assert len(client.get('/api/sessions/'+row['id']).json()['alerts'])==2
    assert client.post('/api/calibrate',json={'owner':OWNER}).json()['calibrated']==1
    assert client.post('/api/sessions/stop',json={'session_id':'stale-session'}).status_code==409
    assert client.post('/api/sessions/stop',json={'session_id':row['id']}).status_code==200
    assert client.post('/api/frames'+suffix,content=jpeg()).status_code==400
    second=start(client)
    assert client.post('/api/frames'+suffix,content=jpeg()).status_code==409
    export=client.get(f"/api/sessions/{row['id']}/export").json()
    assert len(export['alerts'])==2 and export['session']['ended_at']
    assert not client.get('/api/sessions/'+second['id']).json()['alerts']


def test_audio_finishes_into_original_session_after_stop(client):
    client,runtime=client
    first=start(client)
    suffix=f"?owner={OWNER}&capture_id={first['capture_id']}&offset=0&rate=16000"
    pcm=np.zeros(1600,dtype='<f4').tobytes()
    assert client.post('/api/audio'+suffix,content=pcm).status_code==202
    assert client.post('/api/audio'+suffix,content=pcm).status_code==400
    client.post('/api/sessions/stop',json={'session_id':first['id']})
    second=start(client)
    runtime.speech.release.set()
    runtime.audio.join()
    data=client.get('/api/sessions/'+first['id']).json()
    assert data['transcripts'][0]['text']=='Nội dung thử nghiệm'
    assert not client.get('/api/sessions/'+second['id']).json()['transcripts']


def test_standing_video_served_after_background_encoding(client):
    client,runtime=client
    row=start(client)
    suffix=f"?owner={OWNER}&capture_id={row['capture_id']}"
    client.post('/api/frames'+suffix,content=jpeg())
    alert=next(a for a in runtime.store.records(row['id'],'alerts') if a['kind']=='standing')
    assert client.get(f"/api/alerts/{alert['id']}/video").status_code == 404
    runtime.clips.finish(alert['image'])
    runtime.clips.pool.submit(lambda: None).result(timeout=10)
    response=client.get(f"/api/alerts/{alert['id']}/video")
    assert response.status_code == 200 and response.headers['content-type']=='video/webm'
    assert response.content[:4] == b'\x1aE\xdf\xa3'
    assert client.get(f"/api/alerts/{alert['id']}/image").status_code == 404
    alert=next(a for a in runtime.store.records(row['id'],'alerts') if a['kind']=='standing')
    assert alert['evidence_status']=='ready'


def test_arm_and_lean_flags_create_distinct_video_alerts(client,monkeypatch):
    client,runtime=client
    row=start(client)
    track=runtime.vision.track
    track.posture='seated'
    track.emotion='neutral'
    readings={'left_arm':50.,'right_arm':0.,'lean':31.,'lean_source':'shoulders_hips'}
    monkeypatch.setattr('examwatch.runtime.body_angles',lambda *args:readings.copy())
    suffix=f"?owner={OWNER}&capture_id={row['capture_id']}"
    result=client.post('/api/frames'+suffix,content=jpeg()).json()
    assert set(result['tracks'][0]['pose_flags'])=={'left_arm','lean'}
    assert runtime.store.records(row['id'],'alerts')==[]
    # Advance only the two new rules; leave application clock/session untouched.
    track.left_arm_rule.since-=1
    track.lean_rule.since-=1
    readings.update(left_arm=75.,lean=51.)
    client.post('/api/frames'+suffix,content=jpeg())
    alerts=runtime.store.records(row['id'],'alerts')
    assert {a['kind'] for a in alerts}=={'arm_raise','body_lean'}
    assert all(a['evidence_type']=='video' for a in alerts)
    client.post('/api/frames'+suffix,content=jpeg())
    assert len(runtime.store.records(row['id'],'alerts'))==2
    client.post('/api/sessions/stop',json={'session_id':row['id']})
    runtime.clips.pool.submit(lambda:None).result(timeout=10)
    assert all(a['evidence_status']=='ready' for a in runtime.store.records(row['id'],'alerts'))


def test_frame_processing_reuses_session_gallery_without_querying_database(client,monkeypatch):
    client,runtime=client
    runtime.store.add_student('fixture','Fixture',[[1.,0.,0.]])
    row=start(client)
    assert runtime.gallery[0]['id']=='fixture'
    def forbidden(*args,**kwargs):
        raise AssertionError('Per-frame gallery reload')
    monkeypatch.setattr(runtime.store,'students',forbidden)
    suffix=f"?owner={OWNER}&capture_id={row['capture_id']}"
    assert client.post('/api/frames'+suffix,content=jpeg()).status_code==200
    assert client.post('/api/frames'+suffix,content=jpeg()).status_code==200


def test_input_validation_and_local_origin(client):
    client,runtime=client
    row=start(client)
    suffix=f"?owner={OWNER}&capture_id={row['capture_id']}"
    assert client.post('/api/frames'+suffix,content=b'not a jpeg').status_code==400
    assert client.post('/api/audio'+suffix,content=b'bad').status_code==400
    assert client.post('/api/audio'+suffix,content=np.array([np.nan],dtype='<f4').tobytes()).status_code==400
    assert client.post('/api/calibrate',json={'owner':OWNER},headers={'Origin':'https://example.com'}).status_code==403
    assert client.get('/api/sessions/nonexistent').status_code==404
    assert client.get('/api/alerts/unknown/image').status_code==404


def test_other_dashboard_can_stop_exact_session_but_cannot_capture(client):
    client,runtime=client
    first=start(client)
    foreign=f"?owner=another-browser&capture_id={first['capture_id']}"
    assert client.post('/api/frames'+foreign,content=jpeg()).status_code==409
    assert client.post('/api/audio'+foreign,content=np.zeros(1600,dtype='<f4').tobytes()).status_code==409
    # A second dashboard has no capture-owner token but can control this local session.
    response=client.post('/api/sessions/stop',json={'session_id':first['id']})
    assert response.status_code==200 and response.json()['ended_at']
    second=start(client)
    # Repeated/stale clicks cannot end the new session, even from the original owner.
    assert client.post('/api/sessions/stop',json={'session_id':first['id']}).status_code==200
    assert runtime.session['id']==second['id']
    assert client.post('/api/sessions/stop',json={'session_id':'unknown-id'}).status_code==409
    assert runtime.session['id']==second['id']
