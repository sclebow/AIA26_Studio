Spatial Flow Agent
==================

# Description
The Spatial Flow Agent optimizes industrial floor plan layouts by intelligently placing and analyzing equipment in factories, workshops, warehouses, assembly halls, and clean rooms. It uses OSHA, NFPA, and ISO standards to evaluate collision clearances, path efficiency, visibility, reachability, and equipment orientation. The agent builds a spatial relationship graph connecting all objects, walls, windows, and doors ; then uses this graph to reason about workflow logic, proximity constraints, and industrial standards when placing or relocating equipment. It accepts natural language spatial descriptions, resolves complex multi-object dependencies, and iteratively adjusts placements using exact move vectors until the layout meets industrial safety and ergonomic standards.

# Layouts referenced by the examples
- `industrial_005` — **the only pre-populated layout**: a *Clean Room* (Assembly Station 1, Packaging Stations 2-4, Conveyor Sections 5/8/10, Labeling Station 6, Parts Bin Racks 7/9/11, QC Table 12) plus a *Bathroom* (Toilet, Sink). Use it for move/reorganize examples.
- `industrial_02` — **empty**: Assembly Hall, Quality Control Room, Loading Bay, Offices, Break Room, Restroom. Use it for populate examples.
- `industrial_03` — **empty**: Distribution Floor, Receiving/Shipping/Packaging Areas, Offices, Meeting Room, Utility Room, Restrooms. Use it for warehouse/forklift examples.

> Run each example from `team_03/python`. `industrial_01/02/03` start empty, so "move/reorganize existing equipment" prompts only apply to `industrial_005`.

# Example Prompts

1. Reorganize congestion / circulation flow
   ```
   python main.py --layout industrial_005 "The Clean Room is too congested. Conveyor Sections 5, 8 and 10 and the Packaging Stations are blocking circulation. Reorganize them so workers can move freely between Assembly Station 1 and QC Table 12 without crossing paths."
   ```
   - The Spatial Flow Agent reads the spatial relationship graph to find which conveyors and packaging stations have `near` edges to the main circulation corridor. It evaluates path-efficiency scores between Assembly Station 1 and QC Table 12, identifies the specific objects causing blockages, emits `move_object` calls to relocate them while preserving the production-flow sequence and opening a minimum 1.2m OSHA-compliant corridor, then re-runs collision, path, and reachability analysis to confirm every station stays reachable and visible.

2. Move an object and its dependent cluster
   ```
   python main.py --layout industrial_005 "Conveyor Section 10 is too close to the north wall and maintenance workers can't reach the rear. Move it and everything that depends on it to a better spot in the Clean Room."
   ```
   - The Spatial Flow Agent reads the spatial graph to find objects with `near` edges to Conveyor Section 10 (e.g. QC Table 12, 2.82m away). It switches to the maintenance_worker profile, calculates a new zone with adequate rear clearance, relocates Conveyor Section 10 and its dependent cluster keeping their relative positions and workflow sequence, then runs full collision, path, and reachability analysis to confirm the new configuration is compliant.

3. Forklift-friendly layout in an (empty) warehouse
   ```
   python main.py --layout industrial_03 "This distribution floor is empty. Set up a forklift-friendly layout: place racks and stations on the Distribution Floor keeping 3.05m forklift aisles while staying accessible to standard workers."
   ```
   - The Spatial Flow Agent switches to the forklift movement profile (3.05m corridor, 2.5m turning radius per ANSI B56.1), divides the Distribution Floor into functional zones, and places racks and stations so the layout satisfies the forklift profile while remaining accessible to the standard worker profile. It runs a full reachability and path analysis after placement and reports the trade-offs if any constraint between the two profiles cannot be resolved.

4. Targeted quality-control station placement
   ```
   python main.py --layout industrial_005 "Add a new quality control station in the Clean Room with good visibility of the Packaging Stations, close to Labeling Station 6, and not blocking the door to the Bathroom."
   ```
   - The Spatial Flow Agent reasons over the spatial graph to find a position that satisfies all three constraints simultaneously — visibility edges to the Packaging Stations, a `near` edge to Labeling Station 6 within 3m, and no overlap with the door clearance zone of the Bathroom. It computes isovist visibility polygons at standing height (1.55m) to verify sightlines, places the QC station with the correct ergonomic height, and runs the full analysis pipeline to confirm compliance.

5. Populate an empty layout
   ```
   python main.py --layout industrial_02 "This layout is empty. Set up a standard production line in the Assembly Hall for electronic assembly, with material flow from the Loading Bay to shipping."
   ```
   - The Spatial Flow Agent analyzes the room geometry and door positions to identify the material-flow axis from the Loading Bay. It selects equipment from the industrial knowledge base appropriate for electronic assembly (ESD-safe workstations, controlled conveyors, inspection stations), divides the Assembly Hall into functional zones (receiving, assembly, QC, packaging, dispatch), places all equipment in workflow sequence maintaining OSHA clearances, and runs full spatial analysis after each placement to ensure the complete layout is compliant before presenting the result.
