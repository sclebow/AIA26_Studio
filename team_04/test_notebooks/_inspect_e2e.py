import json
from pathlib import Path

base = Path(r'c:\Users\tuemi\Downloads\Glabtools\IAAC Repo\bimsc26-datamgmt-session03\AIA26_Studio\team_04\test_notebooks')
with open(base / 'end_to_end_api_agent.ipynb', encoding='utf-8') as f:
    nb = json.load(f)

print('Total cells:', len(nb['cells']))
for i, c in enumerate(nb['cells']):
    ctype = c['cell_type']
    src = c['source'] if isinstance(c['source'], str) else ''.join(c['source'])
    outs = c.get('outputs', [])
    has_out = len(outs) > 0
    preview = src.strip().split('\n')[0][:72]
    print(f'  [{i:02d}] {ctype[:4]}  out={str(has_out):<5}  | {preview}')
