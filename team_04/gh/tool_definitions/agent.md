TerraPilot Agent
================

# Description
The TerraPilot Agent is an architectural massing and Grasshopper workflow agent. It handles locked typologies, courtyard-driven optimization, parametric shape generation, and post-generation move/rotate/tree updates. Use it when the prompt needs a shape-aware plan, structured JSON output, or safe handling of null inputs without inventing a default geometry.

# Example Prompts
1. "Create a U-shape building inside this site polygon that maximizes courtyard area, opening facing south."
	- The TerraPilot Agent will route this to the U-shape planning and generation path, then return ranked ShapeOutput JSONs.
2. "Generate a rectangle footprint length=40 m, width=20 m, height=10 m, rotation=15°."
	- The TerraPilot Agent will produce a rectangle massing plan, clamp invalid values if needed, and return shape JSON plus mesh diagnostics.
3. "Move the building 5m right after optimization."
	- The TerraPilot Agent will route this to the manipulation path and pass a move distance token without regenerating a default shape.
4. "Generate an I-shape with connector on and compare it to connector off."
	- The TerraPilot Agent will create both variants, compare geometry output, and flag connector-related differences.
5. "If the input is null, keep the previous Grasshopper result unchanged."
	- The TerraPilot Agent will avoid fallback geometry and return no new mesh when there is no meaningful input.s