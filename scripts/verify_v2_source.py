"""Compare runtime/web with the v2 snapshot, tolerating Git newline conversion."""
from pathlib import Path
import hashlib
import json

root=Path(__file__).resolve().parents[1]
manifest=json.loads((root/'V2_SOURCE.json').read_text(encoding='utf-8'))
errors=[]
for name,expected in manifest['normalized_lf_sha256'].items():
    path=root/name
    if not path.is_file() or hashlib.sha256(path.read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=expected:
        errors.append(name)
if errors:
    raise SystemExit('Changed since v2 snapshot: '+', '.join(errors))
print(f"V2 snapshot matches: {len(manifest['normalized_lf_sha256'])} runtime/web files")
