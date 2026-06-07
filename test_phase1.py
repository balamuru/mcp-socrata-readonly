import sys
from socrata_client import SocrataClient
from config import logger
import logging

def main():
    # Ensure info logs are printed
    logger.setLevel(logging.INFO)
    
    client = SocrataClient()
    
    # Test UC 1.1: Fetch a single page
    print("--- Testing UC 1.1: Single page fetch ---")
    try:
        # Fetching 5 records from Collin CAD Entity List
        records = client.fetch_page("data.texas.gov", "rwqz-r4mp", limit=5)
        print(f"Success! Fetched {len(records)} records.")
        for r in records:
            print(f"- {r.get('entity_description', 'No desc')} (Code: {r.get('entity_code', 'N/A')})")
    except Exception as e:
        print(f"Failed UC 1.1: {e}")
        
    # Test UC 1.2: Fetch all records (pagination handling)
    print("\n--- Testing UC 1.2 & UC 1.3: Fetch all with pagination/retries ---")
    try:
        all_records = client.fetch_all("data.texas.gov", "rwqz-r4mp")
        print(f"Success! Total records fetched: {len(all_records)}")
    except Exception as e:
        print(f"Failed UC 1.2: {e}")

if __name__ == "__main__":
    main()
