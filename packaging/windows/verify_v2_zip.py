"""Verify archive paths/hash and smoke-test the extracted portable Python."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import os
import subprocess
import zipfile

root=Path(__file__).resolve().parents[2]
archive=root/'release/v2.zip'
expected=(root/'release/v2.zip.sha256').read_text().split()[0]
assert hashlib.sha256(archive.read_bytes()).hexdigest()==expected
destination=root/'.tmp/v2-extracted-qa'
destination.mkdir(exist_ok=True)
with zipfile.ZipFile(archive) as z:
    for name in z.namelist():
        p=PurePosixPath(name)
        assert not p.is_absolute() and '..' not in p.parts and p.parts[0]=='v2'
    z.extractall(destination)
package=destination/'v2'
env=os.environ.copy()
env.update(EXAMWATCH_HOME=str(root/'.tmp/v2-zip-home'),PYTHONHOME='Z:/missing',PYTHONPATH='Z:/missing')
result=subprocess.run([str(package/'runtime/python.exe'),str(package/'app/portable_server.py'),'--self-test'],
    env=env,cwd=package,capture_output=True,text=True,timeout=120)
assert result.returncode==0,result.stderr
report=json.loads(result.stdout)
assert report['ok'] and report['version']=='v2'
(root/'.tmp/v2-extracted-qa-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(dict(ok=True,version=report['version'],zip_sha256=expected)))
