"""
GHPython component: Read layout JSON files using paths relative to the .gh file.

INPUTS:
    relative_path  (str)  - Relative path to a single JSON file.
                            Example: "../layout/layout_residential_complex.json"
    folder_path    (str)  - Relative path to a folder containing JSON files.
                            Example: "../layout"

OUTPUTS:
    json_strings  (list)  - List of JSON strings (one per file loaded).
    file_names    (list)  - List of file names corresponding to each JSON string.
    full_paths    (list)  - List of resolved absolute paths (for debugging).
    info          (str)   - Status message.
"""

import os
import json
import glob as globmod

# ---- Read inputs directly (no eval) ----
rel = None
try:
    if relative_path is not None and str(relative_path).strip() != "":
        rel = str(relative_path).strip()
except NameError:
    pass

folder = None
try:
    if folder_path is not None and str(folder_path).strip() != "":
        folder = str(folder_path).strip()
except NameError:
    pass

# ---- Outputs (match GHPython component output names) ----
json_string = []
full_path = []
info = ""

print("DEBUG rel: {}".format(rel))
print("DEBUG folder: {}".format(folder))

if rel is None and folder is None:
    info = "[ERROR] Connect 'relative_path' (single file) or 'folder_path' (all JSONs in folder)"
else:
    try:
        gh_file = ghenv.Component.OnPingDocument().FilePath
        if gh_file is None or gh_file == "":
            info = "[ERROR] Save the .gh file first."
        else:
            gh_folder = os.path.dirname(gh_file)
            errors = []
            loaded = 0

            # --- Single file ---
            if rel is not None:
                resolved = os.path.normpath(os.path.join(gh_folder, rel))
                if not os.path.isfile(resolved):
                    errors.append("File not found: {}".format(resolved))
                else:
                    with open(resolved, "r") as f:
                        text = f.read()
                    json.loads(text)
                    json_string.append(text)
                    full_path.append(resolved)
                    loaded += 1

            # --- Folder ---
            if folder is not None:
                resolved_folder = os.path.normpath(os.path.join(gh_folder, folder))
                if not os.path.isdir(resolved_folder):
                    errors.append("Folder not found: {}".format(resolved_folder))
                else:
                    pattern = os.path.join(resolved_folder, "*.json")
                    files = sorted(globmod.glob(pattern))
                    if len(files) == 0:
                        errors.append("No .json files in: {}".format(resolved_folder))
                    else:
                        for fp in files:
                            try:
                                with open(fp, "r") as f:
                                    text = f.read()
                                json.loads(text)
                                json_string.append(text)
                                full_path.append(fp)
                                loaded += 1
                            except Exception as e:
                                errors.append("{}: {}".format(os.path.basename(fp), e))

            # --- Build info ---
            parts = []
            if loaded > 0:
                names = [os.path.basename(p) for p in full_path]
                parts.append("[OK] Loaded {} file(s): {}".format(loaded, ", ".join(names)))
            if errors:
                parts.append("[ERRORS] " + " | ".join(errors))
            info = "\n".join(parts)

    except Exception as e:
        info = "[ERROR] {}".format(e)
