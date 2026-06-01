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


def format_area(room):
    attrs = room.get("attributes", {})
    area = attrs.get("area")
    if area is None:
        geom = room.get("geometry", [])
        if len(geom) >= 4:
            points = np.array(geom)
            xs = points[:, 0]
            ys = points[:, 1]
            area = 0.5 * abs(np.dot(xs, np.roll(ys, 1)) - np.dot(ys, np.roll(xs, 1)))
        else:
            area = 0.0
    return round(float(area), 2)


def draw_no_balcony_with_area():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    json_dir = os.path.join(script_dir, "Team06_Export", "No_Balcony")
    out_dir = os.path.join(script_dir, "Team06_Images", "No_Balcony_Area")
    os.makedirs(out_dir, exist_ok=True)

    json_files = [f for f in os.listdir(json_dir) if f.endswith(".json")]
    print(f"Found {len(json_files)} No_Balcony apartments to draw.")

    for json_file in json_files:
        filepath = os.path.join(json_dir, json_file)
        with open(filepath, "r") as f:
            data = json.load(f)

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

        rooms = data.get("rooms", [])
        for room in rooms:
            geom = room.get("geometry", [])
            if not geom or len(geom) < 3:
                continue

            poly_points = np.array(geom)
            name = room.get("name", "Unknown")
            color = COLORS.get(name, COLORS["Unknown"])
            area = format_area(room)

            poly = patches.Polygon(
                poly_points,
                closed=True,
                linewidth=1,
                edgecolor="black",
                facecolor=color,
                alpha=0.8,
            )
            ax.add_patch(poly)

            min_x, max_x = np.min(poly_points[:, 0]), np.max(poly_points[:, 0])
            min_y, max_y = np.min(poly_points[:, 1]), np.max(poly_points[:, 1])
            label = f"{name}\n{area:.2f} m²"
            ax.text(
                min_x + (max_x - min_x) / 2,
                min_y + (max_y - min_y) / 2,
                label,
                color="black",
                fontsize=7,
                ha="center",
                va="center",
            )

        for facade in data.get("facades", []):
            geom = facade.get("geometry", [])
            if len(geom) >= 2:
                fx = [geom[0][0], geom[1][0]]
                fy = [geom[0][1], geom[1][1]]
                ax.plot(fx, fy, color="blue", linewidth=4, zorder=5)

        for circ in data.get("circulation", []):
            geom = circ.get("geometry", [])
            if len(geom) >= 2:
                cx = [geom[0][0], geom[1][0]]
                cy = [geom[0][1], geom[1][1]]
                ax.plot(cx, cy, color="green", linewidth=4, zorder=6)
                ax.text(
                    np.mean(cx),
                    np.mean(cy),
                    "ENTRANCE",
                    color="white",
                    fontsize=6,
                    ha="center",
                    va="center",
                    bbox=dict(facecolor="green", edgecolor="none", pad=0.3, boxstyle="round,pad=0.3"),
                    zorder=7,
                )

        for door in data.get("doors", []):
            geom = door.get("geometry", [])
            if len(geom) >= 1:
                dx, dy = geom[0][0], geom[0][1]
                ax.plot(dx, dy, marker="o", markersize=6, color="yellow", markeredgecolor="black", zorder=8)

        out_path = os.path.join(out_dir, json_file.replace(".json", ".png"))
        plt.savefig(out_path, format="png", bbox_inches="tight")
        plt.close(fig)

    print(f"Finished rendering No_Balcony with area labels! Images saved in {out_dir}")


if __name__ == "__main__":
    draw_no_balcony_with_area()
