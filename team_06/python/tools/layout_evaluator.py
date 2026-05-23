import networkx as nx
import json
import logging
import math

logger = logging.getLogger(__name__)

class LayoutEvaluator:
    """
    Evaluates a generated layout against relaxed architectural rules, 
    including room presence, proportions, minimum dimensions, and doors.
    """
    def __init__(self, expected_topology_json: str = None):
        self.expected_graph = None
        if expected_topology_json:
            try:
                self.expected_graph = nx.node_link_graph(json.loads(expected_topology_json))
            except Exception as e:
                logger.error(f"Could not parse expected topology: {e}")

        # Relaxed rules for room evaluation
        # Format: { program: (Min Area, Min Edge, Max Ratio), ... }
        # Using 0 or float('inf') for unconstrained values
        self.rules = {
            "living":  {"min_area": 9.0, "min_edge": 2.5, "max_ratio": 3.0},
            "bed":     {"min_area": 7.0, "min_edge": 2.0, "max_ratio": 2.5},
            "kitchen": {"min_area": 4.0, "min_edge": 1.5, "max_ratio": 3.5},
            "bath":    {"min_area": 2.5, "min_edge": 1.2, "max_ratio": 3.5},
            "foyer":   {"min_area": 0.0, "min_edge": 0.3, "max_ratio": float('inf')},
            "extra":   {"min_area": 0.3, "min_edge": 0.5, "max_ratio": 4.0}
        }
        
        self.daylight_required = {"bed": 0.05, "living": 0.1} # Minimal daylight factors

        # Synonyms mapping: map common variants to canonical program keys
        self._synonyms = {
            "bedroom": "bed",
            "bedrooms": "bed",
            "bed": "bed",
            "sleep": "bed",
            "bathroom": "bath",
            "bathrooms": "bath",
            "bath": "bath",
            "wc": "bath",
            "toilet": "bath",
            "livingroom": "living",
            "living_room": "living",
            "living": "living",
            "kitchen": "kitchen",
            "foyer": "foyer",
            "hall": "foyer",
            "extra": "extra",
        }

    def _normalize_program(self, prog: str) -> str:
        if not prog:
            return ""
        p = prog.strip().lower().replace(' ', '').replace('-', '_')
        return self._synonyms.get(p, p)
    def evaluate(self, layout_data: dict) -> dict:
        issues = []
        rooms = layout_data.get('rooms', [])
        doors = layout_data.get('doors', [])
        
        # 1. Check Topoplogy matches
        if self.expected_graph:
            expected_programs = [self._normalize_program(d.get('program', '')) for _, d in self.expected_graph.nodes(data=True)]
            actual_programs = [self._normalize_program(r.get('attributes', {}).get('program', '')) for r in rooms]
            
            from collections import Counter
            expected_counts = Counter(p for p in expected_programs if p)
            actual_counts = Counter(p for p in actual_programs if p)
            
            for prog, count in expected_counts.items():
                if actual_counts.get(prog, 0) < count:
                    issues.append(f"Missing room(s): Expected at least {count} '{prog}', but found {actual_counts.get(prog, 0)}.")
        
        # 2. Check doors connectivity
        rooms_with_doors = set()
        for door in doors:
            connected = door.get('attributes', {}).get('connectsRooms', [])
            for r_id in connected:
                rooms_with_doors.add(r_id)
        
        # 3. Check Room Dimensions, Proportions, Area, and Daylight
        for room in rooms:
            program = self._normalize_program(room.get('attributes', {}).get('program', ''))
            room_name = room.get('name', room['id'])
            
            # Door check
            if room['id'] not in rooms_with_doors:
                issues.append(f"Connectivity: '{room_name}' is not connected to any doors.")
                
            geom = room.get('geometry', [])
            area = room.get('attributes', {}).get('area', 0.0)
            
            if geom and len(geom) >= 3:
                xs = [pt[0] for pt in geom]
                ys = [pt[1] for pt in geom]
                width = max(xs) - min(xs)
                height = max(ys) - min(ys)
                
                if width > 0 and height > 0:
                    min_edge = min(width, height)
                    ratio = max(width/height, height/width)
                    
                    # Apply specific rules if the program is mapped
                    if program in self.rules:
                        rule = self.rules[program]
                        
                        if area > 0 and area < rule['min_area']:
                            issues.append(f"Area: '{room_name}' is {area:.1f} m² (minimum for {program} is {rule['min_area']} m²).")
                            
                        if min_edge < rule['min_edge']:
                            issues.append(f"Dimension: '{room_name}' min edge is {min_edge:.1f}m (minimum for {program} is {rule['min_edge']}m).")
                            
                        if ratio > rule['max_ratio']:
                            issues.append(f"Proportion: '{room_name}' ratio is {ratio:.1f}:1 (maximum for {program} is {rule['max_ratio']}:1).")
                            
            # Daylight check
            if program in self.daylight_required:
                daylight_val = room.get('attributes', {}).get('daylight')
                min_daylight = self.daylight_required[program]
                if isinstance(daylight_val, (int, float)) and daylight_val < min_daylight:
                    issues.append(f"Daylight: '{room_name}' daylight score {daylight_val:.2f} is below minimum {min_daylight}.")

        return {
            "passed": len(issues) == 0,
            "issues": issues
        }