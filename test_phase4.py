from main import search_properties, get_property_detail, discover_county_datasets
import json

def main():
    print("\n--- Testing discover_county_datasets ---")
    datasets = json.loads(discover_county_datasets("Collin"))
    print(f"Found {len(datasets)} datasets. First dataset: {datasets[0]['name']}")

    print("\n--- Testing search_properties (By Address) ---")
    results = json.loads(search_properties(address="ELDORADO", limit=1))
    if isinstance(results, list) and results:
        prop = results[0]
        print(f"Property Found: {prop.get('situsconcat')}")
        print(f"Neighborhood Resolved: {prop.get('neighborhood_name')}")
        print(f"Taxing Entities Resolved: {[e.get('name') for e in prop.get('taxing_entities', [])]}")
        
        propid = prop.get('propid')
        print(f"\n--- Testing get_property_detail for Property ID {propid} ---")
        detail = json.loads(get_property_detail(propid))
        print(f"Owner: {detail.get('ownername')}")
    else:
        print("No properties found or error occurred.")

if __name__ == "__main__":
    main()
