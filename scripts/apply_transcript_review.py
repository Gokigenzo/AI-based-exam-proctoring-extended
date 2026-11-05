"""Apply checked CSV labels to dataset splits, retaining the original manifests."""
import argparse
import csv
import json
from pathlib import Path
from prepare_transcript_dataset import clean


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--dataset', type=Path, default=Path('Audio-dataset/transcripts-tiny'))
    args = parser.parse_args()
    root = args.dataset
    with (root/'review.csv').open(encoding='utf-8-sig', newline='') as source:
        review_rows = list(csv.DictReader(source))
    labels = {r['audio']:r for r in review_rows}
    if len(labels) != len(review_rows):
        raise ValueError('Duplicate audio in review CSV')
    pending, prepared = [], {}
    for split in ['train','validation','test']:
        path = root/'splits'/f'{split}.jsonl'
        rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        for row in rows:
            reviewed = labels[row['audio']]
            if reviewed['split'] != split:
                raise ValueError('Do not move clips between temporal splits')
            if reviewed['reviewed'].strip().lower() not in {'yes','true','1'}:
                pending.append(row['audio'])
            text = clean(reviewed['text'])
            if not text:
                raise ValueError('Empty reviewed label')
            row.update(text=text,label_status='reviewed')
        prepared[path] = rows
    if pending:
        raise ValueError(f'{len(pending)} clips still unreviewed; listen, correct text and mark reviewed=yes in review.csv')
    for path, rows in prepared.items():
        original = path.with_suffix('.original.jsonl')
        if not original.exists():
            original.write_bytes(path.read_bytes())
        path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
    print('Reviewed labels applied. Original manifests retained.')


if __name__ == '__main__':
    main()
