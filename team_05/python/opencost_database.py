import requests
from typing import Dict, Optional
import os
from dotenv import load_dotenv

load_dotenv()

class OpenCostDatabase:
    """
    Connect to OpenCost API - free, auto-updating construction cost database
    https://opencost.org
    """
    
    def __init__(self):
        """Initialize OpenCost database connection"""
        self.base_url = "https://api.opencost.org/v1"
        self.region = os.getenv("COST_REGION", "EU")
        self.currency = os.getenv("COST_CURRENCY", "EUR")
        self.data_cache = {}
        
        print(f"[OpenCost] Initializing database (Region: {self.region}, Currency: {self.currency})")
        print("[OpenCost] This database auto-updates with market data - no manual intervention needed!")
    
    def get_cost(self, item_name: str) -> Optional[float]:
        """
        Get cost of architectural element from OpenCost
        
        Queries the live market database
        """
        try:
            # Format item name for API
            item_slug = item_name.lower().replace(" ", "-")
            
            # Query OpenCost API
            url = f"{self.base_url}/materials/{item_slug}"
            params = {
                "region": self.region,
                "currency": self.currency
            }
            
            print(f"[OpenCost] Fetching price for: {item_name}")
            response = requests.get(url, params=params, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                price = data.get("price")
                updated = data.get("updated", "unknown")
                
                print(f"✓ {item_name}: {price} {self.currency} (Updated: {updated})")
                return float(price) if price else None
            
            else:
                # If item not found, try alternatives
                print(f"⚠ Item '{item_name}' not found in OpenCost")
                return self._get_fallback_price(item_name)
        
        except requests.exceptions.Timeout:
            print(f"⚠ OpenCost timeout for {item_name}")
            return None
        except Exception as e:
            print(f"⚠ Error fetching from OpenCost: {e}")
            return None
    
    def _get_fallback_price(self, item_name: str) -> Optional[float]:
        """Try alternative search methods"""
        try:
            # Try category-based search
            item_lower = item_name.lower()
            
            if "door" in item_lower:
                return self._get_cost_by_category("doors")
            elif "window" in item_lower:
                return self._get_cost_by_category("windows")
            elif "wall" in item_lower:
                return self._get_cost_by_category("walls")
            elif "floor" in item_lower or "tile" in item_lower:
                return self._get_cost_by_category("flooring")
            elif "ceiling" in item_lower:
                return self._get_cost_by_category("ceilings")
        except:
            pass
        
        return None
    
    def _get_cost_by_category(self, category: str) -> Optional[float]:
        """Get average cost for a category"""
        try:
            url = f"{self.base_url}/categories/{category}"
            params = {
                "region": self.region,
                "currency": self.currency
            }
            
            response = requests.get(url, params=params, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                avg_price = data.get("average_price")
                return float(avg_price) if avg_price else None
        except:
            pass
        
        return None
    
    def get_all_data(self) -> Dict[str, float]:
        """Get all common architectural elements from OpenCost"""
        try:
            items = [
                "wooden-door",
                "metal-door",
                "window",
                "concrete-wall",
                "brick-wall",
                "glass-facade",
                "floor-tiles",
                "ceiling",
                "paint",
                "insulation"
            ]
            
            costs = {}
            
            for item in items:
                url = f"{self.base_url}/materials/{item}"
                params = {
                    "region": self.region,
                    "currency": self.currency
                }
                
                try:
                    response = requests.get(url, params=params, timeout=3)
                    if response.status_code == 200:
                        data = response.json()
                        price = data.get("price")
                        if price:
                            key = item.replace("-", "_")
                            costs[key] = float(price)
                except:
                    pass
            
            print(f"✓ Loaded {len(costs)} items from OpenCost")
            return costs
        
        except Exception as e:
            print(f"Error loading data: {e}")
            return {}
    
    def get_price_trend(self, item_name: str) -> Dict:
        """Get price trend for an item (if available)"""
        try:
            item_slug = item_name.lower().replace(" ", "-")
            url = f"{self.base_url}/materials/{item_slug}/trend"
            
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                return response.json()
        except:
            pass
        
        return {}
    
    def get_regional_price(self, item_name: str, region: str) -> Optional[float]:
        """Get price for different region"""
        try:
            item_slug = item_name.lower().replace(" ", "-")
            url = f"{self.base_url}/materials/{item_slug}"
            params = {
                "region": region,
                "currency": self.currency
            }
            
            response = requests.get(url, params=params, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                return float(data.get("price"))
        except:
            pass
        
        return None


def get_opencost_db():
    """Get OpenCost database instance"""
    return OpenCostDatabase()
