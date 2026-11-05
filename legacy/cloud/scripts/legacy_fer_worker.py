"""Run with the isolated legacy environment; stdout is JSON lines only."""
import json
from pathlib import Path
import sys
import numpy as np
import mxnet as mx

root = Path(sys.argv[1])
model = mx.gluon.SymbolBlock.imports(str(root / "fer-symbol.json"), ["data"], str(root / "fer-0000.params"), ctx=mx.cpu())
for line in sys.stdin:
    try:
        tensor = np.array(json.loads(line), dtype=np.float32)
        result = model(mx.nd.array(tensor)).softmax().asnumpy().reshape(-1).tolist()
        print(json.dumps({"probabilities": result}), flush=True)
    except Exception as error:
        print(json.dumps({"error": type(error).__name__}), flush=True)
