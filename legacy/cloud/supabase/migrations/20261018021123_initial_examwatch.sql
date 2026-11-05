
CREATE TABLE rooms (
	id VARCHAR(36) NOT NULL,
	name VARCHAR(160) NOT NULL,
	PRIMARY KEY (id)
)

;

CREATE TABLE devices (
	id VARCHAR(36) NOT NULL,
	room_id VARCHAR(36) NOT NULL,
	name VARCHAR(160) NOT NULL,
	token_hash VARCHAR(64) NOT NULL,
	revoked BOOLEAN NOT NULL,
	last_seen VARCHAR(40),
	status JSON NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(room_id) REFERENCES rooms (id),
	UNIQUE (token_hash)
)

;

CREATE TABLE room_members (
	room_id VARCHAR(36) NOT NULL,
	user_id VARCHAR(36) NOT NULL,
	role VARCHAR(16) NOT NULL,
	PRIMARY KEY (room_id, user_id),
	FOREIGN KEY(room_id) REFERENCES rooms (id)
)

;

CREATE TABLE exam_sessions (
	id VARCHAR(36) NOT NULL,
	room_id VARCHAR(36) NOT NULL,
	device_id VARCHAR(36) NOT NULL,
	name VARCHAR(160) NOT NULL,
	started_at VARCHAR(40) NOT NULL,
	ended_at VARCHAR(40),
	config JSON NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(room_id) REFERENCES rooms (id),
	FOREIGN KEY(device_id) REFERENCES devices (id)
)

;

CREATE TABLE sources (
	id VARCHAR(36) NOT NULL,
	device_id VARCHAR(36) NOT NULL,
	kind VARCHAR(16) NOT NULL,
	name VARCHAR(160) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(device_id) REFERENCES devices (id)
)

;

CREATE TABLE tracks (
	id VARCHAR(36) NOT NULL,
	session_id VARCHAR(36) NOT NULL,
	source_id VARCHAR(36) NOT NULL,
	local_id INTEGER NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (session_id, source_id, local_id),
	FOREIGN KEY(session_id) REFERENCES exam_sessions (id),
	FOREIGN KEY(source_id) REFERENCES sources (id)
)

;

CREATE TABLE events (
	id VARCHAR(36) NOT NULL,
	session_id VARCHAR(36) NOT NULL,
	source_id VARCHAR(36) NOT NULL,
	track_id VARCHAR(36),
	kind VARCHAR(40) NOT NULL,
	started_at VARCHAR(40) NOT NULL,
	ended_at VARCHAR(40) NOT NULL,
	model_version VARCHAR(200) NOT NULL,
	model_confidence FLOAT,
	rule_score FLOAT,
	details JSON NOT NULL,
	review_status VARCHAR(24) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(session_id) REFERENCES exam_sessions (id),
	FOREIGN KEY(source_id) REFERENCES sources (id),
	FOREIGN KEY(track_id) REFERENCES tracks (id)
)

;

CREATE TABLE speech_segments (
	id VARCHAR(36) NOT NULL,
	session_id VARCHAR(36) NOT NULL,
	source_id VARCHAR(36) NOT NULL,
	event_id VARCHAR(36),
	started_at VARCHAR(40) NOT NULL,
	ended_at VARCHAR(40) NOT NULL,
	transcript_raw TEXT,
	transcript_corrected TEXT,
	model_version VARCHAR(200) NOT NULL,
	processing_status VARCHAR(16) NOT NULL,
	expires_at VARCHAR(40) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(session_id) REFERENCES exam_sessions (id),
	FOREIGN KEY(source_id) REFERENCES sources (id),
	FOREIGN KEY(event_id) REFERENCES events (id)
)

;

CREATE TABLE evidence_assets (
	id VARCHAR(36) NOT NULL,
	session_id VARCHAR(36) NOT NULL,
	event_id VARCHAR(36),
	speech_id VARCHAR(36),
	object_path VARCHAR(300) NOT NULL,
	content_type VARCHAR(80) NOT NULL,
	size_bytes INTEGER NOT NULL,
	sha256 VARCHAR(64) NOT NULL,
	status VARCHAR(16) NOT NULL,
	expires_at VARCHAR(40) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(session_id) REFERENCES exam_sessions (id),
	FOREIGN KEY(event_id) REFERENCES events (id),
	FOREIGN KEY(speech_id) REFERENCES speech_segments (id),
	UNIQUE (object_path)
)

;

CREATE TABLE reviews (
	id VARCHAR(36) NOT NULL,
	event_id VARCHAR(36),
	speech_id VARCHAR(36),
	user_id VARCHAR(36) NOT NULL,
	verdict VARCHAR(32) NOT NULL,
	note TEXT NOT NULL,
	correction TEXT,
	created_at VARCHAR(40) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(event_id) REFERENCES events (id),
	FOREIGN KEY(speech_id) REFERENCES speech_segments (id)
)

;
CREATE INDEX ix_devices_room_id ON devices (room_id);
CREATE INDEX ix_exam_sessions_room_id ON exam_sessions (room_id);
CREATE INDEX ix_sources_device_id ON sources (device_id);
CREATE INDEX ix_tracks_session_id ON tracks (session_id);
CREATE INDEX events_session_time ON events (session_id, started_at);
CREATE INDEX speech_session_time ON speech_segments (session_id, started_at);
CREATE INDEX ix_evidence_assets_expires_at ON evidence_assets (expires_at);
-- Applied after the generated initial schema. All cloud writes go through the API.
ALTER TABLE room_members ADD CONSTRAINT member_role CHECK (role IN ('admin','reviewer'));
ALTER TABLE sources ADD CONSTRAINT source_kind CHECK (kind IN ('camera','microphone'));
ALTER TABLE events ADD CONSTRAINT event_kind CHECK (kind IN ('expression_observation','speech_detected','rising','standing','side_lean','turned'));
ALTER TABLE events ADD CONSTRAINT event_time CHECK (ended_at >= started_at);
ALTER TABLE events ADD CONSTRAINT event_confidence CHECK (model_confidence IS NULL OR model_confidence BETWEEN 0 AND 1);
ALTER TABLE events ADD CONSTRAINT event_rule_score CHECK (rule_score IS NULL OR rule_score BETWEEN 0 AND 1);
ALTER TABLE events ADD CONSTRAINT event_review CHECK (review_status IN ('pending','confirmed','dismissed','needs_review'));
ALTER TABLE speech_segments ADD CONSTRAINT speech_status CHECK (processing_status IN ('QUEUED','PROCESSING','DONE','FAILED'));
ALTER TABLE speech_segments ADD CONSTRAINT speech_time CHECK (ended_at >= started_at);
ALTER TABLE evidence_assets ADD CONSTRAINT asset_status CHECK (status IN ('pending','ready','expired'));
ALTER TABLE evidence_assets ADD CONSTRAINT asset_size CHECK (size_bytes > 0 AND size_bytes <= 52428800);
ALTER TABLE evidence_assets ADD CONSTRAINT asset_parent CHECK (event_id IS NOT NULL OR speech_id IS NOT NULL);
ALTER TABLE reviews ADD CONSTRAINT review_parent CHECK ((event_id IS NULL) <> (speech_id IS NULL));
ALTER TABLE reviews ADD CONSTRAINT review_verdict CHECK (verdict IN ('confirmed','dismissed','needs_review'));

ALTER TABLE rooms ENABLE ROW LEVEL SECURITY;
ALTER TABLE room_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE exam_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE tracks ENABLE ROW LEVEL SECURITY;
ALTER TABLE events ENABLE ROW LEVEL SECURITY;
ALTER TABLE speech_segments ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE reviews ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON rooms,room_members,devices,sources,exam_sessions,tracks,events,speech_segments,evidence_assets,reviews FROM anon,authenticated;
GRANT SELECT ON rooms,room_members,sources,exam_sessions,tracks,events,evidence_assets TO authenticated;
-- Speech and reviews are API-only to enforce expiry before the cleanup job runs.
GRANT SELECT(id,room_id,name,revoked,last_seen,status) ON devices TO authenticated;

CREATE POLICY own_membership ON room_members FOR SELECT TO authenticated USING (user_id = (SELECT auth.uid())::text);
CREATE POLICY member_room ON rooms FOR SELECT TO authenticated USING (EXISTS (SELECT 1 FROM room_members m WHERE m.room_id=rooms.id AND m.user_id=(SELECT auth.uid())::text));
CREATE POLICY member_device ON devices FOR SELECT TO authenticated USING (EXISTS (SELECT 1 FROM room_members m WHERE m.room_id=devices.room_id AND m.user_id=(SELECT auth.uid())::text));
CREATE POLICY member_source ON sources FOR SELECT TO authenticated USING (EXISTS (SELECT 1 FROM devices d JOIN room_members m ON m.room_id=d.room_id WHERE d.id=sources.device_id AND m.user_id=(SELECT auth.uid())::text));
CREATE POLICY member_session ON exam_sessions FOR SELECT TO authenticated USING (EXISTS (SELECT 1 FROM room_members m WHERE m.room_id=exam_sessions.room_id AND m.user_id=(SELECT auth.uid())::text));
CREATE POLICY member_track ON tracks FOR SELECT TO authenticated USING (EXISTS (SELECT 1 FROM exam_sessions s JOIN room_members m ON m.room_id=s.room_id WHERE s.id=tracks.session_id AND m.user_id=(SELECT auth.uid())::text));
CREATE POLICY member_event ON events FOR SELECT TO authenticated USING (EXISTS (SELECT 1 FROM exam_sessions s JOIN room_members m ON m.room_id=s.room_id WHERE s.id=events.session_id AND m.user_id=(SELECT auth.uid())::text));
CREATE POLICY member_asset ON evidence_assets FOR SELECT TO authenticated USING (EXISTS (SELECT 1 FROM exam_sessions s JOIN room_members m ON m.room_id=s.room_id WHERE s.id=evidence_assets.session_id AND m.user_id=(SELECT auth.uid())::text));

INSERT INTO storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
VALUES ('evidence','evidence',false,52428800,ARRAY['image/jpeg','audio/wav','video/mp4'])
ON CONFLICT(id) DO UPDATE SET public=false,file_size_limit=excluded.file_size_limit,allowed_mime_types=excluded.allowed_mime_types;
-- No client storage policy: the backend validates membership and expiry before signing URLs.

COMMENT ON TABLE events IS 'Machine observations only; human reviews are stored separately.';
