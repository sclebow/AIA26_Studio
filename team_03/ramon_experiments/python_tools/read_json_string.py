import json

def read_json_as_string(file_path):
    if file_path is None or str(file_path).strip() == "":
        return None, "[ERROR] No path connected. Connect 'full_paths' from read_layout_relative."

    file_path = str(file_path).strip()

    import os
    if not os.path.isfile(file_path):
        return None, "[ERROR] File not found: {}".format(file_path)

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    json_string = json.dumps(data)
    return json_string, "[OK] Loaded: {}".format(file_path)

# path viene del input del componente GHPython
try:
    _p = path
except NameError:
    _p = None

json_string, info = read_json_as_string(_p)
