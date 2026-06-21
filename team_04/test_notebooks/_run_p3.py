"""
Execute test_urban_context_P3.ipynb cell by cell.
Captures stdout + matplotlib figures → embeds them back into the notebook as outputs.
"""
import sys, os, io, json, base64, traceback
from pathlib import Path

sys.path.insert(0, r'c:\Users\tuemi\Downloads\Glabtools\IAAC Repo\bimsc26-datamgmt-session03\AIA26_Studio')
os.chdir(r'c:\Users\tuemi\Downloads\Glabtools\IAAC Repo\bimsc26-datamgmt-session03\AIA26_Studio\team_04\test_notebooks')

NB_PATH = Path('test_urban_context_P3.ipynb')

# ── matplotlib backend: Agg (non-interactive, captures to buffer) ─────────────
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# ── helper: capture a figure as base64 PNG ────────────────────────────────────
def _fig_to_output(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=130, bbox_inches='tight')
    buf.seek(0)
    data = base64.b64encode(buf.read()).decode('ascii')
    return {
        "output_type": "display_data",
        "data": {"image/png": data, "text/plain": ["<Figure>"]},
        "metadata": {"image/png": {"width": 1200}},
    }

# ── load notebook ─────────────────────────────────────────────────────────────
with open(NB_PATH, encoding='utf-8') as f:
    nb = json.load(f)

# ── execution namespace ───────────────────────────────────────────────────────
g = {}

print('Running test_urban_context_P3.ipynb ...')
print('=' * 65)

for ci, cell in enumerate(nb['cells']):
    if cell['cell_type'] != 'code':
        continue

    src = cell['source'] if isinstance(cell['source'], str) else ''.join(cell['source'])
    if not src.strip():
        continue

    # Capture stdout
    old_stdout = sys.stdout
    sys.stdout  = io.StringIO()

    cell_outputs = []
    figs_before  = set(map(id, map(plt.figure, plt.get_fignums())))

    try:
        exec(compile(src, f'<cell {ci}>', 'exec'), g)
        stdout_val = sys.stdout.getvalue()
    except Exception:
        stdout_val = sys.stdout.getvalue()
        tb = traceback.format_exc()
        sys.stdout = old_stdout
        print(f'\n[Cell {ci}] ERROR:')
        print(tb[:600])
        # Store the error output
        cell['outputs'] = [{"output_type": "stream", "name": "stdout", "text": stdout_val},
                           {"output_type": "stream", "name": "stderr", "text": tb}]
        cell['execution_count'] = ci
        continue
    finally:
        sys.stdout = old_stdout

    # Print captured stdout so we can see progress
    if stdout_val.strip():
        print(f'\n[Cell {ci}]')
        for ln in stdout_val.strip().split('\n'):
            print(' ', ln)

    # Collect stdout output
    if stdout_val.strip():
        cell_outputs.append({
            "output_type": "stream",
            "name": "stdout",
            "text": stdout_val,
        })

    # Collect any new figures
    new_figs = [plt.figure(n) for n in plt.get_fignums()
                if id(plt.figure(n)) not in figs_before]
    # Actually, check all current figures — save all open ones after this cell
    for fnum in plt.get_fignums():
        fig = plt.figure(fnum)
        if id(fig) not in figs_before:
            cell_outputs.append(_fig_to_output(fig))
    plt.close('all')

    cell['outputs'] = cell_outputs
    cell['execution_count'] = ci

print()
print('=' * 65)
print('Writing outputs back to notebook ...')

with open(NB_PATH, 'w', encoding='utf-8') as f:
    json.dump(nb, f, ensure_ascii=False, indent=1)

print('Done. Open test_urban_context_P3.ipynb to see the embedded figures.')
