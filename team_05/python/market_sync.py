import os
from fredapi import Fred
from supabase import create_client, Client

# These tell the code to look for the "Secret" names in GitHub's vault
FRED_API_KEY = os.getenv("FRED_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

fred = Fred(api_key=FRED_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def update_market_multipliers():
    # Fetches the index: Producer Price Index: Construction Materials
    data = fred.get_series('WPUSI012011')
    latest_index = data.iloc[-1] 
    
    # Update Supabase
    supabase.table("market_multipliers").upsert({
        "series_id": "WPUSI012011",
        "multiplier": round(latest_index / 320.0, 3), # Adjust 320 to your base
        "last_updated": "now()"
    }, on_conflict="series_id").execute()
    print("Done!")

if __name__ == "__main__":
    update_market_multipliers()