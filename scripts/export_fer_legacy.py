"""Executed ONLY with the pinned MXNet environment, not the capture runtime."""
import argparse
from pathlib import Path
import numpy as np
import mxnet as mx
import onnx
try:
    from mxnet.onnx import export_model
except ImportError:
    from mxnet.contrib.onnx import export_model

parser = argparse.ArgumentParser()
parser.add_argument("root", type=Path)
parser.add_argument("--fixtures", type=Path, required=True)
args = parser.parse_args()
root = args.root
# MXNet 1.7 emits opset-9 operators but checks a bare graph against the newest
# installed ONNX opset. Defer that incomplete check, then validate the full model
# with its actual opset below. No unvalidated model is approved for inference.
original_check = onnx.checker.check_graph
onnx.checker.check_graph = lambda graph: None
try:
    export_model(str(root / "fer-symbol.json"), str(root / "fer-0000.params"), [(1, 1, 64, 64)], np.float32, str(root / "fer.onnx"))
finally:
    onnx.checker.check_graph = original_check
exported = onnx.load(str(root / "fer.onnx"))
del exported.opset_import[:]
exported.opset_import.append(onnx.helper.make_opsetid("", 9))
# Old exporter lists weights as both inputs and initializers. Keep only data
# inputs so runtime can optimize constants without treating weights as overrides.
weights = {item.name for item in exported.graph.initializer}
inputs = [item for item in exported.graph.input if item.name not in weights]
del exported.graph.input[:]
exported.graph.input.extend(inputs)
onnx.checker.check_model(exported)
onnx.save(exported, str(root / "fer.onnx"))
model = mx.gluon.SymbolBlock.imports(str(root / "fer-symbol.json"), ["data"], str(root / "fer-0000.params"), ctx=mx.cpu())
samples = np.load(args.fixtures)
probabilities = np.concatenate([model(mx.nd.array(sample[None])).softmax().asnumpy() for sample in samples])
np.save(root / "fer_reference.npy", probabilities)
