import os
import json
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches

COLORS = {
    "Living": "#FF9999",
    "Bed": "#99CCFF",
    "Kitchen": "#FFFF99",
    "Bath": "#E0E0E0",
    "Dining": "#FFCC99",
    "Extra": "#CCFFCC",
    "Balcony": "#99FF99",
    "Foyer": "#CC99FF",
    "Storage": "#C0C0C0",
    "Unknown": "#FFFFFF",
}


def _area(geom: list) -> float:
    if len(geom) < 3:
        return 0.0
    pts = np.array(geom)
    xs, ys = pts[:, 0], pts[:, 1]
    return 0.5 * abs(np.dot(xs, np.roll(ys, 1)) - np.dot(ys, np.roll(xs, 1)))


def draw_pf_apartments():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    json_dir = os.path.join(script_dir, "..", "..", "..", "layout_inputs", "Planfinder_Dataset", "pf_jsons")
    out_dir = os.path.join(script_dir, "..", "..", "..", "layout_inputs", "Planfinder_Dataset", "pf_color_code_export")
    os.makedirs(out_dir, exist_ok=True)

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

        dpi = 100
        fig, ax = plt.subplots(figsize=(512 / dpi, 512 / dpi), dpi=dpi)

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
        ax.set_aspect("equal")
        ax.axis("off")

        # LAYER 1: ROOMS
        for room in data.get("rooms", []):
            geom = room.get("geometry", [])
            if not geom or len(geom) < 3:
                continue

            poly_points = np.array(geom)
            name = room.get("name", "Unknown")
            color = COLORS.get(name, COLORS["Unknown"])
            area = round(_area(geom), 2)

            ax.add_patch(patches.Polygon(
                poly_points, closed=True, linewidth=1,
                edgecolor="black", facecolor=color, alpha=0.8,
            ))

            min_x, max_x = np.min(poly_points[:, 0]), np.max(poly_points[:, 0])
            min_y, max_y = np.min(poly_points[:, 1]), np.max(poly_points[:, 1])
            ax.text(
                min_x + (max_x - min_x) / 2,
                min_y + (max_y - min_y) / 2,
                f"{name}\n{area:.2f} m²",
                color="black", fontsize=7, ha="center", va="center",
            )

        # LAYER 2: FACADES (exterior windows)
        for facade in data.get("facades", []):
            if facade.get("attributes", {}).get("type") == "exterior":
                geom = facade.get("geometry", [])
                if len(geom) >= 2:
                    ax.plot(
                        [geom[0][0], geom[1][0]], [geom[0][1], geom[1][1]],
                        color="blue", linewidth=4, zorder=5,
                    )

        # LAYER 3: CIRCULATION / ACCESS
        for circ in data.get("circulation", []):
            if circ.get("attributes", {}).get("type") == "circulation" or "Door" in circ.get("name", ""):
                geom = circ.get("geometry", [])
                if len(geom) >= 2:
                    cx = [geom[0][0], geom[1][0]]
                    cy = [geom[0][1], geom[1][1]]
                    ax.plot(cx, cy, color="green", linewidth=4, zorder=6)
                    ax.text(
                        np.mean(cx), np.mean(cy), "ENTRANCE",
                        color="white", fontsize=6, ha="center", va="center",
                        bbox=dict(facecolor="green", edgecolor="none", pad=0.3, boxstyle="round,pad=0.3"),
                        zorder=7,
                    )

        # LAYER 4: DOORS
        all_door_coords = []
        main_door = data.get("door_point")
        if main_door and len(main_door) == 2:
            all_door_coords.append(main_door)
        for pt in data.get("door_points", []):
            if len(pt) == 2:
                all_door_coords.append(pt)
        for dx, dy in all_door_coords:
            ax.plot(dx, dy, marker="o", markersize=6,
                    markerfacecolor="yellow", markeredgecolor="black", markeredgewidth=1.5, zorder=8)

        out_path = os.path.join(out_dir, json_file.replace('.json', '.png'))
        plt.savefig(out_path, format='png', bbox_inches='tight', pad_inches=0.1)
        plt.close(fig)

    print(f"\nExecution finished! All assets exported successfully to: {out_dir}")


if __name__ == "__main__":
    draw_pf_apartments()
