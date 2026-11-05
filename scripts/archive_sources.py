"""Archive the exact three legacy source trees; deletion is a separate checked step."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parent.parent
TARGETS = [ROOT / 'modules' / name for name in ('emotion','pose','voice')]


def sha256(path):
    digest=hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    backup=ROOT/'backups'
    backup.mkdir(exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    archive=backup/f'legacy-sources-{stamp}.zip'
    manifest=[]
    files=[]
    for target in TARGETS:
        if target.resolve().parent != (ROOT/'modules').resolve() or not target.is_dir():
            raise RuntimeError(f'Unexpected source directory: {target}')
        for path in target.rglob('*'):
            if path.is_symlink():
                raise RuntimeError(f'Symlinks require manual review: {path}')
            if path.is_file():
                files.append(path)
    print(f'Archiving {len(files)} files...',flush=True)
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=3,allowZip64=True) as out:
        for path in files:
            name=path.relative_to(ROOT).as_posix()
            manifest.append(dict(path=name,bytes=path.stat().st_size,sha256=sha256(path)))
            out.write(path,name)
        out.writestr('BACKUP_MANIFEST.json',json.dumps(manifest,indent=2))
    print('Verifying archive contents...',flush=True)
    with zipfile.ZipFile(archive) as source:
        if source.testzip() is not None:
            raise RuntimeError('ZIP CRC validation failed')
        for record in manifest:
            if hashlib.sha256(source.read(record['path'])).hexdigest()!=record['sha256']:
                raise RuntimeError('Archive SHA-256 validation failed')
    (backup/'last-verified-backup.json').write_text(json.dumps({
        'archive':str(archive),'files':len(manifest),
        'source_bytes':sum(r['bytes'] for r in manifest),
        'archive_bytes':archive.stat().st_size,'verified':True,
        'targets':[str(p) for p in TARGETS]},indent=2),encoding='utf-8')
    print(f'Verified backup: {archive}',flush=True)


if __name__=='__main__':
    main()
