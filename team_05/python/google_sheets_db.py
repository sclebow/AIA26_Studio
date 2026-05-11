import requests
from typing import Dict, Optional
import csv
from io import StringIO

class GoogleSheetsDatabase:
    """Connect to Google Sheets using CSV export (no authentication needed)"""
    
    def __init__(self, sheet_id: str):
        """
        Initialize with Google Sheet ID.
        
        Sheet ID is the long string in the URL:
        https://docs.google.com/spreadsheets/d/SHEET_ID_HERE/edit
        
        Make sure your Google Sheet is "Anyone with the link can view" (public)
        """
        self.sheet_id = sheet_id
        self.data_cache = None
        
        if not sheet_id:
            print("Error: No Sheet ID provided!")
            self.data = {}
            return
        
        # Try to load data from Google Sheets
        self._load_from_sheets()
    
    def _load_from_sheets(self):
        """Load data from Google Sheets via CSV export."""
        try:
            # CSV export URL (works with public sheets)
            csv_url = f"https://docs.google.com/spreadsheets/d/{self.sheet_id}/export?format=csv"
            
            print(f"[Google Sheets] Fetching data from sheet...")
            response = requests.get(csv_url, timeout=10)
            
            if response.status_code == 200:
                # Parse CSV
                csv_reader = csv.DictReader(StringIO(response.text))
                self.data = {}
                
                for row in csv_reader:
                    if row:
                        # Get item name and cost
                        item_name = None
                        cost = None
                        
                        # Try to find columns (flexible column naming)
                        for key, value in row.items():
                            key_lower = key.lower().strip()
                            
                            if 'item' in key_lower or 'name' in key_lower:
                                item_name = value
                            elif 'cost' in key_lower or 'price' in key_lower or 'value' in key_lower:
                                cost = value
                        
                        # If columns not identified, try first two columns
                        if not item_name or not cost:
                            values = [v for v in row.values() if v]
                            if len(values) >= 2:
                                item_name = values[0]
                                cost = values[1]
                        
                        # Store in database
                        if item_name and cost:
                            try:
                                cost_float = float(cost)
                                self.data[item_name] = cost_float
                            except ValueError:
                                pass
                
                if self.data:
                    print(f"✓ Loaded {len(self.data)} items from Google Sheets")
                    print(f"  Items: {', '.join(list(self.data.keys())[:3])}...")
                else:
                    print("Warning: No data found in Google Sheet")
                    
            else:
                print(f"Error: Could not fetch sheet (Status {response.status_code})")
                print("Make sure:")
                print("  1. Sheet ID is correct")
                print("  2. Sheet is shared (Anyone with link can view)")
                self.data = {}
                
        except requests.exceptions.Timeout:
            print("Error: Google Sheets request timed out")
            self.data = {}
        except requests.exceptions.ConnectionError:
            print("Error: Could not connect to Google Sheets")
            self.data = {}
        except Exception as e:
            print(f"Error loading from Google Sheets: {e}")
            self.data = {}
    
    def get_all_data(self) -> Dict[str, float]:
        """Get all items and costs."""
        return self.data.copy()
    
    def get_cost(self, item_name: str) -> Optional[float]:
        """Get cost of an item by name."""
        if not self.data:
            return None
        
        # Try exact match first (case-insensitive)
        for key, value in self.data.items():
            if key.lower() == item_name.lower():
                return value
        
        # Try partial match
        item_lower = item_name.lower()
        for key, value in self.data.items():
            if item_lower in key.lower() or key.lower() in item_lower:
                return value
        
        return None


def get_sheets_db(sheet_id: str):
    """Get Google Sheets database instance."""
    if not sheet_id:
        print("Error: GOOGLE_SHEET_ID environment variable not set!")
        return None
    
    return GoogleSheetsDatabase(sheet_id)