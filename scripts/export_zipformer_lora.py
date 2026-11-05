"""Merge best joiner LoRA into original ONNX graphs without overwriting the base."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import numpy as np
import onnx
from onnx import numpy_helper
import torch
from onnxruntime.quantization import quantize_dynamic, QuantType

ROOT=Path(__file__).resolve().parent.parent


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--run',type=Path,default=ROOT/'training-runs/zipformer-vivos-lora-cosine100-dropout')
    p.add_argument('--output',type=Path,default=ROOT/'models/zipformer-vi-30m-lora')
    args=p.parse_args()
    if args.output.exists():raise FileExistsError(args.output)
    state=torch.load(args.run/'best-joiner.pt',map_location='cpu',weights_only=True)
    report=json.loads((args.run/'comparison.json').read_text(encoding='utf-8'))
    args.output.mkdir(parents=True)
    scripted=torch.jit.load(str(ROOT/'.tmp/zipformer-training-probe/jit_script.pt'),map_location='cpu')
    original=scripted.joiner.state_dict()
    for kind,name in [('encoder','encoder_proj'),('decoder','decoder_proj'),('joiner','output_linear')]:
        graph=onnx.load(str(ROOT/'.tmp/zipformer-training-probe/onnx-fp32'/f'{kind}-epoch-20-avg-10.onnx'))
        merged=(state[name+'.weight']+2*state[name+'.b']@state[name+'.a']).numpy()
        base=original[name+'.weight'].numpy()
        # Encoder projection is the final folded/transposed MatMul initializer.
        candidates=[]
        for init in graph.graph.initializer:
            arr=numpy_helper.to_array(init)
            if arr.shape==base.shape and np.array_equal(arr,base): candidates.append((init,False))
            elif arr.shape==base.T.shape and np.array_equal(arr,base.T): candidates.append((init,True))
        if len(candidates)!=1:raise ValueError(f'{kind}: projection not uniquely matched: {len(candidates)}')
        init,transpose=candidates[0]
        init.CopyFrom(numpy_helper.from_array(merged.T.copy() if transpose else merged.copy(),init.name))
        bias=next(x for x in graph.graph.initializer if x.name==name+'.bias')
        assert np.array_equal(numpy_helper.to_array(bias),state[name+'.bias'].numpy())
        onnx.checker.check_model(graph)
        fp=args.output/f'{kind}.onnx'
        onnx.save(graph,str(fp))
        if kind!='decoder':
            quantize_dynamic(str(fp),str(args.output/f'{kind}.int8.onnx'),op_types_to_quantize=['MatMul'],weight_type=QuantType.QInt8)
        print('Exported',kind,flush=True)
    for name in ['tokens.txt','bpe.model']:
        shutil.copy2(ROOT/'models/zipformer-vi-30m'/name,args.output/name)
    manifest=dict(source_run=str(args.run),checkpoint='best-joiner.pt',best_epoch=report['best_epoch'],
        license='CC-BY-NC-ND-4.0',lora_merged=True,rank=8,alpha=16,
        files={x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in args.output.iterdir() if x.is_file()})
    (args.output/'source.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')


if __name__=='__main__':main()
