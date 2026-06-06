import os
import json
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from collections import defaultdict
from matplotlib.colors import to_hex
import seaborn as sns

def extract_all_typologies(json_dir):
    """
    Scans all JSON files in the directory to find every unique room typology.
    This ensures a completely fixed and consistent color code across all 500+ plots.
    """
    unique_typologies = set()
    json_files = [f for f in os.listdir(json_dir) if f.endswith('.json')]
    
    print("Scanning dataset for room typologies...")
    for json_file in json_files:
        filepath = os.path.join(json_dir, json_file)
        with open(filepath, 'r') as f:
            try:
                data = json.load(f)
                # Read room names directly from the rooms array
                for room in data.get("rooms", []):
                    room_name = room.get("name", "Unknown")
                    unique_typologies.add(room_name)
            except (json.JSONDecodeError, KeyError):
                continue
                
    sorted_typologies = sorted(list(unique_typologies))
    print(f"Found {len(sorted_typologies)} unique typologies: {sorted_typologies}\n")
    return sorted_typologies

def generate_fixed_palette(typologies):
    """
    Generates a deterministic color palette mapping for the extracted typologies.
    """
    colors = sns.color_palette("husl", len(typologies))
    return {typology: to_hex(color) for typology, color in zip(typologies, colors)}

def draw_pf_apartments():
    # Setup paths relative to this script script position
    script_dir = os.path.dirname(os.path.abspath(__file__))
    json_dir = os.path.join(script_dir, "..", "..", "..", "layout_inputs", "Planfinder_Dataset", "pf_jsons")
    out_dir = os.path.join(script_dir, "..", "..", "..", "layout_inputs", "Planfinder_Dataset", "pf_color_code_export")
    os.makedirs(out_dir, exist_ok=True)

    # Step 1: Scan all files to generate a unified color mapping
    typologies = extract_all_typologies(json_dir)
    COLOR_MAP = generate_fixed_palette(typologies)
    
    json_files = [f for f in os.listdir(json_dir) if f.endswith('.json')]
    print(f"Starting rendering process for {len(json_files)} layouts...")

    for json_file in json_files:
        filepath = os.path.join(json_dir, json_file)
        with open(filepath, 'r') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                print(f"Skipping invalid file: {json_file}")
                continue

        # Initialize plot canvas (512x512 pixels configuration)
        dpi = 100
        fig, ax = plt.subplots(figsize=(512/dpi, 512/dpi), dpi=dpi)
        
        # Calculate dynamic plot limits based on the apartment boundary outline
        outline = data.get("outline", [])
        if outline:
            xs = [pt[0] for pt in outline]
            ys = [pt[1] for pt in outline]
            margin = 0.8
            ax.set_xlim(min(xs) - margin, max(xs) + margin)
            ax.set_ylim(min(ys) - margin, max(ys) + margin)
        else:
            ax.set_xlim(-1, 15)
            ax.set_ylim(-1, 15)
            
        # Standardize aspect ratio and clear coordinate axes clutter
        ax.set_aspect('equal')
        ax.axis('off')

        # --- LAYER 1: DRAW ROOMS (Thick Black Internal Walls) ---
        rooms = data.get("rooms", [])
        for room in rooms:
            geom = room.get("geometry", [])
            if not geom or len(geom) < 3: 
                continue
            
            poly_points = np.array(geom)
            room_name = room.get("name", "Unknown")
            face_color = COLOR_MAP.get(room_name, "#FFFFFF")
            
            # Thick black borders for rooms (linewidth=3.5)
            room_poly = patches.Polygon(
                poly_points, closed=True, linewidth=3.5, edgecolor='black', 
                facecolor=face_color, alpha=0.9, zorder=2
            )
            ax.add_patch(room_poly)
            
            # Label room centers
            min_x, max_x = np.min(poly_points[:, 0]), np.max(poly_points[:, 0])
            min_y, max_y = np.min(poly_points[:, 1]), np.max(poly_points[:, 1])
            cx = min_x + (max_x - min_x) / 2
            cy = min_y + (max_y - min_y) / 2
            ax.text(cx, cy, room_name, color='black', fontsize=8, weight='bold', 
                    ha='center', va='center', zorder=3)
        
        # --- LAYER 2: DRAW EXTERIOR APARTMENT OUTLINE (Extra Thick Walls) ---
        if outline and len(outline) > 2:
            outline_poly = patches.Polygon(
                np.array(outline), closed=True, linewidth=5.5, 
                edgecolor='black', facecolor='none', zorder=4
            )
            ax.add_patch(outline_poly)
            
        # --- LAYER 3: DRAW WINDOWS (Light Blue Outer Facades) ---
        facades = data.get("facades", [])
        for facade in facades:
            if facade.get("attributes", {}).get("type") == "exterior":
                geom = facade.get("geometry", [])
                if len(geom) >= 2:
                    wx = [geom[0][0], geom[1][0]]
                    wy = [geom[0][1], geom[1][1]]
                    ax.plot(wx, wy, color="#189FEC", linewidth=4.5, zorder=5)

        # --- LAYER 4: DRAW ACCESS / CIRCULATION SIDE (Bright Red Line) ---
        circulation_items = data.get("circulation", [])
        for circ in circulation_items:
            # Check if it marks the primary entry side context
            if circ.get("attributes", {}).get("type") == "circulation" or "Door" in circ.get("name", ""):
                c_geom = circ.get("geometry", [])
                if len(c_geom) >= 2:
                    cx = [c_geom[0][0], c_geom[1][0]]
                    cy = [c_geom[0][1], c_geom[1][1]]
                    # Highlight the access edge with a thick bright red stroke
                    ax.plot(cx, cy, color="#E76711", linewidth=6.0, label='Access Side', zorder=6)

        # --- LAYER 5: DRAW DOORS (Yellow Dots with crisp White Outlines) ---
        # 5a. Gather individual main entry door coordinates if present
        all_door_coordinates = []
        main_door = data.get("door_point")
        if main_door and len(main_door) == 2:
            all_door_coordinates.append(main_door)
            
        # 5b. Accumulate all interior/secondary door point arrays
        door_points_list = data.get("door_points", [])
        for pt in door_points_list:
            if len(pt) == 2:
                all_door_coordinates.append(pt)
                
        # 5c. Plot collected coordinate sets uniformly
        for dx, dy in all_door_coordinates:
            ax.plot(
                dx, dy, marker='o', markersize=7, markerfacecolor='yellow', 
                markeredgecolor='white', markeredgewidth=1.5, zorder=7
            )

        # Save out frame clear of layout borders
        out_path = os.path.join(out_dir, json_file.replace('.json', '.png'))
        plt.savefig(out_path, format='png', bbox_inches='tight', pad_inches=0.1)
        plt.close(fig)

    # Export translation map as an external legend checklist
    with open(os.path.join(out_dir, "fixed_color_legend.txt"), 'w') as f:
        for typology, color in COLOR_MAP.items():
            f.write(f"{typology}: {color}\n")

    print(f"\nExecution finished! All assets exported successfully to: {out_dir}")

if __name__ == "__main__":
    draw_pf_apartments()