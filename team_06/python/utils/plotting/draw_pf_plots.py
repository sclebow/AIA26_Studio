import os
import json
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from collections import defaultdict
from matplotlib.colors import to_hex
import seaborn as sns

def generate_color_palette(typologies):
    """Generate a consistent color palette for room typologies"""
    colors = sns.color_palette("husl", len(typologies))
    return {typology: to_hex(color) for typology, color in zip(typologies, colors)}

def extract_typologies(json_dir):
    """Scan all JSON files and extract unique room typologies"""
    typologies = set()
    json_files = [f for f in os.listdir(json_dir) if f.endswith('.json')]
    
    for json_file in json_files:
        filepath = os.path.join(json_dir, json_file)
        with open(filepath, 'r') as f:
            try:
                data = json.load(f)
                for room in data.get("rooms", []):
                    typologies.add(room.get("name", "Unknown"))
            except json.JSONDecodeError:
                print(f"Warning: Could not parse {json_file}")
                continue
    
    return sorted(typologies)

def draw_pf_apartments():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    json_dir = os.path.join(script_dir, "..", "..", "..", "layout_inputs", "Planfinder_Dataset", "pf_jsons")
    out_dir = os.path.join(script_dir, "..", "..", "..", "pf_color_code_export")
    os.makedirs(out_dir, exist_ok=True)

    # Collect all room typologies 
    typologies = extract_typologies(json_dir)
    COLORS = generate_color_palette(typologies)
    
    json_files = [f for f in os.listdir(json_dir) if f.endswith('.json')]
    print(f"Found {len(json_files)} Planfinder apartments to draw.")

    for json_file in json_files:
        filepath = os.path.join(json_dir, json_file)
        with open(filepath, 'r') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                print(f"Skipping invalid JSON file: {json_file}")
                continue

        dpi = 100
        fig, ax = plt.subplots(figsize=(512/dpi, 512/dpi), dpi=dpi)
        
        # Determine bounds dynamically based on outline
        outline = data.get("outline", [])
        if outline:
            xs = [pt[0] for pt in outline]
            ys = [pt[1] for pt in outline]
            margin = 0.5
            ax.set_xlim(min(xs) - margin, max(xs) + margin)
            ax.set_ylim(min(ys) - margin, max(ys) + margin)
        else:
            ax.set_xlim(0, 12.8)
            ax.set_ylim(0, 12.8)
            
        ax.invert_yaxis()
        ax.set_aspect('equal')
        ax.axis('off')

        # Draw Rooms
        rooms = data.get("rooms", [])
        for room in rooms:
            geom = room.get("geometry", [])
            if not geom or len(geom) < 3: continue
            
            poly_points = np.array(geom)
            name = room.get("name", "Unknown")
            color = COLORS.get(name, "#FFFFFF")
            
            poly = patches.Polygon(poly_points, closed=True, linewidth=1, edgecolor='black', 
                                 facecolor=color, alpha=0.8)
            ax.add_patch(poly)
            
            # Place label at logical center of bounding box
            min_x, max_x = np.min(poly_points[:, 0]), np.max(poly_points[:, 0])
            min_y, max_y = np.min(poly_points[:, 1]), np.max(poly_points[:, 1])
            ax.text(min_x + (max_x - min_x)/2, min_y + (max_y - min_y)/2, 
                   name, color='black', fontsize=8, ha='center', va='center')
            
        # Draw Doors as dots
        doors = data.get("doors", [])
        for door in doors:
            geom = door.get("geometry", [])
            if len(geom) >= 1:
                dx, dy = geom[0][0], geom[0][1]
                ax.plot(dx, dy, marker='o', markersize=6, color='black', 
                       markeredgecolor='black', zorder=6)

        # Draw Windows (from facades) as light blue lines
        facades = data.get("facades", [])
        for facade in facades:
            if facade.get("attributes", {}).get("type") == "exterior":
                geom = facade.get("geometry", [])
                if len(geom) >= 2:
                    wx = [geom[0][0], geom[1][0]]
                    wy = [geom[0][1], geom[1][1]]
                    ax.plot(wx, wy, color='#A4D3EE', linewidth=3, zorder=5)

        out_path = os.path.join(out_dir, json_file.replace('.json', '.png'))
        plt.savefig(out_path, format='png', bbox_inches='tight')
        plt.close(fig)

    print(f"Finished rendering Planfinder apartments! Images saved in {out_dir}")
    # Save color legend
    with open(os.path.join(out_dir, "color_legend.txt"), 'w') as f:
        for typology, color in COLORS.items():
            f.write(f"{typology}: {color}\n")

if __name__ == "__main__":
    draw_pf_apartments()