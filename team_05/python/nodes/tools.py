import json
import requests
from pathlib import Path
from typing import Any
from _runtime.llm import write_tool_result

import os
from dotenv import load_dotenv

load_dotenv()

# Import database modules
from opencost_database import get_opencost_db
from google_sheets_db import get_sheets_db as get_google_sheets_db

# ---------------------------------------------------------------------------
# Load cost database from JSON file
# ---------------------------------------------------------------------------

def load_cost_database() -> dict:
    """Load cost_database.json from the project."""
    # Try multiple locations
    possible_paths = [
        Path(__file__).resolve().parents[3] / "cost_database.json",  # repo root
        Path(__file__).resolve().parent.parent.parent / "cost_database.json",
        Path.cwd() / "cost_database.json",
    ]
    
    for path in possible_paths:
        if path.exists():
            with open(path, 'r') as f:
                print(f"[cost_db] Loaded from {path}")
                return json.load(f)
    
    print("[cost_db] Warning: cost_database.json not found")
    return {}


# ---------------------------------------------------------------------------
# Tool node — executes MCP tool calls requested by the reason node.
# ---------------------------------------------------------------------------

    # Load cost database if not provided
    if cost_db is None:
        cost_db = load_cost_database()

# Initialize databases
USE_OPENCOST = os.getenv("USE_OPENCOST", "true").lower() == "true"
SHEET_ID = os.getenv("GOOGLE_SHEET_ID")

# Choose database: OpenCost (auto-updated) or Google Sheets
if USE_OPENCOST:
    print("[Database] Using OpenCost - Auto-updated market prices")
    sheets_db = get_opencost_db()
else:
    print("[Database] Using Google Sheets")
    sheets_db = get_google_sheets_db(SHEET_ID) if SHEET_ID else None

print("[Setup] Database initialized successfully")


def build_tool_node(mcp_client, allowed_tools, edited_layout_path, erp_config: dict = None):
    """Build tool node for LangGraph workflow"""

    allowed_names = {t["name"] for t in allowed_tools if t.get("name")}

    def tool_node(state):
        for call in state["pending_tool_calls"]:
            state["iteration"] += 1
            if state["iteration"] > state["max_iterations"]:
                raise RuntimeError("Max iterations exceeded")

            tool_name = call["name"]
            if tool_name not in allowed_names:
                raise RuntimeError(f"Tool '{tool_name}' is not in the allowed tools list")
            
            print(f"Calling tool: {tool_name} with arguments: {call['arguments']}")
            
            tool_args = {k: v for k, v in call["arguments"].items() if v is not None}
            if "layout_json" in tool_args:
                tool_args["layout_json"] = state["layout_json_string"]

            # ── LOCAL TOOLS (using cost_db) ─────────────────────────────────

            # Tool: get_unit_cost_by_type
            if tool_name == "get_unit_cost_by_type" and cost_db:
                element_type = str(tool_args.get("element_type", "")).lower().replace(" ", "_")
                cost = cost_db.get(element_type)
                tool_output = json.dumps(
                    {"element_type": element_type, "unit_cost": cost, "currency": "EUR"}
                    if cost is not None
                    else {"error": f"No cost data for '{element_type}'", "known_types": list(cost_db.keys())}
                )
            
            # Tool: get_door_cost
            elif tool_name == "get_door_cost" and cost_db:
                door_id = tool_args.get("door_id", "unknown")
                door_type = tool_args.get("door_type", "wooden_door").lower().replace(" ", "_")
                quantity = tool_args.get("quantity", 1)
                
                unit_cost = cost_db.get(door_type)
                if unit_cost is None:
                    tool_output = json.dumps({
                        "error": f"Door type '{door_type}' not found",
                        "available_doors": [k for k in cost_db.keys() if "door" in k]
                    })
                else:
                    total_cost = quantity * unit_cost
                    tool_output = json.dumps({
                        "door_id": door_id,
                        "door_type": door_type,
                        "quantity": quantity,
                        "unit_cost": unit_cost,
                        "total_cost": total_cost,
                        "currency": "EUR"
                    })
            
            # Tool: get_window_cost
            elif tool_name == "get_window_cost" and cost_db:
                window_id = tool_args.get("window_id", "unknown")
                quantity = tool_args.get("quantity", 1)
                
                unit_cost = cost_db.get("window")
                if unit_cost is None:
                    tool_output = json.dumps({"error": "Window cost not found in database"})
                else:
                    total_cost = quantity * unit_cost
                    tool_output = json.dumps({
                        "window_id": window_id,
                        "quantity": quantity,
                        "unit_cost": unit_cost,
                        "total_cost": total_cost,
                        "currency": "EUR"
                    })
            
            # Tool: get_wall_cost
            elif tool_name == "get_wall_cost" and cost_db:
                wall_id = tool_args.get("wall_id", "unknown")
                area = tool_args.get("area", 0)
                wall_type = tool_args.get("wall_type", "brick_wall").lower().replace(" ", "_")
                
                cost_per_m2 = cost_db.get(wall_type)
                if cost_per_m2 is None:
                    tool_output = json.dumps({
                        "error": f"Wall type '{wall_type}' not found",
                        "available_walls": [k for k in cost_db.keys() if "wall" in k]
                    })
                else:
                    total_cost = area * cost_per_m2
                    tool_output = json.dumps({
                        "wall_id": wall_id,
                        "wall_type": wall_type,
                        "area": area,
                        "cost_per_m2": cost_per_m2,
                        "total_cost": total_cost,
                        "currency": "EUR"
                    })
            
            # Tool: get_flooring_cost
            elif tool_name == "get_flooring_cost" and cost_db:
                room_id = tool_args.get("room_id", "unknown")
                area = tool_args.get("area", 0)
                material = tool_args.get("material", "floor_tiles").lower().replace(" ", "_")
                
                cost_per_m2 = cost_db.get(material)
                if cost_per_m2 is None:
                    tool_output = json.dumps({
                        "error": f"Material '{material}' not found",
                        "available_flooring": [k for k in cost_db.keys() if "floor" in k or "tile" in k or "carpet" in k]
                    })
                else:
                    total_cost = area * cost_per_m2
                    tool_output = json.dumps({
                        "room_id": room_id,
                        "material": material,
                        "area": area,
                        "cost_per_m2": cost_per_m2,
                        "total_cost": total_cost,
                        "currency": "EUR"
                    })
            
            # Tool: get_ceiling_cost
            elif tool_name == "get_ceiling_cost" and cost_db:
                room_id = tool_args.get("room_id", "unknown")
                area = tool_args.get("area", 0)
                
                cost_per_m2 = cost_db.get("ceiling")
                if cost_per_m2 is None:
                    tool_output = json.dumps({"error": "Ceiling cost not found in database"})
                else:
                    total_cost = area * cost_per_m2
                    tool_output = json.dumps({
                        "room_id": room_id,
                        "area": area,
                        "cost_per_m2": cost_per_m2,
                        "total_cost": total_cost,
                        "currency": "EUR"
                    })
            
            # Tool: get_facade_cost
            elif tool_name == "get_facade_cost" and cost_db:
                facade_id = tool_args.get("facade_id", "unknown")
                area = tool_args.get("area", 0)
                facade_type = tool_args.get("facade_type", "glass_facade").lower().replace(" ", "_")
                
                cost_per_m2 = cost_db.get(facade_type)
                if cost_per_m2 is None:
                    tool_output = json.dumps({
                        "error": f"Facade type '{facade_type}' not found",
                        "available_facades": [k for k in cost_db.keys() if "facade" in k]
                    })
                else:
                    total_cost = area * cost_per_m2
                    tool_output = json.dumps({
                        "facade_id": facade_id,
                        "facade_type": facade_type,
                        "area": area,
                        "cost_per_m2": cost_per_m2,
                        "total_cost": total_cost,
                        "currency": "EUR"
                    })
            
            # Tool: estimate_total_building_cost
            elif tool_name == "estimate_total_building_cost" and cost_db:
                components = tool_args.get("components", {})
                # components = {"wooden_door": 2, "window": 5, "floor_tiles": 100, ...}
                
                total_cost = 0
                breakdown = {}
                
                for item_name, quantity in components.items():
                    item_key = item_name.lower().replace(" ", "_")
                    unit_cost = cost_db.get(item_key)
                    
                    if unit_cost is None:
                        continue  # Skip if not found
                    
                    item_total = quantity * unit_cost
                    total_cost += item_total
                    breakdown[item_name] = {
                        "quantity": quantity,
                        "unit_cost": unit_cost,
                        "subtotal": item_total
                    }
                
                tool_output = json.dumps({
                    "breakdown": breakdown,
                    "total_cost": total_cost,
                    "item_count": len(breakdown),
                    "currency": "EUR"
                })
            
            # Tool: compare_wall_types
            elif tool_name == "compare_wall_types" and cost_db:
                area = tool_args.get("area", 0)
                
                brick_cost = cost_db.get("brick_wall", 0)
                concrete_cost = cost_db.get("concrete_wall", 0)
                
                brick_total = area * brick_cost
                concrete_total = area * concrete_cost
                
                difference = abs(brick_total - concrete_total)
                cheaper = "brick_wall" if brick_total < concrete_total else "concrete_wall"
                
                tool_output = json.dumps({
                    "area": area,
                    "brick_wall": {
                        "cost_per_m2": brick_cost,
                        "total_cost": brick_total
                    },
                    "concrete_wall": {
                        "cost_per_m2": concrete_cost,
                        "total_cost": concrete_total
                    },
                    "cheaper_option": cheaper,
                    "cost_difference": difference,
                    "currency": "EUR"
                })
            
            # ── MCP TOOLS (call Grasshopper) ────────────────────────────────
            # ========== GOOGLE SHEETS / OPENCOST COST TOOLS ==========

            # Tool: get_door_cost_05
            if tool_name == "get_door_cost_05" and sheets_db:
                door_type = tool_args.get("door_type", "Wooden Door")
                quantity = tool_args.get("quantity", 1)
                
                try:
                    unit_cost = sheets_db.get_cost(door_type)
                    
                    if unit_cost is None:
                        all_items = sheets_db.get_all_data()
                        tool_output = json.dumps({
                            "error": f"'{door_type}' not found in database",
                            "available_items": list(all_items.keys()) if all_items else []
                        })
                    else:
                        total = quantity * unit_cost
                        tool_output = json.dumps({
                            "door_type": door_type,
                            "quantity": quantity,
                            "unit_cost": unit_cost,
                            "total_cost": total,
                            "currency": "EUR",
                            "source": "opencost" if USE_OPENCOST else "google_sheets"
                        })
                except Exception as e:
                    tool_output = json.dumps({"error": str(e)})

            # Tool: get_window_cost_05
            elif tool_name == "get_window_cost_05" and sheets_db:
                quantity = tool_args.get("quantity", 1)
                
                try:
                    unit_cost = sheets_db.get_cost("Window")
                    
                    if unit_cost is None:
                        tool_output = json.dumps({"error": "Window cost not found"})
                    else:
                        total = quantity * unit_cost
                        tool_output = json.dumps({
                            "quantity": quantity,
                            "unit_cost": unit_cost,
                            "total_cost": total,
                            "currency": "EUR",
                            "source": "opencost" if USE_OPENCOST else "google_sheets"
                        })
                except Exception as e:
                    tool_output = json.dumps({"error": str(e)})

            # Tool: get_wall_cost_05
            elif tool_name == "get_wall_cost_05" and sheets_db:
                wall_type = tool_args.get("wall_type", "Brick Wall")
                area = tool_args.get("area", 0)
                
                try:
                    cost_per_m2 = sheets_db.get_cost(wall_type)
                    
                    if cost_per_m2 is None:
                        tool_output = json.dumps({
                            "error": f"'{wall_type}' not found"
                        })
                    else:
                        total = area * cost_per_m2
                        tool_output = json.dumps({
                            "wall_type": wall_type,
                            "area": area,
                            "cost_per_m2": cost_per_m2,
                            "total_cost": total,
                            "currency": "EUR",
                            "source": "opencost" if USE_OPENCOST else "google_sheets"
                        })
                except Exception as e:
                    tool_output = json.dumps({"error": str(e)})

            # Tool: get_flooring_cost_05
            elif tool_name == "get_flooring_cost_05" and sheets_db:
                material = tool_args.get("material", "Floor Tiles")
                area = tool_args.get("area", 0)
                
                try:
                    cost_per_m2 = sheets_db.get_cost(material)
                    
                    if cost_per_m2 is None:
                        tool_output = json.dumps({
                            "error": f"'{material}' not found"
                        })
                    else:
                        total = area * cost_per_m2
                        tool_output = json.dumps({
                            "material": material,
                            "area": area,
                            "cost_per_m2": cost_per_m2,
                            "total_cost": total,
                            "currency": "EUR",
                            "source": "opencost" if USE_OPENCOST else "google_sheets"
                        })
                except Exception as e:
                    tool_output = json.dumps({"error": str(e)})

            # Tool: get_facade_cost_05
            elif tool_name == "get_facade_cost_05" and sheets_db:
                facade_type = tool_args.get("facade_type", "Glass Facade")
                area = tool_args.get("area", 0)
                
                try:
                    cost_per_m2 = sheets_db.get_cost(facade_type)
                    
                    if cost_per_m2 is None:
                        tool_output = json.dumps({"error": f"'{facade_type}' not found"})
                    else:
                        total = area * cost_per_m2
                        tool_output = json.dumps({
                            "facade_type": facade_type,
                            "area": area,
                            "cost_per_m2": cost_per_m2,
                            "total_cost": total,
                            "currency": "EUR",
                            "source": "opencost" if USE_OPENCOST else "google_sheets"
                        })
                except Exception as e:
                    tool_output = json.dumps({"error": str(e)})

            # Tool: get_ceiling_cost_05
            elif tool_name == "get_ceiling_cost_05" and sheets_db:
                area = tool_args.get("area", 0)
                
                try:
                    cost_per_m2 = sheets_db.get_cost("Ceiling")
                    
                    if cost_per_m2 is None:
                        tool_output = json.dumps({"error": "Ceiling cost not found"})
                    else:
                        total = area * cost_per_m2
                        tool_output = json.dumps({
                            "area": area,
                            "cost_per_m2": cost_per_m2,
                            "total_cost": total,
                            "currency": "EUR",
                            "source": "opencost" if USE_OPENCOST else "google_sheets"
                        })
                except Exception as e:
                    tool_output = json.dumps({"error": str(e)})

            # Tool: estimate_total_building_cost_05
            elif tool_name == "estimate_total_building_cost_05" and sheets_db:
                components = tool_args.get("components", {})
                
                try:
                    total_cost = 0
                    breakdown = {}
                    
                    for item_name, quantity in components.items():
                        unit_cost = sheets_db.get_cost(item_name)
                        if unit_cost:
                            item_total = quantity * unit_cost
                            total_cost += item_total
                            breakdown[item_name] = {
                                "quantity": quantity,
                                "unit_cost": unit_cost,
                                "subtotal": item_total
                            }
                    
                    tool_output = json.dumps({
                        "breakdown": breakdown,
                        "total_cost": total_cost,
                        "item_count": len(breakdown),
                        "currency": "EUR",
                        "source": "opencost" if USE_OPENCOST else "google_sheets"
                    })
                except Exception as e:
                    tool_output = json.dumps({"error": str(e)})

            # Tool: compare_wall_types_05
            elif tool_name == "compare_wall_types_05" and sheets_db:
                area = tool_args.get("area", 0)
                
                try:
                    brick_cost = sheets_db.get_cost("Brick Wall")
                    concrete_cost = sheets_db.get_cost("Concrete Wall")
                    
                    if brick_cost and concrete_cost:
                        brick_total = area * brick_cost
                        concrete_total = area * concrete_cost
                        difference = abs(brick_total - concrete_total)
                        cheaper = "Brick Wall" if brick_total < concrete_total else "Concrete Wall"
                        
                        tool_output = json.dumps({
                            "area": area,
                            "brick_wall": {
                                "cost_per_m2": brick_cost,
                                "total_cost": brick_total
                            },
                            "concrete_wall": {
                                "cost_per_m2": concrete_cost,
                                "total_cost": concrete_total
                            },
                            "cheaper_option": cheaper,
                            "cost_difference": difference,
                            "currency": "EUR",
                            "source": "opencost" if USE_OPENCOST else "google_sheets"
                        })
                    else:
                        tool_output = json.dumps({"error": "Wall costs not found"})
                except Exception as e:
                    tool_output = json.dumps({"error": str(e)})

            # --- DEFAULT: Call MCP Tools ---
            else:
                tool_output = mcp_client.call_tool(tool_name, tool_args)

            # Standard processing continues...
            write_tool_result(tool_output, edited_layout_path)
            
            try:
                updated = json.loads(tool_output.strip())
                if isinstance(updated, dict):
                    state["layout_json_string"] = json.dumps(updated)
            except:
                pass

            state["messages"].append({
                "role": "assistant",
                "content": json.dumps({
                    "action": "tool",
                    "final_response": "",
                    "tool_calls": [{"name": tool_name, "arguments": tool_args}],
                }),
            })
            state["messages"].append({"role": "user", "content": f"Tool result: {tool_output}"})
            print(f"Tool result: {tool_output}")

        state["pending_tool_calls"] = None
        return state

    return tool_node