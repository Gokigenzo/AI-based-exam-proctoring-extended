from types import SimpleNamespace
import numpy as np
import pytest
from examwatch.speech import Speech, unreliable_segment


def segment(text="Các em tập trung làm bài nhé.",**kwargs):
    return SimpleNamespace(text=text,start=0,end=2,no_speech_prob=.05,avg_logprob=-.3,
                           compression_ratio=kwargs.pop('compression_ratio',1.2),**kwargs)


@pytest.mark.parametrize('text',[
    'hồi '*30,
    'Hãy bỏ lỡ những video dưới '*12,
])
def test_repetition_loops_from_reported_failure_are_rejected(text):
    assert unreliable_segment(segment(text))


def test_real_repeated_short_words_not_censored():
    assert not unreliable_segment(segment('Có, có. Các em bắt đầu làm bài.'))


def test_speech_uses_quality_decode_and_never_stores_uncertain_segments():
    class Model:
        def transcribe(self,samples,**kwargs):
            assert kwargs['language']=='vi' and kwargs['beam_size']==5
            assert kwargs['condition_on_previous_text'] is False
            assert kwargs['without_timestamps'] is True
            assert kwargs['vad_filter'] and kwargs['no_repeat_ngram_size']==3
            low=segment();low.avg_logprob=-1.5
            return iter([segment(),low,segment('hồi '*30)]),None
    speech=Speech.__new__(Speech);speech.model=Model()
    output=speech.transcribe(np.full(16000,.02,dtype=np.float32),16000)
    assert [r['text'] for r in output]==['Các em tập trung làm bài nhé.']
    assert speech.last_warning


def test_silence_never_calls_the_decoder():
    speech=Speech.__new__(Speech)
    assert speech.transcribe(np.zeros(16000,dtype=np.float32),16000)==[]


def test_zipformer_uses_fresh_stream_and_chunk_duration():
    class Stream:
        result=SimpleNamespace(text=' CÂU HAI   Ý B ')
        def accept_waveform(self, rate, samples):
            assert rate == 16000 and len(samples) == 16000
    class Model:
        def __init__(self): self.streams=[]
        def create_stream(self):
            stream=Stream(); self.streams.append(stream); return stream
        def decode_stream(self, stream): assert stream is self.streams[-1]
    speech=Speech.__new__(Speech); speech.zipformer=True; speech.model=Model()
    for _ in range(2):
        assert speech.transcribe(np.full(16000,.02,dtype=np.float32),16000)==[
            {'start':0.,'end':1.,'text':'CÂU HAI Ý B'}]
    assert speech.model.streams[0] is not speech.model.streams[1]
