"""Load local JSON using datasets without duplicating WAV files in Arrow."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--dataset', type=Path, default=ROOT / 'Audio-dataset')
    args = parser.parse_args()
    root = args.dataset.resolve()
    from datasets import load_dataset
    # The remote repository stores string paths, not embedded Audio objects.
    # Point to local manifests so a later training run does not need the Hub.
    dataset = load_dataset('json', data_files={
        name: str(root / 'splits' / f'{name}.jsonl') for name in ('train', 'validation', 'test')},
        cache_dir=str(root / '.datasets-cache'))
    output = root / 'huggingface-dataset'
    if not output.exists():
        dataset.save_to_disk(str(output))
    print(json.dumps({name: len(rows) for name, rows in dataset.items()}))

if __name__ == '__main__':
    main()
