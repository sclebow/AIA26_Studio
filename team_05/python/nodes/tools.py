import json
import requests
from pathlib import Path
from typing import Any
from _runtime.llm import write_tool_result

import os
from dotenv import load_dotenv
from google_sheets_db import get_sheets_db

# Load environment variables
load_dotenv()

# Get Sheet ID from .env file
SHEET_ID = os.getenv("GOOGLE_SHEET_ID")

if SHEET_ID:
    print(f"[Google Sheets] Sheet ID loaded: {SHEET_ID}")
else:
    print("[Google Sheets] Warning: GOOGLE_SHEET_ID not found in .env")

# Initialize the Google Sheets database
sheets_db = get_sheets_db(SHEET_ID) if SHEET_ID else None

def build_tool_node(mcp_client, allowed_tools, edited_layout_path, erp_config: dict = None):
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

            # ========== GOOGLE SHEETS COST TOOLS ==========

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
                            "available_items": list(all_items.keys())
                        })
                    else:
                        total = quantity * unit_cost
                        tool_output = json.dumps({
                            "door_type": door_type,
                            "quantity": quantity,
                            "unit_cost": unit_cost,
                            "total_cost": total,
                            "currency": "EUR",
                            "source": "google_sheets"
                        })
                except Exception as e:
                    tool_output = json.dumps({"error": str(e)})

            # Tool: get_window_cost_05
            elif tool_name == "get_window_cost_05" and sheets_db:
                quantity = tool_args.get("quantity", 1)
                
                try:
                    unit_cost = sheets_db.get_cost("Window")
                    
                    if unit_cost is None:
                        tool_output = json.dumps({"error": "Window cost not found in database"})
                    else:
                        total = quantity * unit_cost
                        tool_output = json.dumps({
                            "quantity": quantity,
                            "unit_cost": unit_cost,
                            "total_cost": total,
                            "currency": "EUR",
                            "source": "google_sheets"
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
                        all_items = sheets_db.get_all_data()
                        tool_output = json.dumps({
                            "error": f"'{wall_type}' not found",
                            "available_walls": [k for k in all_items.keys() if "wall" in k]
                        })
                    else:
                        total = area * cost_per_m2
                        tool_output = json.dumps({
                            "wall_type": wall_type,
                            "area": area,
                            "cost_per_m2": cost_per_m2,
                            "total_cost": total,
                            "currency": "EUR",
                            "source": "google_sheets"
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
                        all_items = sheets_db.get_all_data()
                        tool_output = json.dumps({
                            "error": f"'{material}' not found",
                            "available_flooring": [k for k in all_items.keys() if "floor" in k or "tile" in k or "carpet" in k]
                        })
                    else:
                        total = area * cost_per_m2
                        tool_output = json.dumps({
                            "material": material,
                            "area": area,
                            "cost_per_m2": cost_per_m2,
                            "total_cost": total,
                            "currency": "EUR",
                            "source": "google_sheets"
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
                            "source": "google_sheets"
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
                            "source": "google_sheets"
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
                        "source": "google_sheets"
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
                            "source": "google_sheets"
                        })
                    else:
                        tool_output = json.dumps({"error": "Wall costs not found"})
                except Exception as e:
                    tool_output = json.dumps({"error": str(e)})

            # --- ERP INTEGRATION LOGIC (ORIGINAL) ---
            elif tool_name == "get_unit_cost_by_type" and erp_config is not None:
                element_type = str(tool_args.get("element_type", "")).lower()
                
                try:
                    response = requests.get(
                        f"{erp_config['base_url']}/api/v1/costs/{element_type}",
                        headers={"Authorization": f"Bearer {erp_config['api_key']}"},
                        timeout=5
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        tool_output = json.dumps({
                            "element_type": element_type,
                            "unit_cost": data.get("price") or data.get("unit_cost"),
                            "currency": data.get("currency", "EUR"),
                            "source": "ERP_Live"
                        })
                    else:
                        tool_output = json.dumps({"error": f"ERP lookup failed: {response.status_code}"})
                
                except Exception as e:
                    tool_output = json.dumps({"error": f"Connection to ERP failed: {str(e)}"})

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