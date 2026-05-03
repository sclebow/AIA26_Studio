import json
from pathlib import Path

class CostDatabase:
    """Load and query cost data from JSON file."""
    
    def __init__(self, json_path=None):
        """Initialize with path to cost_database.json."""
        
        # Try to find the file if not provided
        if json_path is None:
            # Look in several common locations
            possible_paths = [
                Path(__file__).parent.parent.parent / "cost_database.json",  # team_05/
                Path(__file__).parent.parent / "cost_database.json",          # team_05/python/
                Path.cwd() / "cost_database.json",                            # current directory
            ]
            
            for path in possible_paths:
                if path.exists():
                    json_path = path
                    break
            
            if json_path is None:
                raise FileNotFoundError("cost_database.json not found. Please provide the path.")
        
        self.json_path = Path(json_path)
        self.data = self._load_json()
    
    def _load_json(self):
        """Load JSON file."""
        with open(self.json_path, 'r') as f:
            return json.load(f)
    
    def get_cost(self, item_name: str) -> float:
        """Get cost of an item by name."""
        # Handle case-insensitive lookups
        item_lower = item_name.lower().replace(" ", "_")
        
        for key, value in self.data.items():
            if key.lower() == item_lower:
                return value
        
        # If not found, try partial match
        for key, value in self.data.items():
            if item_lower in key.lower() or key.lower() in item_lower:
                return value
        
        return None
    
    def get_all_items(self) -> dict:
        """Get all items and their costs."""
        return self.data.copy()
    
    def list_items(self):
        """Print all available items."""
        print("Available items in cost database:")
        for item, cost in self.data.items():
            print(f"  - {item}: ${cost}")


# Singleton instance
_db_instance = None

def get_db(json_path=None) -> CostDatabase:
    """Get or create database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = CostDatabase(json_path)
    return _db_instance