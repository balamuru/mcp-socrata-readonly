from fastmcp import FastMCP
from typing import Optional, List, Dict, Any
from socrata_client import SocrataClient
from geocoder import Geocoder
from registry import get_registry
import database
import json
from config import logger
import logging

logger.setLevel(logging.INFO)

# Initialize MCP server
mcp = FastMCP("Socrata-Real-Estate")
client = SocrataClient()
geo = Geocoder()

def _ensure_cache(domain: str, reg: Dict[str, str]):
    nbhd_dataset = reg["neighborhood_dataset"]
    entity_dataset = reg["entity_dataset"]
    
    if not database.is_cache_valid(nbhd_dataset, "neighborhoods"):
        logger.info(f"Rebuilding neighborhood cache for dataset {nbhd_dataset}...")
        records = client.fetch_all(domain, nbhd_dataset)
        database.update_cache(nbhd_dataset, "neighborhoods", records, database.insert_neighborhoods)
        
    if not database.is_cache_valid(entity_dataset, "entities"):
        logger.info(f"Rebuilding entities cache for dataset {entity_dataset}...")
        records = client.fetch_all(domain, entity_dataset)
        database.update_cache(entity_dataset, "entities", records, database.insert_entities)

def _format_property(reg: Dict[str, str], prop: Dict[str, Any]) -> Dict[str, Any]:
    """Helper to join codes and format a property record."""
    formatted = dict(prop)
    
    # Neighborhood lookup
    if "nbhdcode" in prop:
        formatted["neighborhood_name"] = database.get_cached_neighborhood(reg["neighborhood_dataset"], prop["nbhdcode"])
        
    # Entity lookup (entitycodes is often a comma-separated string)
    if "entitycodes" in prop and prop["entitycodes"]:
        codes = [c.strip() for c in str(prop["entitycodes"]).split(",")]
        resolved = [database.get_cached_entity(reg["entity_dataset"], c) for c in codes]
        formatted["taxing_entities"] = resolved
    
    return formatted

@mcp.tool()
def search_properties(address: Optional[str] = None, owner: Optional[str] = None, zip_code: Optional[str] = None, limit: int = 10, county: str = "collin") -> str:
    """
    Search for real estate properties by address, owner name, or zip code.
    Returns JSON formatted properties with resolved neighborhood and taxing entities.
    """
    reg = get_registry(county)
    domain = reg["domain"]
    _ensure_cache(domain, reg)
    
    where_clauses = []
    if address:
        where_clauses.append(f"lower(situsconcat) like '%{address.lower()}%'")
    if owner:
        where_clauses.append(f"lower(ownername) like '%{owner.lower()}%'")
    if zip_code:
        where_clauses.append(f"situszip = '{zip_code}'")
        
    if not where_clauses:
        return json.dumps({"error": "Must provide at least one search parameter (address, owner, or zip_code)."})
        
    where_query = " AND ".join(where_clauses)
    
    try:
        records = client.fetch_page(domain, reg["appraisal_dataset"], limit=limit, where=where_query)
        formatted_records = [_format_property(reg, r) for r in records]
        return json.dumps(formatted_records, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def get_property_detail(property_id: str, county: str = "collin") -> str:
    """
    Retrieve deep details for a specific property using its unique Property ID (propid).
    """
    reg = get_registry(county)
    domain = reg["domain"]
    _ensure_cache(domain, reg)
    
    try:
        records = client.fetch_page(domain, reg["appraisal_dataset"], limit=1, where=f"propid = '{property_id}'")
        if not records:
            return json.dumps({"error": f"Property ID {property_id} not found."})
            
        formatted = _format_property(reg, records[0])
        return json.dumps(formatted, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def query_properties_near(address: str, radius_miles: float = 1.0, limit: int = 10, county: str = "collin") -> str:
    """
    Search for properties within a specific radius of a given address.
    Uses geocoding to resolve the target address to latitude/longitude, then performs a geospatial search.
    """
    reg = get_registry(county)
    domain = reg["domain"]
    _ensure_cache(domain, reg)
    
    coords = geo.geocode(address)
    if not coords:
        return json.dumps({"error": f"Could not geocode address: {address}"})
        
    return json.dumps({"error": "Geospatial search (within_circle) requires a Socrata Point column, which is not natively exposed in the Collin CAD Appraisal Dataset. Feature unavailable."})

@mcp.tool()
def discover_county_datasets(county_name: str) -> str:
    """
    Search the Global Socrata Catalog for datasets related to a specific county.
    """
    import requests
    url = f"https://api.us.socrata.com/api/catalog/v1?q={county_name} CAD"
    try:
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        items = res.json().get('results', [])
        results = [{"id": item['resource']['id'], "name": item['resource']['name'], "domain": item['metadata']['domain']} for item in items[:10]]
        return json.dumps(results, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def refresh_cache(county: str = "collin") -> str:
    """Manually rebuild the local SQLite cache for neighborhoods and entities from SODA API."""
    try:
        reg = get_registry(county)
        domain = reg["domain"]
        records_n = client.fetch_all(domain, reg["neighborhood_dataset"])
        database.update_cache(domain, "neighborhoods", records_n, database.insert_neighborhoods)
        
        records_e = client.fetch_all(domain, reg["entity_dataset"])
        database.update_cache(domain, "entities", records_e, database.insert_entities)
        return json.dumps({"status": "Success", "message": f"Cache rebuilt for {county}."})
    except Exception as e:
        return json.dumps({"error": str(e)})

def run():
    # Allows the server to run over stdio (compatible with Claude Code/Desktop)
    mcp.run(transport='stdio')

if __name__ == "__main__":
    run()
