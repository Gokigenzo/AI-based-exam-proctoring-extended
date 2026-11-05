"""Run feature regressions using only the distributed v2 Python and libraries."""
from pathlib import Path
import importlib.util
import json

ROOT=Path(__file__).resolve().parents[2]
checks=[]
for name in ['test_tracking','test_pose_tracking','test_clips']:
    spec=importlib.util.spec_from_file_location(name,ROOT/'tests'/f'{name}.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for key,function in vars(module).items():
        if not key.startswith('test_'):
            continue
        if name=='test_clips':
            output=ROOT/'.tmp'/'v2 video kiểm tra'/key
            output.mkdir(parents=True,exist_ok=True)
            function(output)
        else:
            function()
        checks.append(key)
report=dict(ok=True,checks=checks)
(ROOT/'.tmp/portable-v2-feature-qa.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
