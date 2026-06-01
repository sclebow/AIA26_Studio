import json
from typing import Any
from heatmap_generator import HeatmapGenerator
from live_material_api import live_db
import pathlib

def build_generate_heatmap_node():
    """Node that generates heatmap from layout and Live Market costs"""
    
    heatmap_gen = HeatmapGenerator()
    
    def generate_heatmap_node(state):
        """Generate heatmap visualization from layout data"""
        
        print("\n[generate_heatmap] Creating heatmap from Live Market data...")
        
        # Get layout data from state
        layout_data = state.get("layout_data", {})
        
        if not layout_data:
            state["final_response"] = "Error: No layout data available for heatmap generation"
            return state
        
        try:
            # Generate heatmap with our new Live Database costs
            heatmap_data = heatmap_gen.generate_full_heatmap(layout_data)
            
            # Store in state
            state["heatmap_data"] = heatmap_data
            state["heatmap_json_string"] = json.dumps(heatmap_data, indent=2)
            
            print("[generate_heatmap] ✓ Heatmap generated successfully")
            
        except Exception as e:
            print(f"[generate_heatmap] Error: {e}")
            state["final_response"] = f"Error generating heatmap: {str(e)}"
        
        return state
    
    return generate_heatmap_node


def build_present_heatmap_node():
    """Node that presents the heatmap to the user"""
    
    def present_heatmap_node(state):
        print("\n[present_heatmap] Presenting cost heatmap...")
        
        try:
            heatmap_data = state.get("heatmap_data", {})
            # Ensure we have the necessary sub-dictionaries
            costs = heatmap_data.get("costs", {})
            totals = heatmap_data.get("totals", {})

            # 1. Start building the response string (Updated for Live Database & USD)
            response = f"""## Cost Heatmap Analysis (Live Market Database)

### Project Overview
- **Total Cost:** ${totals.get('grand_total', 0):,.2f}
- **Currency:** USD
- **Data Source:** Supabase + FRED API

### Cost Breakdown by Element

**Rooms:** ${totals.get('rooms', 0):,.2f}
- Includes all room finishes (floor, walls, ceiling, slab)
- Calculated from layout area × Live Market rates per m²

**Doors:** ${totals.get('doors', 0):,.2f}
- All door openings and their finishes
- Queried from Live Supabase Database

**Windows:** ${totals.get('windows', 0):,.2f}
- All window openings and their finishes
- Queried from Live Supabase Database

**Columns:** ${totals.get('columns', 0):,.2f}
- All structural columns and finishes
- Queried from Live Supabase Database

### Room-by-Room Breakdown
"""
            # 2. Add room details dynamically
            rooms = costs.get("rooms", {})
            for room_id, room_data in rooms.items():
                response += f"""
**{room_data.get('name', 'Unknown')}** (ID: {room_id})
- Area: {room_data.get('area_m2', 0)} m²
- Unit Rate: ${room_data.get('cost_per_m2', 0):,.2f}/m²
- Total Cost: ${room_data.get('total_cost', 0):,.2f}
"""
            
            # 3. Add Footer
            response += """
### Heatmap Color Legend
- 🟦 **Blue (Cool):** Low cost areas
- 🟩 **Green (Medium):** Medium cost areas   
- 🟨 **Yellow (Warm):** High cost areas
- 🟥 **Red (Hot):** Very high cost areas

All costs are calculated using live market data from the US Federal Reserve. The heatmap helps identify cost-heavy areas in your design based on today's economic conditions.

### Next Steps
1. Ask for cost comparisons between different materials
2. Request modifications to specific rooms
3. Analyze trade-offs between design alternatives
4. Export the cost data for further analysis
"""
            state["final_response"] = response
            
            # 4. Handle File Saving
            heatmap_json = state.get("heatmap_json_string", "{}")
            if "edited_layout_path" in state:
                # Save relative to the layout path
                heatmap_path = pathlib.Path(state["edited_layout_path"]).parent / "heatmap_data.json"
            else:
                # Fallback to current directory
                heatmap_path = pathlib.Path("heatmap_data.json")
                
            heatmap_path.write_text(heatmap_json)
            state["heatmap_path"] = str(heatmap_path)
            print(f"[present_heatmap] Heatmap saved to {heatmap_path}")
            
        except Exception as e:
            print(f"[present_heatmap] Error: {e}")
            state["final_response"] = f"Error presenting heatmap: {str(e)}"
        
        return state
    
    return present_heatmap_node


def build_calculate_delta_node():
    """Node that calculates cost difference between scenarios"""
    
    def calculate_delta_node(state):
        """Calculate cost delta between baseline and alternative"""
        
        print("\n[calculate_delta] Computing cost difference...")
        
        baseline_cost = state.get("baseline_cost", 0)
        alternative_cost = state.get("alternative_cost", 0)
        
        # Use simple validation to allow 0 cost if that's valid, but ensure keys exist
        if baseline_cost is None or alternative_cost is None:
            state["final_response"] = "Error: Missing cost data for comparison"
            return state
        
        delta = alternative_cost - baseline_cost
        delta_percent = (delta / baseline_cost * 100) if baseline_cost != 0 else 0
        
        # Store in state
        state["cost_delta"] = delta
        state["cost_delta_percent"] = delta_percent
        
        print(f"[calculate_delta] Delta: ${delta:,.2f} ({delta_percent:.1f}%)")
        
        return state
    
    return calculate_delta_node