import hashlib
import json
from pathlib import Path
import run_development as core

p=Path(__file__).resolve().parent
spec=json.loads((p/'development_spec_v2.json').read_text())
core.BUNDLES={k:v for k,v in core.BUNDLES.items() if k in spec['families']}
manifest=json.loads((p/'out/development_v1/manifest.json').read_text())
feature_bytes=(p/'out/development_v1/features.json').read_bytes()
assert hashlib.sha256(feature_bytes).hexdigest()==manifest['files']['features.json']
panel=json.loads(feature_bytes)
predictions,runs,results=core.run(panel,spec)
out=p/'out/development_v2';out.mkdir(exist_ok=False)
for name,value in [('predictions.json',predictions),('runs.json',runs),('results.json',results)]:
 (out/name).write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n')
m={'availability':'RETROSPECTIVE_DEVELOPMENT_NOT_PIT_REPLAY','live_calls':0,'promotions':0,'spec_sha256':hashlib.sha256((p/'development_spec_v2.json').read_bytes()).hexdigest(),'core_sha256':hashlib.sha256((p/'run_development.py').read_bytes()).hexdigest(),'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'feature_sha256':hashlib.sha256(feature_bytes).hexdigest(),'files':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(out.iterdir())}}
(out/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
print(json.dumps({'runs':[{k:v for k,v in r.items() if not k.endswith('_ids')} for r in runs],'results':{k:{'n':v['arms'].get('M1',{}).get('n',0),'M1_minus_M2':v.get('M1_minus_M2'),'M2_minus_M2H':v.get('M2_minus_M2H')} for k,v in results.items()}},indent=2))
