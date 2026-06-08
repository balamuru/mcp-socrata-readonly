from fastmcp import FastMCP
from typing import Optional, List, Dict, Any
from socrata_client import SocrataClient
from geocoder import Geocoder
from registry import get_registry, list_states, list_counties
import database
import json
from config import logger
import logging

logger.setLevel(logging.INFO)

# Initialize MCP server
mcp = FastMCP("mcp-socrata-readonly")
client = SocrataClient()
geo = Geocoder()

def _fetch_and_cache_cities(domain: str, reg: Dict[str, str]) -> List[Dict[str, Any]]:
    """Return city/zip pairs for a county, fetching from Socrata if the cache is stale."""
    appraisal_dataset = reg["appraisal_dataset"]
    if not database.is_cache_valid(appraisal_dataset, "cities"):
        logger.info(f"Rebuilding cities cache for dataset {appraisal_dataset}...")
        records = client.fetch_page(
            domain, appraisal_dataset,
            limit=500,
            select="situscity,situszip",
            where="situscity IS NOT NULL AND situszip IS NOT NULL",
            group="situscity,situszip",
            order="situscity ASC,situszip ASC",
        )
        database.update_cache(appraisal_dataset, "cities", records, database.insert_cities)
    return database.get_cached_cities(appraisal_dataset)

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

def _sanitize(value: str) -> str:
    """Escape single quotes for SODA SoQL string literals."""
    return value.replace("'", "''")

def _word_boundary_clause(field: str, token: str) -> str:
    """Match token as a whole word (not as a substring of a longer word)."""
    t = _sanitize(token)
    return (
        f"({field} = '{t}'"
        f" OR {field} like '{t} %'"
        f" OR {field} like '% {t} %'"
        f" OR {field} like '% {t}')"
    )

def _build_owner_where(owner: str) -> str:
    """
    Build a SODA WHERE clause for owner name matching with:
    - Word-boundary awareness for single tokens (avoids partial matches like balamuru→balamurugan)
    - Phrase reversal for multi-word queries (handles 'vinay balamuru' → 'BALAMURU VINAY')
    - Per-token word-boundary AND for multi-word queries
    """
    tokens = owner.lower().split()
    if not tokens:
        return "1=1"

    field = "lower(ownername)"

    if len(tokens) == 1:
        return _word_boundary_clause(field, tokens[0])

    phrase = " ".join(_sanitize(t) for t in tokens)
    reversed_phrase = " ".join(_sanitize(t) for t in reversed(tokens))

    clauses = [f"{field} like '%{phrase}%'"]
    if reversed_phrase != phrase:
        clauses.append(f"{field} like '%{reversed_phrase}%'")
    # Also match records where every token appears as a whole word (any order)
    token_clauses = [_word_boundary_clause(field, t) for t in tokens]
    clauses.append("(" + " AND ".join(token_clauses) + ")")

    return "(" + " OR ".join(clauses) + ")"

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
        # Allow * as a user-friendly wildcard; sanitize quotes
        addr_pattern = _sanitize(address.lower()).replace("*", "%")
        where_clauses.append(f"lower(situsconcat) like '%{addr_pattern}%'")
    if owner:
        where_clauses.append(_build_owner_where(owner))
    if zip_code:
        where_clauses.append(f"situszip = '{_sanitize(zip_code)}'")

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
def list_supported_locations(state: Optional[str] = None, county: Optional[str] = None) -> str:
    """
    Browse the geographic coverage supported by this MCP server.

    - No arguments:          lists all supported states.
    - state="TX":            lists all supported counties in Texas.
    - county="collin":       lists all cities and zip codes within Collin County.
    - state="TX", county="collin": same as above (state disambiguates if county key is shared across states).
    """
    try:
        # County-level drill-down: return cities + zip codes
        if county:
            reg = get_registry(county)
            domain = reg["domain"]
            cities = _fetch_and_cache_cities(domain, reg)
            return json.dumps({
                "level": "cities",
                "county": county.lower().strip(),
                "display_name": reg.get("display_name", county),
                "state": reg.get("state", ""),
                "cities": cities,
            }, indent=2)

        # State-level drill-down: return matching counties
        if state:
            counties = list_counties(state)
            if not counties:
                return json.dumps({"error": f"No supported counties found for state '{state}'."})
            return json.dumps({
                "level": "counties",
                "state": state.upper(),
                "counties": counties,
            }, indent=2)

        # Top level: return all supported states
        return json.dumps({
            "level": "states",
            "supported_states": list_states(),
        }, indent=2)

    except ValueError as e:
        return json.dumps({"error": str(e)})

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
