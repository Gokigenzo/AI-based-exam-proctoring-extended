import json
import wave
import pytest
from scripts.download_audio_dataset import safe_audio, valid_wav, prepare_manifests
from scripts.train_stt import normalize, read_rows
from scripts.train_stt import augment_audio
from scripts.prepare_tiny_dataset import quotas, clean_text

def test_source_split_and_duplicate_audio(tmp_path):
    rows = [dict(audio=f'audio/{i}.wav', text='xin chào', duration=1, source=f'video-{i // 3}')
            for i in range(150)]
    (tmp_path / 'train.json').write_text(json.dumps(rows[:100]), encoding='utf-8')
    (tmp_path / 'dev.json').write_text(json.dumps(rows[90:]), encoding='utf-8')
    unique, counts = prepare_manifests(tmp_path)
    assert len(unique) == sum(counts.values()) == 150
    sources = {}
    for name in counts:
        for line in (tmp_path / 'splits' / f'{name}.jsonl').read_text(encoding='utf-8').splitlines():
            source = json.loads(line)['source']
            assert source not in sources or sources[source] == name
            sources[source] = name

@pytest.mark.parametrize('path', ['audio/../../escape.wav', '/audio/absolute.wav', 'audio/C:/x.wav', 'audio/..\\x.wav'])
def test_audio_path_cannot_escape(tmp_path, path):
    with pytest.raises(ValueError):
        safe_audio(tmp_path, path)

def test_truncated_wav_is_not_resumed_as_complete(tmp_path):
    path = tmp_path / 'sample.wav'
    with wave.open(str(path), 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16000)
        out.writeframes(b'\0' * 32000)
    assert valid_wav(path)
    path.write_bytes(path.read_bytes()[:-100])
    assert not valid_wav(path)

def test_normalization_preserves_vietnamese_accents():
    assert normalize('  Thí SINH, đứng lên! ') == 'thí sinh đứng lên'

def test_training_requires_local_audio(tmp_path):
    (tmp_path / 'splits').mkdir()
    (tmp_path / 'splits/train.jsonl').write_text(json.dumps(
        dict(audio='audio/missing.wav', text='test', duration=1)) + '\n')
    with pytest.raises(FileNotFoundError):
        read_rows(tmp_path, 'train')

def test_small_dataset_quotas_keep_speaker_balance():
    assigned = quotas(['a','b','c'], 10)
    assert sum(assigned.values()) == 10
    assert max(assigned.values()) - min(assigned.values()) <= 1
    assert clean_text('  THÍ   SINH  ') == 'thí sinh'

def test_audio_augmentation_is_reproducible_and_preserves_length():
    import numpy as np
    original = np.full(16000, .1, dtype=np.float32)
    before = original.copy()
    a = augment_audio(original, np.random.default_rng(4))
    b = augment_audio(original, np.random.default_rng(4))
    assert np.array_equal(a, b)
    assert np.array_equal(original, before)
    assert len(a) == len(original)
    assert np.isfinite(a).all() and np.max(np.abs(a)) <= 1
