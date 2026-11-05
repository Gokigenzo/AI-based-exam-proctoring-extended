"""Download exactly the audio referenced by VietSuperSpeech, resumably."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import threading
import time
import wave

REPO = 'thanhnew2001/VietSuperSpeech'
REVISION = 'cbf624ae9b30e1c2793a27e95b262115c69601f3'
ROOT = Path(__file__).resolve().parent.parent

def safe_audio(root, relative):
    parts = PurePosixPath(relative)
    if parts.is_absolute() or '..' in parts.parts or '\\' in relative or ':' in relative:
        raise ValueError(f'Unsafe audio path: {relative}')
    target = (root / relative).resolve()
    if not target.is_relative_to(root.resolve()) or not relative.startswith('audio/'):
        raise ValueError(f'Unsafe audio path: {relative}')
    return target

def valid_wav(path):
    try:
        with wave.open(str(path), 'rb') as audio:
            expected = audio.getnframes() * audio.getnchannels() * audio.getsampwidth()
            return (audio.getnframes() > 0 and audio.getframerate() > 0
                    and len(audio.readframes(audio.getnframes())) == expected)
    except (OSError, EOFError, wave.Error):
        return False

def source_split(source):
    # Same source recording is never present in multiple evaluation partitions.
    bucket = int(hashlib.sha256(source.encode('utf-8')).hexdigest()[:8], 16) % 100
    return 'test' if bucket < 5 else 'validation' if bucket < 10 else 'train'

def prepare_manifests(root):
    unique = {}
    for name in ('train', 'dev'):
        for row in json.loads((root / f'{name}.json').read_text(encoding='utf-8')):
            safe_audio(root, row['audio'])
            if row['audio'] in unique and unique[row['audio']]['text'] != row['text']:
                raise ValueError(f'Conflicting label: {row["audio"]}')
            unique[row['audio']] = row
    groups = {k: [] for k in ('train', 'validation', 'test')}
    for row in unique.values():
        if not row.get('source'):
            raise ValueError('Missing source: cannot build independent evaluation splits')
        groups[source_split(row['source'])].append(row)
    split_dir = root / 'splits'
    split_dir.mkdir(exist_ok=True)
    for name, rows in groups.items():
        with (split_dir / f'{name}.jsonl').open('w', encoding='utf-8') as out:
            for row in rows:
                out.write(json.dumps(row, ensure_ascii=False) + '\n')
    return unique, {k: len(v) for k, v in groups.items()}

def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'Audio-dataset')
    parser.add_argument('--workers', type=int, default=12)
    parser.add_argument('--limit', type=int, default=0, help='Smoke download only; 0 downloads all audio')
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    from huggingface_hub import hf_hub_download, hf_hub_url, get_token
    import httpx
    for file in ('README.md', 'manifest.json', 'train.json', 'dev.json'):
        hf_hub_download(REPO, file, repo_type='dataset', revision=REVISION, local_dir=str(root))
    records, counts = prepare_manifests(root)
    selected = list(records)[:args.limit or None]
    # PCM metadata estimates ~28 GB. Reserve room for training checkpoints as well.
    estimate = sum(float(records[p]['duration']) * 32000 for p in selected if not (root / p).exists())
    if shutil.disk_usage(root).free < estimate + 3 * 1024**3:
        raise RuntimeError(f'Not enough disk space: need about {(estimate / 1024**3)+3:.1f} GiB free')
    local = threading.local()
    path_lock = threading.Lock()
    request_lock = threading.Lock()
    next_request = [0.0]
    token = get_token()
    def download(relative):
        # Serialize validation/creation: Windows path canonicalization can race
        # while workers create a shared, previously absent folder.
        with path_lock:
            target = safe_audio(root, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
        if valid_wav(target):
            return target.stat().st_size
        if not hasattr(local, 'http'):
            local.http = httpx.Client(follow_redirects=True, timeout=httpx.Timeout(120, connect=30))
        for attempt in range(8):
            try:
                headers = {'Authorization': f'Bearer {token}'} if token else {}
                url = hf_hub_url(REPO, relative, repo_type='dataset', revision=REVISION)
                part = target.with_suffix('.wav.part')
                # Public Hub resolver quota is 3000 requests / 5 minutes.
                # Bound aggregate requests across workers, including retries.
                with request_lock:
                    delay = max(0, next_request[0] - time.monotonic())
                    if delay:
                        time.sleep(delay)
                    next_request[0] = time.monotonic() + .12
                with local.http.stream('GET', url, headers=headers) as response:
                    if response.status_code == 429:
                        retry = min(300, max(1, int(response.headers.get('retry-after', '60'))))
                        with request_lock:
                            next_request[0] = max(next_request[0], time.monotonic() + retry)
                    response.raise_for_status()
                    with part.open('wb') as out:
                        for block in response.iter_bytes(1024 * 1024):
                            out.write(block)
                if not valid_wav(part):
                    raise ValueError('Invalid or truncated WAV')
                part.replace(target)
                return target.stat().st_size
            except (httpx.HTTPError, ValueError, OSError):
                if attempt == 7:
                    raise
                time.sleep(min(120, 2 ** (attempt + 1)))
    status = dict(repository=REPO, revision=REVISION, total=len(records), selected=len(selected),
                  splits=counts, complete=False, completed=0, bytes=0, failures=[])
    def report():
        status['updated_at'] = datetime.now(timezone.utc).isoformat()
        temp = root / 'download-status.tmp'
        temp.write_text(json.dumps(status, indent=2), encoding='utf-8')
        for retry in range(10):
            try:
                temp.replace(root / 'download-status.json')
                break
            except PermissionError:
                if retry == 9:
                    raise
                time.sleep(.1)
        print(f"Audio: {status['completed']}/{len(selected)}; {status['bytes']/1024**3:.2f} GiB; errors={len(status['failures'])}", flush=True)
    report()
    with ThreadPoolExecutor(max_workers=max(1, min(32, args.workers))) as pool:
        futures = {pool.submit(download, path): path for path in selected}
        for future in as_completed(futures):
            try:
                status['bytes'] += future.result()
                status['completed'] += 1
            except Exception as exc:
                status['failures'].append({'audio': futures[future], 'error': str(exc)})
            if (status['completed'] + len(status['failures'])) % 100 == 0:
                report()
    status['complete'] = status['completed'] == len(records) and not status['failures']
    report()
    if status['failures']:
        raise SystemExit('Some audio failed; rerun the same command to resume.')

if __name__ == '__main__':
    main()
