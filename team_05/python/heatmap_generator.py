import json
from typing import Dict, Any, List
from live_material_api import live_db

class HeatmapGenerator:
    """Generate cost heatmap from layout and Live Market database"""
    
    def __init__(self):
        self.db = live_db
    
    def calculate_room_costs(self, layout_data: Dict[str, Any]) -> Dict[str, Any]:
        """Prioritizes costs calculated by the Grasshopper MCP tool."""
        
        rooms = layout_data.get("rooms", [])
        room_costs = {}
        total_room_cost = 0
        
        for room in rooms:
            room_id = room.get("id", "unknown")
            room_name = room.get("name", "Unknown")
            
            # --- THE GRASSHOPPER CONNECTION ---
            # 1. Check if the 'compute_room_cost' tool already calculated this
            total_cost = room.get("total_cost")
            area_m2 = room.get("area_m2", 0)
            
            # 2. If the tool hasn't run yet, we fetch a live rate as a fallback
            if total_cost is None:
                cost_rate = self.db.get_live_rate(room_name, base_rate=500.0)
                total_cost = area_m2 * cost_rate if cost_rate else 0
            else:
                # If the tool DID run, calculate the effective rate for the report
                cost_rate = total_cost / area_m2 if area_m2 > 0 else 0
            
            total_room_cost += total_cost
            
            room_costs[room_id] = {
                "name": room_name,
                "area_m2": area_m2,
                "cost_per_m2": cost_rate,
                "total_cost": total_cost,
                "polygon": room.get("polygon", [])
            }
        
        return {
            "rooms": room_costs,
            "total_cost": total_room_cost
        }
    
    def calculate_openings_costs(self, layout_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate cost for doors and windows using Live Market prices"""
        
        openings = layout_data.get("openings", [])
        doors_cost = {}
        windows_cost = {}
        total_doors = 0
        total_windows = 0
        
        for opening in openings:
            opening_id = opening.get("id", "unknown")
            opening_type = opening.get("type", "unknown").lower()
            subtype = opening.get("subtype", "")
            
            # Query Live Database
            cost = self.db.get_live_rate(subtype, base_rate=500.0) or self.db.get_live_rate(opening_type, base_rate=500.0)
            
            if cost is None:
                cost = 0
            
            if opening_type == "door":
                doors_cost[opening_id] = {
                    "type": subtype,
                    "cost": cost,
                    "polygon": opening.get("polygon", [])
                }
                total_doors += cost
            elif opening_type == "window":
                windows_cost[opening_id] = {
                    "type": subtype,
                    "cost": cost,
                    "polygon": opening.get("polygon", [])
                }
                total_windows += cost
        
        return {
            "doors": doors_cost,
            "windows": windows_cost,
            "total_doors": total_doors,
            "total_windows": total_windows
        }
    
    def calculate_columns_costs(self, layout_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate cost for columns using Live Market prices"""
        
        columns = layout_data.get("columns", [])
        columns_cost = {}
        total_columns = 0
        
        for column in columns:
            column_id = column.get("id", "unknown")
            subtype = column.get("subtype", "interior")
            
            # Query Live Database
            cost = self.db.get_live_rate(subtype, base_rate=500.0) or self.db.get_live_rate("column", base_rate=500.0)
            
            if cost is None:
                cost = 0
            
            columns_cost[column_id] = {
                "type": subtype,
                "cost": cost,
                "polygon": column.get("polygon", [])
            }
            total_columns += cost
        
        return {
            "columns": columns_cost,
            "total_cost": total_columns
        }
    
    def generate_full_heatmap(self, layout_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate complete heatmap with all costs from Live Database"""
        
        print("[Heatmap] Calculating costs from Live Market database...")
        
        # Calculate costs for all elements
        room_costs = self.calculate_room_costs(layout_data)
        opening_costs = self.calculate_openings_costs(layout_data)
        column_costs = self.calculate_columns_costs(layout_data)
        
        # Calculate totals
        total_cost = (
            room_costs["total_cost"] + 
            opening_costs["total_doors"] + 
            opening_costs["total_windows"] + 
            column_costs["total_cost"]
        )
        
        # Generate heatmap with color ranges
        heatmap_data = {
            "project": layout_data.get("project", {}),
            "costs": {
                "rooms": room_costs,
                "openings": {
                    "doors": opening_costs["doors"],
                    "windows": opening_costs["windows"],
                    "total_doors": opening_costs["total_doors"],
                    "total_windows": opening_costs["total_windows"]
                },
                "columns": column_costs,
                "totals": {
                    "rooms": room_costs["total_cost"],
                    "doors": opening_costs["total_doors"],
                    "windows": opening_costs["total_windows"],
                    "columns": column_costs["total_cost"],
                    "grand_total": total_cost,
                    "currency": "USD"
                }
            },
            "heatmap": self._generate_color_ramp(room_costs["rooms"]),
            "source": "Supabase + FRED API"
        }
        
        print(f"[Heatmap] Total project cost: ${total_cost:,.2f} USD")
        print(f"[Heatmap] Breakdown:")
        print(f"  - Rooms: ${room_costs['total_cost']:,.2f} USD")
        print(f"  - Doors: ${opening_costs['total_doors']:,.2f} USD")
        print(f"  - Windows: ${opening_costs['total_windows']:,.2f} USD")
        print(f"  - Columns: ${column_costs['total_cost']:,.2f} USD")
        
        return heatmap_data
    
    def _generate_color_ramp(self, rooms: Dict[str, Any]) -> Dict[str, Any]:
        """Generate color values for heatmap visualization"""
        
        if not rooms:
            return {}
        
        # Find min/max costs
        costs = [r["total_cost"] for r in rooms.values()]
        min_cost = min(costs) if costs else 0
        max_cost = max(costs) if costs else 1
        
        # Color ramp: light yellow (low) → orange → red (high)
        color_ramp = [
            {"t": 0.0, "hex": "#FFF5DC"},    # Cream
            {"t": 0.25, "hex": "#FED976"},   # Light yellow
            {"t": 0.5, "hex": "#FEB24C"},    # Yellow
            {"t": 0.75, "hex": "#F06913"},   # Orange
            {"t": 1.0, "hex": "#BD0026"}     # Red
        ]
        
        # Assign colors to rooms
        room_colors = {}
        for room_id, room_data in rooms.items():
            cost = room_data["total_cost"]
            # Normalize cost to 0-1
            if max_cost > min_cost:
                heat_t = (cost - min_cost) / (max_cost - min_cost)
            else:
                heat_t = 0
            
            # Find appropriate color
            color_hex = self._get_color_for_heat(heat_t, color_ramp)
            
            room_colors[room_id] = {
                "heat_t": heat_t,
                "color_hex": color_hex
            }
        
        return {
            "rooms": room_colors,
            "ranges": {
                "min_cost": min_cost,
                "max_cost": max_cost
            },
            "ramp": color_ramp
        }
    
    def _get_color_for_heat(self, heat_t: float, ramp: List[Dict]) -> str:
        """Get hex color for heat value (0-1)"""
        
        # Find surrounding ramp points
        for i in range(len(ramp) - 1):
            if ramp[i]["t"] <= heat_t <= ramp[i+1]["t"]:
                # Use the closer color
                if heat_t - ramp[i]["t"] < ramp[i+1]["t"] - heat_t:
                    return ramp[i]["hex"]
                else:
                    return ramp[i+1]["hex"]
        
        return ramp[-1]["hex"]  # Return highest color if beyond range
    
    def _get_rate_for_category(self, category: str) -> float:
        """Get default rate for room category adjusted by live market multiplier"""
        
        category_rates = {
            "common": 3200.0,
            "bedroom": 2500.0,
            "wet": 4500.0,
            "circulation": 1500.0,
            "service": 1800.0,
            "kitchen": 3500.0
        }
        
        # Default fallback
        base_rate = category_rates.get(category, 2000.0)
        
        # Query our live database using the category name and its base rate
        live_rate = self.db.get_live_rate(category, base_rate=base_rate)
        
        return live_rate


def get_heatmap_generator() -> HeatmapGenerator:
    """Get or create heatmap generator instance"""
    return HeatmapGenerator()