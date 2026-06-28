"""Revit-compatible IFC exporter — writes a real IFC4 file with an IfcSite (the
confirmed boundary), an IfcBuilding, one IfcBuildingStorey per floor, and the
selected building as an extruded IfcBuildingElementProxy solid, with score / FAR /
metadata as property sets.

This is **Revit-compatible IFC**, not a native .rvt — Revit imports IFC.
Built with ifcopenshell using a minimal hand-rolled IFC4 model so it works across
ifcopenshell versions without depending on the higher-level api surface.
"""
from __future__ import annotations

import time
from typing import Any

import ifcopenshell
import ifcopenshell.guid


def _ring_xy(boundary: list[list[float]]) -> list[tuple[float, float]]:
    pts = [(float(p[0]), float(p[1])) for p in boundary if len(p) >= 2]
    # IFC polyline profile must be closed but NOT repeat the first point as last.
    if len(pts) >= 2 and pts[0] == pts[-1]:
        pts = pts[:-1]
    return pts


def build_ifc(
    *,
    site_boundary: list[list[float]],
    building_boundary: list[list[float]],
    height_m: float = 12.0,
    floors: int = 1,
    metadata: dict[str, Any] | None = None,
) -> ifcopenshell.file:
    metadata = metadata or {}
    f = ifcopenshell.file(schema="IFC4")

    def guid() -> str:
        return ifcopenshell.guid.new()  # already an IFC-compressed GUID string

    # --- Units (meters) ---
    length_unit = f.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE")
    unit_assignment = f.create_entity("IfcUnitAssignment", Units=[length_unit])

    # --- Geometric context ---
    origin = f.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))
    axis_z = f.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    axis_x = f.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))
    world_placement = f.create_entity("IfcAxis2Placement3D", Location=origin, Axis=axis_z, RefDirection=axis_x)
    context = f.create_entity(
        "IfcGeometricRepresentationContext",
        ContextType="Model",
        CoordinateSpaceDimension=3,
        Precision=1e-5,
        WorldCoordinateSystem=world_placement,
        TrueNorth=f.create_entity("IfcDirection", DirectionRatios=(0.0, 1.0, 0.0)),
    )
    body_context = f.create_entity(
        "IfcGeometricRepresentationSubContext",
        ContextIdentifier="Body",
        ContextType="Model",
        ParentContext=context,
        TargetView="MODEL_VIEW",
    )

    def local_placement(rel_to=None):
        a2p = f.create_entity("IfcAxis2Placement3D", Location=origin, Axis=axis_z, RefDirection=axis_x)
        return f.create_entity("IfcLocalPlacement", PlacementRelTo=rel_to, RelativePlacement=a2p)

    # --- Owner history (minimal) ---
    person = f.create_entity("IfcPerson", FamilyName="TerraPilot")
    org = f.create_entity("IfcOrganization", Name="TerraPilot")
    person_org = f.create_entity("IfcPersonAndOrganization", ThePerson=person, TheOrganization=org)
    app = f.create_entity("IfcApplication", ApplicationDeveloper=org,
                          Version="1.0", ApplicationFullName="TerraPilot", ApplicationIdentifier="TerraPilot")
    owner_history = f.create_entity(
        "IfcOwnerHistory", OwningUser=person_org, OwningApplication=app,
        ChangeAction="ADDED", CreationDate=int(time.time()),
    )

    # --- Project → Site → Building → Storeys spatial tree ---
    project = f.create_entity(
        "IfcProject", GlobalId=guid(), OwnerHistory=owner_history,
        Name=str(metadata.get("project_name", "TerraPilot Project")),
        UnitsInContext=unit_assignment, RepresentationContexts=[context],
    )
    site = f.create_entity("IfcSite", GlobalId=guid(), OwnerHistory=owner_history,
                           Name="Confirmed Site", ObjectPlacement=local_placement(),
                           CompositionType="ELEMENT")
    building = f.create_entity("IfcBuilding", GlobalId=guid(), OwnerHistory=owner_history,
                              Name=str(metadata.get("option_id", "Selected Building")),
                              ObjectPlacement=local_placement(site.ObjectPlacement), CompositionType="ELEMENT")

    floors = max(1, int(floors or 1))
    storey_h = float(height_m or 12.0) / floors
    storeys = []
    for i in range(floors):
        st = f.create_entity("IfcBuildingStorey", GlobalId=guid(), OwnerHistory=owner_history,
                             Name=f"Level {i + 1}", ObjectPlacement=local_placement(building.ObjectPlacement),
                             CompositionType="ELEMENT", Elevation=round(i * storey_h, 4))
        storeys.append(st)

    f.create_entity("IfcRelAggregates", GlobalId=guid(), OwnerHistory=owner_history,
                    RelatingObject=project, RelatedObjects=[site])
    f.create_entity("IfcRelAggregates", GlobalId=guid(), OwnerHistory=owner_history,
                    RelatingObject=site, RelatedObjects=[building])
    f.create_entity("IfcRelAggregates", GlobalId=guid(), OwnerHistory=owner_history,
                    RelatingObject=building, RelatedObjects=storeys)

    # --- Selected building as an extruded solid ---
    def extruded_profile(boundary, depth, name):
        ring = _ring_xy(boundary)
        if len(ring) < 3:
            return None
        ifc_pts = [f.create_entity("IfcCartesianPoint", Coordinates=(x, y)) for x, y in ring]
        ifc_pts.append(ifc_pts[0])  # close
        polyline = f.create_entity("IfcPolyline", Points=ifc_pts)
        profile = f.create_entity("IfcArbitraryClosedProfileDef", ProfileType="AREA",
                                  ProfileName=name, OuterCurve=polyline)
        extrude_dir = f.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
        position = f.create_entity("IfcAxis2Placement3D", Location=origin, Axis=axis_z, RefDirection=axis_x)
        solid = f.create_entity("IfcExtrudedAreaSolid", SweptArea=profile, Position=position,
                                ExtrudedDirection=extrude_dir, Depth=float(depth))
        shape_rep = f.create_entity("IfcShapeRepresentation", ContextOfItems=body_context,
                                    RepresentationIdentifier="Body", RepresentationType="SweptSolid",
                                    Items=[solid])
        return f.create_entity("IfcProductDefinitionShape", Representations=[shape_rep])

    product_shape = extruded_profile(building_boundary, height_m or 12.0, "BuildingFootprint")
    proxy = f.create_entity(
        "IfcBuildingElementProxy", GlobalId=guid(), OwnerHistory=owner_history,
        Name=f"Building {metadata.get('option_id', '')}".strip(),
        ObjectPlacement=local_placement(storeys[0].ObjectPlacement),
        Representation=product_shape,
    )
    f.create_entity("IfcRelContainedInSpatialStructure", GlobalId=guid(), OwnerHistory=owner_history,
                    RelatingStructure=storeys[0], RelatedElements=[proxy])

    # --- Site footprint as a curve annotation on the site ---
    site_shape = extruded_profile(site_boundary, 0.05, "SiteBoundary")
    if site_shape is not None:
        site_proxy = f.create_entity("IfcBuildingElementProxy", GlobalId=guid(), OwnerHistory=owner_history,
                                     Name="Site Boundary",
                                     ObjectPlacement=local_placement(site.ObjectPlacement),
                                     Representation=site_shape)
        f.create_entity("IfcRelContainedInSpatialStructure", GlobalId=guid(), OwnerHistory=owner_history,
                        RelatingStructure=site, RelatedElements=[site_proxy])

    # --- Metadata property set on the building proxy ---
    def prop(name, value):
        return f.create_entity("IfcPropertySingleValue", Name=name,
                               NominalValue=f.create_entity("IfcText", str(value)))
    pset = f.create_entity("IfcPropertySet", GlobalId=guid(), OwnerHistory=owner_history,
                           Name="TerraPilot_Metadata",
                           HasProperties=[
                               prop("OptionID", metadata.get("option_id", "")),
                               prop("Score", metadata.get("score", "")),
                               prop("HeightM", height_m),
                               prop("Floors", floors),
                               prop("FootprintAreaSqm", metadata.get("footprint_area", "")),
                               prop("FAR", metadata.get("far", "")),
                               prop("BuildingUse", metadata.get("building_use", "")),
                           ])
    f.create_entity("IfcRelDefinesByProperties", GlobalId=guid(), OwnerHistory=owner_history,
                    RelatedObjects=[proxy], RelatingPropertyDefinition=pset)

    return f


def export_ifc_bytes(**kwargs: Any) -> bytes:
    model = build_ifc(**kwargs)
    return model.to_string().encode("utf-8")
