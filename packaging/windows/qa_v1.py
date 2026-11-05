"""Exercise the portable backend via HTTP, using fixtures outside the release."""
import base64
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import time
import urllib.request
import urllib.error

ROOT=Path(__file__).resolve().parents[2]


def main():
    import cv2
    from faster_whisper.audio import decode_audio
    version=os.environ.get('EXAMWATCH_QA_VERSION','v1')
    assert version in {'v1','v2'}
    package=ROOT/'release'/version
    home=ROOT/'.tmp'/('portable-http-qa-'+str(time.time_ns()))
    token=secrets.token_hex(32);port=8123
    env=os.environ.copy()
    env.update(EXAMWATCH_HOME=str(home),PYTHONHOME='Z:/no-python',PYTHONPATH='Z:/no-packages',PYTHONIOENCODING='utf-8')
    home.mkdir(parents=True,exist_ok=True)
    def request(path,body=None,headers=None):
        data=None if body is None else (json.dumps(body).encode() if isinstance(body,dict) else body)
        h=headers or {}
        if isinstance(body,dict):h={**h,'Content-Type':'application/json'}
        req=urllib.request.Request(f'http://127.0.0.1:{port}'+path,data=data,headers=h)
        with urllib.request.urlopen(req,timeout=30) as res:
            raw=res.read()
            return json.loads(raw) if 'application/json' in res.headers.get('Content-Type','') else raw
    def start():
        log=(home/'backend.log').open('ab')
        child=subprocess.Popen([str(package/'runtime/python.exe'),str(package/'app/portable_server.py'),
                                '--port',str(port),'--token',token],env=env,cwd=package,stdout=log,stderr=log)
        log.close()
        for _ in range(120):
            if child.poll() is not None:raise RuntimeError('Portable backend exited; inspect backend.log')
            try:
                if request('/_launcher/health',headers={'X-ExamWatch-Launcher':token})['ready']:return child
            except (OSError,urllib.error.URLError):pass
            time.sleep(.5)
        child.terminate();raise TimeoutError('Startup timed out')
    child=start();checks=[]
    try:
        assert request('/').lower().startswith(b'<!doctype html>');checks.append('dashboard HTTP 200')
        assert request('/static/audio-worklet.js');checks.append('static audio worklet served')
        status=request('/api/status');assert all(status['models'].values())
        assert status['voice_model']=='zipformer-vi-30m';checks.append('all models preloaded')
        assert request('/api/students')==[] and request('/api/sessions')==[];checks.append('fresh database, no developer data')
        assert request('/api/settings/alerts',dict(standing_threshold_seconds=8))['standing_threshold_seconds']==8
        checks.append('customizable standing alert threshold')
        try:request('/_launcher/health')
        except urllib.error.HTTPError as error:assert error.code==403
        else:raise AssertionError('Launcher endpoint not protected')
        checks.append('launcher endpoints reject missing token')
        frame=cv2.imread(str(ROOT/'.tmp/fixtures/person1.jpg'))
        frame=cv2.resize(frame,(960,round(frame.shape[0]*960/frame.shape[1])))
        jpg=cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,85])[1].tobytes()
        image=base64.b64encode(jpg).decode()
        request('/api/students',dict(student_id='QA_ONLY',name='Portable QA',images=[image]*3))
        checks.append('face enrollment with real model')
        owner='portable-qa-owner-123456'
        session=request('/api/sessions',dict(title='Portable QA session',owner=owner))
        query=f'?owner={owner}&capture_id={session["capture_id"]}'
        result=request('/api/frames'+query,jpg)
        assert any(track['student_id']=='QA_ONLY' for track in result['tracks']);checks.append('frame face recognition, emotion and pose pipeline')
        assert len(result['tracks'][0]['mouth_points'])==3;checks.append('three mouth points from actual face detection')
        audio=decode_audio(str(ROOT/'.tmp/fixtures/vi-clean.wav'),sampling_rate=16000)
        assert len(audio)<=160000
        time.sleep(len(audio)/16000)  # Capture cannot finish before this much session time.
        request('/api/audio'+query+'&rate=16000&offset=0',audio.astype('<f4').tobytes())
        record=None
        for _ in range(40):
            record=request('/api/sessions/'+session['id'])
            if record['transcripts']:break
            time.sleep(.5)
        assert record['transcripts'];checks.append('PCM audio queue -> Zipformer -> saved transcript')
        exported=request('/api/sessions/'+session['id']+'/export')
        assert exported['transcripts'];checks.append('session JSON export')
        # Quit with a session still open; lifespan must persist its end timestamp.
        request('/_launcher/shutdown',b'',{'X-ExamWatch-Launcher':token})
        child.wait(40);assert child.returncode==0;checks.append('graceful shutdown with active session')
        child=start()
        record=request('/api/sessions/'+session['id'])
        assert record['session']['ended_at'] and record['transcripts'];checks.append('restart retains transcript and closed history')
        assert request('/api/status')['session'] is None
        assert request('/api/status')['standing_threshold_seconds']==8;checks.append('alert threshold persists across restart')
        request('/_launcher/shutdown',b'',{'X-ExamWatch-Launcher':token});child.wait(40)
        assert child.returncode==0
        report=dict(ok=True,checks=checks,transcript=record['transcripts'],home=str(home),
                    limits=['Same Windows host; not a clean second PC','HTTP fixture capture, not physical camera/microphone'])
        (ROOT/'.tmp'/f'portable-qa-report-{version}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(dict(ok=True,checks=checks),ensure_ascii=True))
    finally:
        if child.poll() is None:
            try:request('/_launcher/shutdown',b'',{'X-ExamWatch-Launcher':token});child.wait(40)
            except Exception:child.terminate()


if __name__=='__main__':main()
