"""Synthetic stress inputs for numerical parity only, never an FER accuracy score."""
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages"))
from examwatch.local.adapters import fer_normalize

root = Path(sys.argv[1] if len(sys.argv) > 1 else "models")
samples = [fer_normalize(np.random.default_rng(index).integers(0, 256, (64, 64), dtype=np.uint8)) for index in range(100)]
np.save(root / "fer_fixtures.npy", np.concatenate(samples))
print("100 synthetic numerical parity inputs; not an accuracy benchmark")
