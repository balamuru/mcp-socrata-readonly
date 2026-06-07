import logging
from config import logger
from socrata_client import SocrataClient
from registry import get_registry
import database

def main():
    logger.setLevel(logging.INFO)
    
    county = "collin"
    reg = get_registry(county)
    domain = reg["domain"]
    
    client = SocrataClient()
    
    # Check if Neighborhood cache is valid
    if not database.is_cache_valid(domain, "neighborhoods"):
        print("Neighborhood cache is invalid or missing. Fetching from SODA...")
        records = client.fetch_all(domain, reg["neighborhood_dataset"])
        database.update_cache(domain, "neighborhoods", records, database.insert_neighborhoods)
    else:
        print("Neighborhood cache is valid.")
        
    # Check if Entity cache is valid
    if not database.is_cache_valid(domain, "entities"):
        print("Entity cache is invalid or missing. Fetching from SODA...")
        records = client.fetch_all(domain, reg["entity_dataset"])
        database.update_cache(domain, "entities", records, database.insert_entities)
    else:
        print("Entity cache is valid.")

    # Test cache retrieval (Testing fast local joins)
    print("\n--- Testing fast local joins from SQLite ---")
    print("Neighborhood code '10A':", database.get_cached_neighborhood(domain, "10A"))
    print("Entity code 'GCO':", database.get_cached_entity(domain, "GCO"))

if __name__ == "__main__":
    main()
