import os
from supabase import create_client, Client

# Use your actual Supabase URL and anon Key here (or use os.getenv if you set up local env variables)
SUPABASE_URL = "https://chqvhptqibvptgshjmjc.supabase.co"
SUPABASE_KEY = "sb_publishable_--6slnsto3odBa2OLi73Fw_sOXSxM5T"

class MaterialAPI:
    def __init__(self):
        self.supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        # Fetch the live market multiplier as soon as the agent wakes up
        self.market_multiplier = self._get_live_multiplier()

    def _get_live_multiplier(self) -> float:
        """Pulls the latest FRED index multiplier from Supabase."""
        try:
            response = self.supabase.table("market_multipliers") \
                .select("multiplier") \
                .eq("series_id", "WPUSI012011") \
                .execute()
            
            if response.data:
                return float(response.data[0]['multiplier'])
            return 1.0 # Default to 1.0 if not found
        except Exception as e:
            print(f"⚠️ Could not fetch market multiplier: {e}")
            return 1.0

    def get_live_rate(self, element_name: str, base_rate: float) -> float:
        """
        Calculates the final cost by applying the live market multiplier 
        to your base architectural element rate.
        """
        final_rate = base_rate * self.market_multiplier
        print(f"🧮 {element_name}: Base ${base_rate} x {self.market_multiplier} Market Index = ${round(final_rate, 2)}")
        
        return round(final_rate, 2)

# Initialize for use in your LangGraph workflow
live_db = MaterialAPI()