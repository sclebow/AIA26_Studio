from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from _runtime.config import load_settings
from _runtime.mcp_client import McpClient
from _runtime.llm import create_chat_llm, get_llm_response_format
from dotenv import load_dotenv


@dataclass
class Context:
    """Everything the agent graph needs to run — passed from main.py into graph.py."""
    llm: Any
    mcp_client: McpClient
    tools: list[dict[str, Any]]
    layout_data: dict[str, Any]
    max_iterations: int
    edited_layout_path: Path
    cost_db: dict[str, Any]


def bootstrap() -> Context:
    """Load settings, connect to the MCP server, discover tools, and build the LLM.

    Call this once from main.py and pass the returned Context into run_agent().
    """
    settings = load_settings()

    # Read the layout schema that will be given to the agent as context (team_05-specific)
    repo_root = Path(__file__).resolve().parents[3]
    layout_path = repo_root / "layout_input" / "layout_schema.json"
    layout_data: dict[str, Any] = json.loads(layout_path.read_text(encoding="utf-8"))

    # Connect to the Grasshopper MCP server and list available tools
    mcp_client = McpClient(settings.mcp_endpoint, settings.request_timeout_seconds)
    mcp_client.initialize()
    tools = mcp_client.list_tools()

    # Register virtual (locally-handled) tools.
    # compute_slab_cost: per-m3 slab pricing (area * thickness * rate). Rate is
    # resolved from cost_rates.json (room_finishes.slab_material), with a fallback
    # to OnlineCostFetcher when the material is unknown.
    tools.append({
        "name": "compute_slab_cost",
        "description": (
            "Compute the cost of a slab for a room using a per-cubic-metre rate. "
            "cost = area_m2 * thickness_m * rate_per_m3. The rate is looked up from "
            "the slab_material table in cost_rates.json by `material` "
            "(e.g. post_tensioned, rc_solid, timber_joist). Use this tool whenever "
            "the user mentions a slab thickness or asks for slab cost. "
            "Provide `room_name` and `thickness_m` and `material`. `area_m2` is "
            "optional - omit it to use the room's area from the layout."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "room_name": {"type": "string"},
                "thickness_m": {"type": "number"},
                "material": {"type": "string"},
                "area_m2": {"type": "number"},
            },
            "required": ["room_name", "thickness_m", "material"],
        },
    })

    # compute_finish_cost: per-m2 finish pricing for floor, wall, or ceiling.
    # Looks up the rate from cost_rates.json[room_finishes][<surface>_finish or
    # ceiling_material] by material. Computes surface area from the layout
    # (floor/ceiling = room.area_m2; wall = perimeter * height_m).
    tools.append({
        "name": "compute_finish_cost",
        "description": (
            "Compute the cost of a floor, wall, or ceiling finish for a room "
            "using a per-square-metre rate. cost = surface_area_m2 * rate_per_m2. "
            "Rate is looked up from cost_rates.json room_finishes by `surface` "
            "(`floor`, `wall`, or `ceiling`) and `material` "
            "(e.g. gypsum_paint, porcelain_tile, marble, wood_panel). "
            "Use this whenever the user asks for the cost of a floor/wall/ceiling "
            "material or finish in a room. Provide `room_name`, `surface`, and "
            "`material`. For walls, `height_m` is optional (defaults to 3.0 m); "
            "wall area is computed from the room polygon perimeter * height. "
            "`area_m2` is optional - omit it to compute from the layout."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "room_name": {"type": "string"},
                "surface": {"type": "string", "enum": ["floor", "wall", "ceiling"]},
                "material": {"type": "string"},
                "height_m": {"type": "number"},
                "area_m2": {"type": "number"},
            },
            "required": ["room_name", "surface", "material"],
        },
    })

    tools.append({
        "name": "get_unit_cost_by_type",
        "description": (
            "Get the unit cost (USD) for a building element type such as door, window, or column. "
            "Looks up lump-sum rates from the cost database by element type and optional subtype. "
            "Provide `element_type` (e.g. 'door', 'window', 'column') and optionally `subtype` "
            "(e.g. 'interior_standard', 'exterior_entrance', 'solid_wood', 'curtain_wall')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "element_type": {"type": "string"},
                "subtype": {"type": "string"},
            },
            "required": ["element_type"],
        },
    })

    tools.append({
        "name": "get_count_by_type",
        "description": (
            "Count the number of discrete elements of a given type in the layout. "
            "Use for doors, windows, rooms, columns, or any countable element. "
            "Provide `element_type` (e.g. 'door', 'window', 'room', 'column')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "element_type": {"type": "string"},
            },
            "required": ["element_type"],
        },
    })

    tools.append({
        "name": "get_area_by_type",
        "description": (
            "Get the total area (m²) of all elements of a given type in the layout. "
            "Use for floors, ceilings, facade panels, or any planar element. "
            "Provide `element_type` (e.g. 'floor', 'ceiling', 'facade')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "element_type": {"type": "string"},
            },
            "required": ["element_type"],
        },
    })

    print(f"Discovered MCP tools: {[t.get('name') for t in tools]}")

   # Using SupaBase + FRED for cost database - no JSON file needed
    cost_db: dict[str, Any] = {}
    print("[bootstrap] ✓ Using SupaBase + FRED - auto-updated market database")

    # Build the LLM with a structured-output schema tailored to the available tools
    llm = create_chat_llm(
        api_key=settings.api_key,
        base_url=settings.base_url,
        llm_model=settings.llm_model,
        timeout_seconds=settings.request_timeout_seconds,
        #model_kwargs=get_llm_response_format(tools),
    )

    team_dir = Path(__file__).resolve().parents[2]
    team_name = team_dir.name
    edited_layout_path = team_dir / f"{team_name}_edited_layout.json"

    return Context(
        llm=llm,
        mcp_client=mcp_client,
        tools=tools,
        layout_data=layout_data,
        max_iterations=settings.max_iterations,
        edited_layout_path=edited_layout_path,
        cost_db=cost_db,
    )