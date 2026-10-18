from datetime import datetime, timedelta, timezone
import hashlib
import re
from uuid import uuid4

from examwatch.api.models import Room, Member, Device, Asset, Speech, Review, Event
from examwatch.api.security import DEMO_USER, digest
from examwatch.api.cleanup import cleanup


def post_event(api, event):
    response = api.post("/v1/events:batch", headers=api.device_headers, json={"items": [event]})
    assert response.status_code == 200, response.text


def test_auth_role_and_idempotency(api, event):
    assert api.get("/v1/rooms").status_code == 401
    assert api.post("/v1/events:batch", headers=api.user_headers, json={"items": [event]}).status_code == 403
    post_event(api, event)
    post_event(api, event)
    result = api.get(f"/v1/events?session_id={api.session_id}", headers=api.user_headers).json()
    assert len(result["items"]) == 1
    event["details"] = {"changed": True}
    assert api.post("/v1/events:batch", headers=api.device_headers, json={"items": [event]}).status_code == 409


def test_cross_room_and_revocation(api, event):
    room, other_device = str(uuid4()), str(uuid4())
    with api.app.state.factory() as db:
        db.add(Room(id=room, name="Other room"))
        db.flush()
        db.add(Device(id=other_device, room_id=room, name="Other", token_hash=digest("other-device")))
        db.commit()
    assert api.get(f"/v1/devices?room_id={room}", headers=api.user_headers).status_code == 403
    assert api.post("/v1/events:batch", headers={"Authorization": "Bearer other-device"}, json={"items": [event]}).status_code == 403
    assert api.delete(f"/v1/devices/{api.device_id}", headers=api.user_headers).status_code == 200
    assert api.post("/v1/devices/heartbeat", headers=api.device_headers, json={}).status_code == 401


def test_batch_atomicity_and_source_scope(api, event):
    bad = {**event, "id": str(uuid4()), "source_id": str(uuid4())}
    response = api.post("/v1/events:batch", headers=api.device_headers, json={"items": [event, bad]})
    assert response.status_code == 403
    assert api.get(f"/v1/events?session_id={api.session_id}", headers=api.user_headers).json()["items"] == []


def test_timestamps_track_and_source_validation(api, event):
    event["started_at"] = "2026-10-18T10:00:00"
    assert api.post("/v1/events:batch", headers=api.device_headers, json={"items": [event]}).status_code == 422
    event["started_at"] = api.timestamp
    event["track_id"] = str(uuid4())
    assert api.post("/v1/events:batch", headers=api.device_headers, json={"items": [event]}).status_code == 422
    event["track_id"] = None
    event["source_id"] = api.mic_id
    assert api.post("/v1/events:batch", headers=api.device_headers, json={"items": [event]}).status_code == 400


def test_upload_checksum_signed_url_and_review(api, event):
    post_event(api, event)
    content = b"test evidence bytes"
    asset = {"id": str(uuid4()), "session_id": api.session_id, "event_id": event["id"], "speech_id": None, "content_type": "image/jpeg", "size_bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
    info = api.post("/v1/assets/upload-url", headers=api.device_headers, json=asset).json()
    assert api.get(f"/v1/assets/{asset['id']}/view-url", headers=api.user_headers).status_code == 409
    assert api.put(info["url"], content=b"x" * len(content)).status_code == 409
    assert api.put(info["url"], content=content).status_code == 200
    assert api.post(f"/v1/assets/{asset['id']}/complete", headers=api.device_headers).status_code == 200
    view = api.get(f"/v1/assets/{asset['id']}/view-url", headers=api.user_headers).json()
    assert api.get(view["url"]).content == content
    assert api.get(re.sub(r"expires=\d+", "expires=1", view["url"])).status_code == 403
    assert api.put(view["url"], content=content).status_code == 403
    assert api.post(f"/v1/events/{event['id']}/reviews", headers=api.user_headers, json={"verdict": "dismissed", "note": "Đã xem, không có vi phạm"}).status_code == 200
    detail = api.get(f"/v1/events/{event['id']}", headers=api.user_headers).json()
    assert detail["review_status"] == "dismissed" and len(detail["reviews"]) == 1


def test_cross_session_evidence_rejected(api, event):
    post_event(api, event)
    session = str(uuid4())
    api.post("/v1/sessions", headers=api.device_headers, json={"id": session, "name": "Other", "started_at": api.timestamp})
    response = api.post("/v1/assets/upload-url", headers=api.device_headers, json={"id": str(uuid4()), "session_id": session, "event_id": event["id"], "content_type": "image/jpeg", "size_bytes": 3, "sha256": "0" * 64})
    assert response.status_code == 400


def test_speech_revision_immutable_raw_and_expiry(api):
    speech = {"id": str(uuid4()), "session_id": api.session_id, "source_id": api.mic_id, "event_id": None, "started_at": api.timestamp, "ended_at": api.timestamp, "model_version": "PhoWhisper-test", "processing_status": "DONE", "transcript_raw": "Xin chào"}
    assert api.post("/v1/speech-segments:batch", headers=api.device_headers, json={"items": [speech]}).status_code == 200
    assert api.patch(f"/v1/speech-segments/{speech['id']}/review", headers=api.user_headers, json={"verdict": "confirmed", "correction": "Xin chào các em", "note": "Đã nghe"}).status_code == 200
    row = api.get(f"/v1/speech-segments?session_id={api.session_id}", headers=api.user_headers).json()["items"][0]
    assert row["transcript_raw"] == "Xin chào" and row["transcript_corrected"] == "Xin chào các em"
    speech["transcript_raw"] = "Overwrite"
    assert api.post("/v1/speech-segments:batch", headers=api.device_headers, json={"items": [speech]}).status_code == 409
    with api.app.state.factory() as db:
        db.get(Speech, speech["id"]).expires_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        db.commit()
    result = api.get(f"/v1/speech-segments?session_id={api.session_id}", headers=api.user_headers).json()["items"][0]
    assert result["expired"] and result["transcript_raw"] is None
    cleanup(api.app.state.factory, api.app.state.storage)
    with api.app.state.factory() as db:
        assert db.get(Speech, speech["id"]).transcript_corrected is None
        review = db.query(Review).filter_by(speech_id=speech["id"]).one()
        assert review.correction is None and review.note == "[Nội dung đã hết hạn]"


def test_pagination_and_filters(api, event):
    for i in range(4):
        post_event(api, {**event, "id": str(uuid4()), "kind": "standing" if i % 2 else "side_lean"})
    response = api.get(f"/v1/events?session_id={api.session_id}&limit=2", headers=api.user_headers).json()
    assert len(response["items"]) == 2 and response["has_more"]
    response = api.get(f"/v1/events?session_id={api.session_id}&kind=standing", headers=api.user_headers).json()
    assert len(response["items"]) == 2


def test_cleanup_retries_failed_delete(api, event):
    post_event(api, event)
    with api.app.state.factory() as db:
        row = Asset(id=str(uuid4()), session_id=api.session_id, event_id=event["id"], object_path="test/path.jpg", content_type="image/jpeg", size_bytes=1, sha256="0" * 64, status="ready", expires_at="2000-01-01T00:00:00+00:00")
        identifier = row.id
        db.add(row)
        db.commit()
    class Failing:
        def delete(self, _):
            raise OSError("offline")
    assert cleanup(api.app.state.factory, Failing())["failed"] == 1
    with api.app.state.factory() as db:
        assert db.get(Asset, identifier).status == "ready"
    assert cleanup(api.app.state.factory, api.app.state.storage)["deleted"] == 1
    assert cleanup(api.app.state.factory, api.app.state.storage)["deleted"] == 0
