from pathlib import Path
import hashlib
import json
import zipfile

root = Path("dist/ExamWatch")
if not (root / "Start ExamWatch.cmd").exists():
    raise SystemExit("Build and validate the portable directory first")
target = Path("dist/ExamWatch-Windows-x64.zip")
with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as archive:
    for path in sorted(root.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
            archive.write(path, path.relative_to(root.parent))
checksum = hashlib.sha256()
with target.open("rb") as handle:
    for block in iter(lambda: handle.read(1024 * 1024), b""):
        checksum.update(block)
report = {"path": str(target), "size_bytes": target.stat().st_size, "sha256": checksum.hexdigest(), "clean_windows_machine_tested": False}
Path("deliverables/verification/portable.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report))
