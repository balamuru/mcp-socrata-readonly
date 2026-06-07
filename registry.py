from typing import Dict, Any

# Map of supported counties to their Socrata domain and specific dataset IDs.
# Currently pre-configured for Collin County, TX.
COUNTY_REGISTRY: Dict[str, Dict[str, str]] = {
    "collin": {
        "domain": "data.texas.gov",
        "appraisal_dataset": "vffy-snc6",  # Collin CAD Appraisal Data - 2025
        "neighborhood_dataset": "uem9-5zfv", # Collin CAD Neighborhood List
        "entity_dataset": "rwqz-r4mp",     # Collin CAD Entity List - Current Year
    },
    "collin_test": {
        "domain": "data.texas.gov",
        "appraisal_dataset": "vffy-snc6",
        "neighborhood_dataset": "test-nbhd",
        "entity_dataset": "test-enti",
    }
}

def get_registry(county_name: str) -> Dict[str, str]:
    """Retrieve the Socrata domain and dataset IDs for a given county."""
    key = county_name.lower().strip()
    if key not in COUNTY_REGISTRY:
        raise ValueError(f"County '{county_name}' is not currently pre-configured in the registry.")
    return COUNTY_REGISTRY[key]
