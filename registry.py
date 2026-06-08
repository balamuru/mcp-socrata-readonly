from typing import Dict, Any, List, Optional

# Map of supported counties to their Socrata domain and specific dataset IDs.
# Keys ending in "_test" are internal and excluded from public listing.
COUNTY_REGISTRY: Dict[str, Dict[str, str]] = {
    "collin": {
        "state": "TX",
        "display_name": "Collin County",
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

def list_states() -> List[str]:
    """Return distinct states that have at least one configured county (excludes _test entries)."""
    states = {
        cfg["state"]
        for key, cfg in COUNTY_REGISTRY.items()
        if not key.endswith("_test") and "state" in cfg
    }
    return sorted(states)

def list_counties(state: Optional[str] = None) -> List[Dict[str, str]]:
    """Return configured counties, optionally filtered by state abbreviation (e.g. 'TX')."""
    results = []
    for key, cfg in COUNTY_REGISTRY.items():
        if key.endswith("_test") or "state" not in cfg:
            continue
        if state and cfg["state"].upper() != state.upper():
            continue
        results.append({
            "key": key,
            "display_name": cfg["display_name"],
            "state": cfg["state"],
        })
    return sorted(results, key=lambda c: (c["state"], c["display_name"]))
