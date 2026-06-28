"""Real geometry exporters for the final selected option (Rhino .3dm + IFC).

Lives in the live connection backend (one backend). Each exporter takes the
confirmed site boundary + the selected building option and writes a real file:
  rhino_export  -> .3dm via rhino3dm (site curve + extruded building solid)
  ifc_export    -> .ifc via ifcopenshell (IfcSite + IfcBuilding + storeys)
"""
from __future__ import annotations

from .. import _TEAM_ROOT  # noqa: F401  (side-effect import — sys.path)
