import json
import os

# Load once at import
with open(os.path.join(os.path.dirname(__file__), "program_rules.json")) as f:
    RULES = json.load(f)
with open(os.path.join(os.path.dirname(__file__), "program_synonyms.json")) as f:
    SYNONYMS = json.load(f)

def normalize_program(prog: str) -> str:
    if not prog:
        return ""
    p = prog.strip().lower().replace(' ', '').replace('-', '_')
    return SYNONYMS.get(p, p)