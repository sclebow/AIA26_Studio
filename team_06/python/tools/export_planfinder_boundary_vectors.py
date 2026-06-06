"""Export boundary embeddings for Planfinder_Dataset.

Writes two files into `team_06/output/`:
- `planfinder_boundary_vectors.json` : list of {layoutId, path, vector}
- `planfinder_boundary_vectors.npy` : stacked float32 array of vectors

Usage: run from repo root Python environment.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
from typing import List

# Importiamo le funzioni REALI presenti nel tuo matcher
from tools.boundary_embedding_matcher import (
    _vector_from_coords,
    _normalize_layout_outline
)


def find_planfinder_jsons(root: Path) -> List[Path]:
    pf_dir = root / 'team_06' / 'layout_inputs' / 'Planfinder_Dataset'
    if not pf_dir.exists():
        return []
    return sorted(pf_dir.glob('*.json'))


def load_layout(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}


def main():
    repo = Path('.').resolve()
    files = find_planfinder_jsons(repo)
    out_dir = repo / 'team_06' / 'output'
    out_dir.mkdir(parents=True, exist_ok=True)

    records = []
    vectors = []

    for p in files:
        layout = load_layout(p)
        if not layout:
            continue
            
        layout_id = layout.get('layoutId') or p.stem
        coords = layout.get('outline') or layout.get('apartment', {}).get('geometry')
        
        if not coords:
            continue
            
        # Prepariamo un dizionario compatibile con la funzione di normalizzazione
        layout_like = {"outline": coords, "circulation": layout.get("circulation", [])}
        
        # 1. Allinea all'ingresso e forza il senso orario
        aligned_coords = _normalize_layout_outline(layout_like)
        
        # 2. Calcola la turning function a 64-D
        vec = _vector_from_coords(aligned_coords)
        
        vectors.append(vec.astype('float32'))
        records.append({
            'layoutId': layout_id,
            'path': str(p),
            'vector': vec.tolist()
        })

    if vectors:
        stacked = np.vstack(vectors)
        npy_path = out_dir / 'planfinder_boundary_vectors.npy'
        json_path = out_dir / 'planfinder_boundary_vectors.json'
        
        np.save(str(npy_path), stacked)
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(records, f, indent=2)
            
        print('Wrote', npy_path, json_path)
    else:
        print('No Planfinder layout JSONs found or no vectors generated')


if __name__ == '__main__':
    main()
