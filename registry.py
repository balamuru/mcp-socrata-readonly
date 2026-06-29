import requests
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger("socrata-mcp.registry")

# Map of supported counties to their Socrata domain and specific dataset IDs per year.
COUNTY_REGISTRY: Dict[str, Dict[str, Any]] = {
    "collin": {
        "state": "TX",
        "display_name": "Collin County",
        "domain": "data.texas.gov",
        "appraisal_datasets": {
            "2024": "6dqt-e958",  # Collin CAD Appraisal Data - 2024
            "2025": "vffy-snc6",  # Collin CAD Appraisal Data - 2025
            "2026": "nne4-8riu",  # Collin CAD Appraisal Data - 2026 (Preliminary/Current)
        },
        "default_year": "2026",
        "neighborhood_dataset": "uem9-5zfv", # Collin CAD Neighborhood List
        "entity_dataset": "rwqz-r4mp",     # Collin CAD Entity List - Current Year
    },
    "collin_test": {
        "domain": "data.texas.gov",
        "appraisal_datasets": {
            "2025": "vffy-snc6",
            "2026": "nne4-8riu",
        },
        "default_year": "2026",
        "neighborhood_dataset": "test-nbhd",
        "entity_dataset": "test-enti",
    }
}

def discover_dataset_id(county_display_name: str, year: str) -> Optional[str]:
    """
    Dynamically search the Socrata Discovery API for a matching appraisal dataset.
    This enables the server to run in future years without requiring code updates.
    """
    query = f"{county_display_name} CAD Appraisal Data"
    url = f"https://api.us.socrata.com/api/catalog/v1?q={query}"
    try:
        logger.info(f"Auto-discovering dataset on Socrata for {county_display_name} Year {year}...")
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        results = res.json().get('results', [])
        
        # Look for a title matching e.g. "Collin CAD Appraisal Data - 2028"
        for item in results:
            resource = item.get('resource', {})
            name = resource.get('name', '')
            if county_display_name.lower() in name.lower() and "appraisal" in name.lower():
                # Direct year match in title
                if str(year) in name:
                    logger.info(f"Discovered dataset '{name}' with ID '{resource.get('id')}'")
                    return resource.get('id')
                # If checking a future year or current preliminary year, check for "Preliminary"
                if "preliminary" in name.lower():
                    logger.info(f"Using preliminary dataset '{name}' with ID '{resource.get('id')}' for Year {year}")
                    return resource.get('id')
    except Exception as e:
        logger.warning(f"Failed to auto-discover dataset ID: {e}")
    return None

def get_registry(county_name: str, year: Optional[str] = None) -> Dict[str, str]:
    """Retrieve the Socrata domain and dataset IDs for a given county and tax year."""
    key = county_name.lower().strip()
    if key not in COUNTY_REGISTRY:
        raise ValueError(f"County '{county_name}' is not currently pre-configured in the registry.")
    
    cfg = COUNTY_REGISTRY[key]
    target_year = str(year).strip() if year else cfg.get("default_year", "2026")
    
    datasets = cfg.get("appraisal_datasets", {})
    
    # 1. First, check if the year is pre-configured
    if target_year in datasets:
        dataset_id = datasets[target_year]
    # 2. If not, attempt to discover it dynamically on the fly
    else:
        dataset_id = discover_dataset_id(cfg["display_name"], target_year)
        if not dataset_id:
            # Fall back to default if discovery fails
            fallback_year = cfg.get("default_year", "2026")
            dataset_id = datasets[fallback_year]
            logger.warning(
                f"Tax year '{target_year}' could not be discovered. "
                f"Falling back to default year '{fallback_year}' ({dataset_id})"
            )
            target_year = fallback_year
        else:
            # Cache it in memory for subsequent calls in this execution
            datasets[target_year] = dataset_id
        
    return {
        "state": cfg.get("state", ""),
        "display_name": cfg.get("display_name", ""),
        "domain": cfg["domain"],
        "appraisal_dataset": dataset_id,
        "neighborhood_dataset": cfg["neighborhood_dataset"],
        "entity_dataset": cfg["entity_dataset"],
    }

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
