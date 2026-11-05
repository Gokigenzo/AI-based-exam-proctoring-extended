"""Local experimental RNNT LoRA on the released Zipformer joiner; encoder/decoder frozen."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import random
import re
import time
import unicodedata

import numpy as np
import soundfile as sf
import torch
from torch import nn
from torch.nn import functional as F
import torchaudio
import kaldi_native_fbank as knf
import sentencepiece as spm
from jiwer import wer, cer
from zipformer_schedule import learning_rate, update_early_stopping

ROOT = Path(__file__).resolve().parent.parent


class LowRankLinear(nn.Module):
    def __init__(self, weight, bias, rank=8, dropout=0.):
        super().__init__()
        self.weight = nn.Parameter(weight.clone(), requires_grad=False)
        self.bias = nn.Parameter(bias.clone(), requires_grad=False)
        self.a = nn.Parameter(torch.empty(rank, weight.shape[1]))
        self.b = nn.Parameter(torch.zeros(weight.shape[0], rank))
        nn.init.kaiming_uniform_(self.a, a=5**.5)
        self.scale = 2.
        self.dropout = nn.Dropout(dropout)

    def forward(self, x):
        return F.linear(x, self.weight, self.bias) + F.linear(F.linear(self.dropout(x),self.a),self.b)*self.scale


class Joiner(nn.Module):
    def __init__(self, state, dropout=0.):
        super().__init__()
        for name in ['encoder_proj','decoder_proj','output_linear']:
            setattr(self,name,LowRankLinear(state[name+'.weight'],state[name+'.bias'],dropout=dropout))

    def forward(self, encoder, decoder):
        return self.output_linear(torch.tanh(self.encoder_proj(encoder)+self.decoder_proj(decoder)))


def fbank(audio):
    opts=knf.FbankOptions()
    opts.frame_opts.dither=0
    opts.frame_opts.snip_edges=False
    opts.frame_opts.samp_freq=16000
    opts.mel_opts.num_bins=80
    opts.mel_opts.low_freq=20
    opts.mel_opts.high_freq=-400
    fb=knf.OnlineFbank(opts)
    # Sherpa's normalize_samples=True consumes float samples in [-1, 1].
    fb.accept_waveform(16000,audio.tolist())
    fb.input_finished()
    return torch.tensor(np.stack([fb.get_frame(i) for i in range(fb.num_frames_ready)]))


def normalize(text):
    return ' '.join(re.findall(r'\w+',unicodedata.normalize('NFC',text).casefold()))


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--dataset',type=Path,default=ROOT/'Audio-dataset/vivos-small')
    parser.add_argument('--checkpoint',type=Path,default=ROOT/'.tmp/zipformer-training-probe/jit_script.pt')
    parser.add_argument('--output',type=Path,default=ROOT/'training-runs/zipformer-vivos-lora')
    parser.add_argument('--epochs',type=int,default=3)
    parser.add_argument('--max-batch',type=int,default=32)
    parser.add_argument('--learning-rate',type=float,default=1e-4)
    parser.add_argument('--min-learning-rate',type=float,default=1e-6)
    parser.add_argument('--warmup-ratio',type=float,default=.05)
    parser.add_argument('--patience',type=int,default=10)
    parser.add_argument('--early-stopping-start-epoch',type=int,default=1)
    parser.add_argument('--lora-dropout',type=float,default=0.)
    parser.add_argument('--min-delta',type=float,default=.01,help='WER percentage points')
    parser.add_argument('--feature-cache',type=Path)
    parser.add_argument('--smoke',action='store_true')
    args=parser.parse_args()
    if args.epochs<1 or not 0<=args.warmup_ratio<1 or args.patience<0 or args.min_delta<0:
        parser.error('Invalid epochs/warmup/patience/min-delta')
    if args.early_stopping_start_epoch<1 or not 0<=args.lora_dropout<1:
        parser.error('Invalid early stopping start epoch/dropout')
    if not 0<=args.min_learning_rate<=args.learning_rate or args.learning_rate<=0:
        parser.error('Invalid learning rates')
    if (args.output/'run.json').exists() or (args.output/'comparison.json').exists(): raise FileExistsError(args.output)
    args.output.mkdir(parents=True,exist_ok=True)
    torch.manual_seed(42); random.seed(42); np.random.seed(42); torch.set_num_threads(2)
    if not torch.cuda.is_available():raise RuntimeError('CUDA is required')
    device='cuda'
    scripted=torch.jit.load(str(args.checkpoint),map_location=device).eval()
    for p in scripted.parameters():p.requires_grad_(False)
    joiner=Joiner(scripted.joiner.state_dict(),dropout=args.lora_dropout).to(device)
    sp=spm.SentencePieceProcessor(model_file=str(ROOT/'models/zipformer-vi-30m/bpe.model'))
    assert sp.get_piece_size()==2000 and sp.piece_to_id('<blk>')==0
    # Verify recovered joiner including gradients through zero-initialized LoRA.
    with torch.no_grad():
        x=torch.randn(2,4,1,256,device=device);y=torch.randn(2,1,5,512,device=device)
        ref=scripted.joiner(x,y)
        error=float((ref-joiner(x,y)).abs().max())
        assert error<1e-5, error
    print('Joiner parity max error:',error,flush=True)
    rows={s:[json.loads(x) for x in (args.dataset/'splits'/f'{s}.jsonl').read_text(encoding='utf-8').splitlines()] for s in ['train','validation','test']}
    if args.smoke:rows={s:v[:4] for s,v in rows.items()}
    assert not ({r['source'] for r in rows['train']} & {r['source'] for r in rows['validation']})
    cache_path=args.feature_cache or args.output/'frozen-features.pt'
    if cache_path.exists():
        if args.feature_cache:
            provenance=json.loads((cache_path.parent/'run.json').read_text(encoding='utf-8'))
            if provenance['checkpoint_sha256']!=hashlib.sha256(args.checkpoint.read_bytes()).hexdigest():
                raise ValueError('Feature cache model mismatch')
        cached=torch.load(cache_path,weights_only=True)
        for split in rows:
            if [(r['audio'],r['text']) for r in rows[split]] != [(r['audio'],r['text']) for r in cached[split]]:
                raise ValueError('Feature cache dataset mismatch')
    else:
        cached={}
        for split,items in rows.items():
            cached[split]=[]
            for i,row in enumerate(items):
                audio,rate=sf.read(args.dataset/row['audio'],dtype='float32')
                assert rate==16000 and audio.ndim==1
                feats=fbank(audio).to(device)
                ids=sp.encode(unicodedata.normalize('NFC',row['text']).upper(),out_type=int)
                assert ids and 2 not in ids, 'Unknown BPE token'
                with torch.no_grad():
                    enc,length=scripted.encoder(feats[None],torch.tensor([len(feats)],device=device))
                    target=torch.tensor([0]+ids,device=device)[None]
                    dec=scripted.decoder(target,True)
                cached[split].append(dict(encoder=enc[0,:int(length[0])].cpu(),decoder=dec[0].cpu(),
                    ids=torch.tensor(ids,dtype=torch.int32),text=row['text'],audio=row['audio']))
                if (i+1)%100==0:print('Cached',split,i+1,'/',len(items),flush=True)
        torch.save(cached,cache_path)

    def batch(items):
        n=len(items);t=max(len(r['encoder']) for r in items);u=max(len(r['ids']) for r in items)
        enc=torch.zeros(n,t,256,device=device);dec=torch.zeros(n,u+1,512,device=device)
        targets=torch.zeros(n,u,dtype=torch.int32,device=device)
        for i,r in enumerate(items):
            enc[i,:len(r['encoder'])]=r['encoder'].to(device)
            dec[i,:len(r['decoder'])]=r['decoder'].to(device)
            targets[i,:len(r['ids'])]=r['ids'].to(device)
        return enc,dec,targets,torch.tensor([len(r['encoder']) for r in items],dtype=torch.int32,device=device),torch.tensor([len(r['ids']) for r in items],dtype=torch.int32,device=device)

    def loss(items):
        enc,dec,targets,tl,ul=batch(items)
        logits=joiner(enc[:,:,None,:],dec[:,None,:,:]).contiguous()
        return torchaudio.functional.rnnt_loss(logits,targets,tl,ul,blank=0,reduction='mean',fused_log_softmax=True)

    # Worst padded shape, not a conveniently short first batch. Keep headroom.
    longest_audio=max(cached['train'],key=lambda r:len(r['encoder']))
    longest_text=max(cached['train'],key=lambda r:len(r['ids']))
    worst=dict(encoder=longest_audio['encoder'],decoder=longest_text['decoder'],ids=longest_text['ids'])
    probes=[];selected=1
    optimizer=torch.optim.AdamW([p for p in joiner.parameters() if p.requires_grad],lr=args.learning_rate,weight_decay=.01)
    initial=copy.deepcopy(joiner.state_dict())
    for size in [1,2,4,8,16,32,64]:
        if size>args.max_batch:break
        optimizer.zero_grad(set_to_none=True);torch.cuda.empty_cache();torch.cuda.reset_peak_memory_stats()
        try:
            value=loss([worst]*size);value.backward();torch.cuda.synchronize()
            peak=torch.cuda.max_memory_allocated()
            free,total=torch.cuda.mem_get_info()
            probes.append(dict(batch=size,peak_mib=peak/2**20,loss=float(value.detach())))
            print('VRAM probe',probes[-1],flush=True)
            del value
            if peak<total*.7:selected=size
            else:break
        except torch.OutOfMemoryError:
            probes.append(dict(batch=size,oom=True));break
    joiner.load_state_dict(initial);optimizer.zero_grad(set_to_none=True);torch.cuda.empty_cache()

    @torch.no_grad()
    def evaluate(items):
        was_training=joiner.training
        joiner.eval()
        hypotheses=[];elapsed=time.perf_counter()
        # Greedy RNNT, at most one symbol per encoder frame, as deployed.
        for row in items:
            history=[-1,0];out=[]
            d=scripted.decoder(torch.tensor([history],device=device),False)[0,0]
            enc=joiner.encoder_proj(row['encoder'].to(device))
            for frame in enc:
                logits=joiner.output_linear(torch.tanh(frame+joiner.decoder_proj(d)))
                token=int(logits.argmax())
                if token:
                    out.append(token);history=(history+[token])[-2:]
                    d=scripted.decoder(torch.tensor([history],device=device),False)[0,0]
            hypotheses.append(sp.decode(out))
        refs=[normalize(r['text']) for r in items];hyps=[normalize(h) for h in hypotheses]
        joiner.train(was_training)
        return dict(wer=100*wer(refs,hyps),cer=100*cer(refs,hyps),seconds=time.perf_counter()-elapsed,
                    predictions=[dict(audio=r['audio'],reference=r['text'],prediction=h) for r,h in zip(items,hypotheses)])

    total_steps=math.ceil(len(cached['train'])/selected)*args.epochs
    warmup_steps=min(total_steps-1,math.ceil(total_steps*args.warmup_ratio))
    run=dict(model='hynt/Zipformer-30M-RNNT-6000h',checkpoint_sha256=hashlib.sha256(args.checkpoint.read_bytes()).hexdigest(),
        scope='joiner encoder_proj, decoder_proj, output_linear only; encoder and prediction decoder frozen',
        rank=8,alpha=16,batch_size=selected,batch_probes=probes,epochs=args.epochs,learning_rate=args.learning_rate,
        scheduler='linear_warmup_cosine',min_learning_rate=args.min_learning_rate,warmup_steps=warmup_steps,
        total_steps=total_steps,patience=args.patience,min_delta_wer_points=args.min_delta,
        early_stopping_start_epoch=args.early_stopping_start_epoch,lora_dropout=args.lora_dropout,
        optimizer='AdamW',weight_decay=.01,
        feature_cache=str(cache_path),initialization='original model with zero LoRA update',
        trainable_parameters=sum(p.numel() for p in joiner.parameters() if p.requires_grad),
        counts={s:len(v) for s,v in cached.items()},parity_max_error=error,gpu=torch.cuda.get_device_name(),
        dataset=str(args.dataset),note='VIVOS held out from this adaptation only; upstream training overlap unknown. Not a room-domain benchmark.')
    (args.output/'run.json').write_text(json.dumps(run,indent=2),encoding='utf-8')
    base=evaluate(cached['validation']);print('Baseline validation WER',base['wer'],flush=True)
    if base['wer']>50:raise RuntimeError('Baseline sanity check failed; inspect preprocessing before training')
    (args.output/'baseline.json').write_text(json.dumps(base,ensure_ascii=False,indent=2),encoding='utf-8')
    best=base['wer'];best_state=copy.deepcopy(initial);best_epoch=0;history=[];started=time.perf_counter()
    early_best=best;stale=0;step=0;stopped_early=False
    for epoch in range(args.epochs):
        joiner.train()
        order=list(cached['train']);random.shuffle(order)
        # Sort short random buckets to reduce padding, preserving stochastic order.
        order=[r for i in range(0,len(order),selected*8) for r in sorted(order[i:i+selected*8],key=lambda r:len(r['encoder']))]
        losses=[]
        for i in range(0,len(order),selected):
            lr=learning_rate(step,total_steps,warmup_steps,args.learning_rate,args.min_learning_rate)
            for group in optimizer.param_groups:group['lr']=lr
            optimizer.zero_grad(set_to_none=True)
            value=loss(order[i:i+selected]);assert torch.isfinite(value)
            value.backward()
            grads=[p.grad for p in joiner.parameters() if p.requires_grad and p.grad is not None]
            assert grads and all(torch.isfinite(g).all() for g in grads)
            assert any(torch.count_nonzero(g)>0 for g in grads), 'No adaptation gradient'
            torch.nn.utils.clip_grad_norm_([p for p in joiner.parameters() if p.requires_grad],5.)
            optimizer.step();step+=1;losses.append(float(value.detach()))
            if (i//selected)%20==0:print('Epoch',epoch+1,'batch',i//selected,'loss',losses[-1],flush=True)
        val=evaluate(cached['validation'])
        history.append(dict(epoch=epoch+1,train_loss=float(np.mean(losses)),validation_wer=val['wer'],learning_rate=lr,global_step=step))
        print('Epoch result',history[-1],flush=True)
        torch.save({k:v.cpu() for k,v in joiner.state_dict().items()},args.output/'last-joiner.pt')
        if val['wer']<best:
            best=val['wer'];best_epoch=epoch+1;best_state=copy.deepcopy(joiner.state_dict())
        torch.save({k:v.cpu() for k,v in best_state.items()},args.output/'best-joiner.pt')
        early_best,stale=update_early_stopping(epoch+1,args.early_stopping_start_epoch,
                                             val['wer'],early_best,stale,args.min_delta)
        torch.save(dict(joiner=joiner.state_dict(),optimizer=optimizer.state_dict(),global_step=step,
                        epoch=epoch+1,best_wer=best,best_epoch=best_epoch,stale_epochs=stale,
                        python_rng=random.getstate(),torch_rng=torch.get_rng_state(),
                        cuda_rng=torch.cuda.get_rng_state_all()),args.output/'last-training-state.pt')
        (args.output/'progress.json').write_text(json.dumps(dict(history=history,best_epoch=best_epoch,
            best_wer=best,stale_epochs=stale,global_step=step),indent=2),encoding='utf-8')
        if args.patience and stale>=args.patience:
            stopped_early=True
            print('Early stopping at epoch',epoch+1,'stale epochs',stale,flush=True)
            break
    runtime=time.perf_counter()-started
    joiner.load_state_dict(initial);test_base=evaluate(cached['test'])
    joiner.load_state_dict(best_state);test_best=evaluate(cached['test'])
    # Keep last adaptation too, even when baseline is best.
    report=dict(baseline_validation=base['wer'],best_validation=best,best_epoch=best_epoch,
        history=history,training_seconds=runtime,baseline_test=test_base,best_test=test_best,
        selected_baseline=best_epoch==0,completed_epochs=len(history),stopped_early=stopped_early)
    (args.output/'comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    torch.save({k:v.cpu() for k,v in joiner.state_dict().items() if k.endswith(('.a','.b'))},args.output/'adapter.pt')
    print('Completed:',args.output,'best epoch',best_epoch,'test WER',test_best['wer'],flush=True)


if __name__=='__main__':main()
