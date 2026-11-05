"""Diagnostic comparison on a supplied public fixture; not an accuracy benchmark."""
from pathlib import Path
import json
import re
import sys
import time
import unicodedata

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from examwatch.config import Settings
from examwatch.speech import Speech
from faster_whisper import WhisperModel
from faster_whisper.audio import decode_audio


def wer(reference,hypothesis):
    def tokens(text):
        return re.findall(r"\w+",unicodedata.normalize('NFC',text.casefold()))
    reference,hypothesis=tokens(reference),tokens(hypothesis)
    row=list(range(len(hypothesis)+1))
    for i,a in enumerate(reference,1):
        new=[i]
        for j,b in enumerate(hypothesis,1):
            new.append(min(new[-1]+1,row[j]+1,row[j-1]+(a!=b)))
        row=new
    return row[-1]/max(1,len(reference))


def main():
    samples=decode_audio(str(ROOT/'.tmp/fixtures/vietnamese.wav'))[:7*16000]
    metadata=json.loads((ROOT/'.tmp/fixtures/vietnamese.json').read_text(encoding='utf-8'))
    reference=metadata['reference']
    tiny_path=ROOT/'models/whisper-tiny'
    base_path=ROOT/'models/whisper-base'
    if not tiny_path.is_dir(): tiny_path=ROOT/'backups/previous-voice-models/whisper-tiny'
    if not base_path.is_dir(): base_path=ROOT/'backups/previous-voice-models/whisper-base'
    tiny=WhisperModel(str(tiny_path),device='cpu',compute_type='int8',cpu_threads=2,local_files_only=True)
    begin=time.perf_counter()
    rows,_=tiny.transcribe(samples,language='vi',beam_size=1,best_of=1,temperature=0,
        condition_on_previous_text=False,vad_filter=True,
        vad_parameters={'min_silence_duration_ms':400,'speech_pad_ms':200})
    old=' '.join(s.text.strip() for s in rows)
    old_seconds=time.perf_counter()-begin
    base=Speech(Settings(models=base_path.parent,whisper_name='base'))
    begin=time.perf_counter()
    output=base.transcribe(samples,16000)
    new=' '.join(s['text'] for s in output)
    report={'fixture':metadata,'audio_seconds':7,
        'tiny_before':{'text':old,'wer':round(wer(reference,old),3),'seconds':round(old_seconds,2)},
        'base_after':{'text':new,'wer':round(wer(reference,new),3),'seconds':round(time.perf_counter()-begin,2),
                      'warning':base.last_warning}}
    if (ROOT/'models/whisper-phowhisper-base/model.bin').is_file():
        pho=Speech(Settings(whisper_name='phowhisper-base'))
        begin=time.perf_counter()
        pho_text=' '.join(s['text'] for s in pho.transcribe(samples,16000))
        report['phowhisper_int8']={'text':pho_text,'wer':round(wer(reference,pho_text),3),
                                 'seconds':round(time.perf_counter()-begin,2),'warning':pho.last_warning}
    (ROOT/'.tmp/vi-asr-comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True,indent=2))


if __name__=='__main__':
    main()
