import json
from pathlib import Path


def main():
    base = Path(__file__).parent
    rplan_dir = base / "RPLAN_Dataset_R-NB"
    sample_path = base / "sample_layouts.json"
    backup_path = base / "sample_layouts.json.bak"

    if not rplan_dir.exists():
        print(f"RPLAN folder not found: {rplan_dir}")
        return 2

    # Backup existing sample file
    if sample_path.exists():
        sample_path.replace(backup_path)
        print(f"Backed up existing sample to: {backup_path}")

    merged = []
    files = sorted([p for p in rplan_dir.glob('*.json') if p.name.lower() != 'graphs.json'])
    if not files:
        print(f"No JSON files found in {rplan_dir}")
        return 3

    for p in files:
        try:
            with p.open('r', encoding='utf-8-sig') as fh:
                data = json.load(fh)
        except Exception as e:
            print(f"Failed to read {p}: {e}")
            continue

        if isinstance(data, list):
            merged.extend(data)
        elif isinstance(data, dict):
            merged.append(data)
        else:
            print(f"Skipping {p}: unexpected JSON root type {type(data)}")

    # Write merged file with UTF-8 (no BOM) and pretty formatting
    with sample_path.open('w', encoding='utf-8') as fh:
        json.dump(merged, fh, indent=4, ensure_ascii=False)

    print(f"Wrote {len(merged)} entries to {sample_path}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
