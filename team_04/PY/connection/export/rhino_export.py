"""Rhino .3dm exporter — writes a real Rhino file containing the confirmed site
boundary (as a curve) and the selected building as an extruded solid to its
height, with floors/score/metadata attached as document user text.

Uses rhino3dm (pure-Python Rhino I/O) — produces a genuine .3dm openable in Rhino.
"""
from __future__ import annotations

from typing import Any

import rhino3dm as r3


def _closed_ring(boundary: list[list[float]]) -> list[tuple[float, float, float]]:
    pts = [(float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 0.0) for p in boundary if len(p) >= 2]
    if pts and pts[0] != pts[-1]:
        pts.append(pts[0])
    return pts


def _polyline_curve(boundary: list[list[float]], z: float = 0.0):
    pts = _closed_ring(boundary)
    if len(pts) < 4:
        return None
    pl = r3.Polyline()
    for x, y, _z in pts:
        pl.Add(x, y, z)
    return pl.ToPolylineCurve()


def build_3dm(
    *,
    site_boundary: list[list[float]],
    building_boundary: list[list[float]],
    building_holes: list | None = None,
    height_m: float = 12.0,
    metadata: dict[str, Any] | None = None,
) -> r3.File3dm:
    """Build a File3dm with the site curve + extruded building solid + metadata."""
    model = r3.File3dm()
    metadata = metadata or {}
    building_holes = building_holes or []

    # Site boundary as a ground curve.
    site_crv = _polyline_curve(site_boundary, z=0.0)
    if site_crv is not None:
        attrs = r3.ObjectAttributes()
        attrs.Name = "Site Boundary"
        model.Objects.AddCurve(site_crv, attrs)

    # Selected building: extrude the footprint to its height → a real solid. A courtyard
    # is carved as a TRUE void using an Extrusion with an inner profile (NOT a separate
    # floating curve, which read as a disconnected block in Rhino).
    h_val = float(height_m or 12.0)
    bld_crv = _polyline_curve(building_boundary, z=0.0)
    if bld_crv is not None:
        attrs = r3.ObjectAttributes()
        attrs.Name = f"Building {metadata.get('option_id', '')}".strip()
        ext = r3.Extrusion.Create(bld_crv, h_val, True)
        carved = False
        if ext is not None and building_holes:
            for h in building_holes:
                # the inner profile must be CLOSED + planar; Extrusion expects it on the
                # same base plane as the outer profile.
                hc = _polyline_curve(h, z=0.0)
                if hc is None:
                    continue
                try:
                    if ext.AddInnerProfile(hc):
                        carved = True
                except Exception:  # noqa: BLE001
                    pass
        if ext is not None:
            model.Objects.AddExtrusion(ext, attrs)
            # Only if the inner-profile carve FAILED, add the courtyard ring as a labelled
            # curve so the void is at least documented (not a misleading solid block).
            if building_holes and not carved:
                for h in building_holes:
                    hc = _polyline_curve(h, z=0.0)
                    if hc is not None:
                        ha = r3.ObjectAttributes(); ha.Name = "Courtyard outline (carve manually)"
                        model.Objects.AddCurve(hc, ha)
        else:
            model.Objects.AddCurve(bld_crv, attrs)

    # Attach metadata as document strings (Rhino "document user text").
    meta = {
        "option_id": str(metadata.get("option_id", "")),
        "score": str(metadata.get("score", "")),
        "height_m": str(height_m),
        "floors": str(metadata.get("floors", "")),
        "footprint_area_sqm": str(metadata.get("footprint_area", "")),
        "far": str(metadata.get("far", "")),
        "building_use": str(metadata.get("building_use", "")),
        "exported_by": "TerraPilot",
    }
    for k, v in meta.items():
        try:
            model.Strings.SetString(f"TerraPilot.{k}", v)
        except Exception:  # noqa: BLE001
            pass
    return model


def export_3dm_bytes(**kwargs: Any) -> bytes:
    """Return the .3dm file as bytes (for an HTTP download response)."""
    import os
    import tempfile

    model = build_3dm(**kwargs)
    path = os.path.join(tempfile.gettempdir(), "terrapilot_export.3dm")
    if not model.Write(path, 7):
        raise RuntimeError("Failed to write .3dm file")
    with open(path, "rb") as fh:
        data = fh.read()
    try:
        os.remove(path)
    except OSError:
        pass
    return data
