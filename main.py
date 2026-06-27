from fastmcp import FastMCP
from typing import Optional, List, Dict, Any
from socrata_client import SocrataClient
from geocoder import Geocoder
from registry import get_registry, list_states, list_counties
import database
import json
import statistics
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

def _comp_stats(comps_raw: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute YoY market-value change statistics across a list of comparable property records."""
    yoy_pcts: List[float] = []
    comp_details: List[Dict[str, Any]] = []
    for c in comps_raw:
        try:
            prev = float(c.get("prevvalmarket", 0) or 0)
            curr = float(c.get("currvalmarket", 0) or 0)
            if prev <= 0 or curr <= 0:
                continue
            yoy = (curr - prev) / prev * 100
            yoy_pcts.append(yoy)
            comp_details.append({
                "address": c.get("situsconcat", ""),
                "sqft": int(float(c.get("imprvmainarea", 0) or 0)),
                "year_built": c.get("imprvyearbuilt", ""),
                "prev_value": int(prev),
                "curr_value": int(curr),
                "yoy_change_pct": round(yoy, 2),
            })
        except (ValueError, TypeError, ZeroDivisionError):
            continue

    n = len(yoy_pcts)
    if n == 0:
        return {"count": 0, "comps": []}

    return {
        "count": n,
        "median_yoy_pct": round(statistics.median(yoy_pcts), 2),
        "mean_yoy_pct": round(statistics.mean(yoy_pcts), 2),
        "stdev_yoy_pct": round(statistics.stdev(yoy_pcts) if n >= 2 else 0.0, 2),
        "pct_increased": round(sum(1 for y in yoy_pcts if y > 0) / n * 100, 1),
        "pct_decreased": round(sum(1 for y in yoy_pcts if y < 0) / n * 100, 1),
        "comps": sorted(comp_details, key=lambda x: x["yoy_change_pct"]),
    }


def _build_evidence_doc(
    subject: Dict[str, Any],
    stats: Dict[str, Any],
    state: str,
    county_display: str,
    dataset_id: str,
    comps_source: str,
    size_tolerance_pct: int,
) -> str:
    """Render a markdown protest evidence package for an outlier appraisal increase."""
    from datetime import date as _date

    subj_prev = subject["prev_value"]
    subj_curr = subject["curr_value"]
    subj_yoy = subject["yoy_change_pct"]
    comp_median = stats["median_yoy_pct"]
    gap_pp = round(subj_yoy - comp_median, 2)
    target_value = int(subj_prev * (1 + comp_median / 100))
    reduction = subj_curr - target_value
    reduction_pct = round(reduction / subj_curr * 100, 2)

    comp_yoys = sorted(c["yoy_change_pct"] for c in stats["comps"])
    rank_below = sum(1 for y in comp_yoys if y < subj_yoy)
    percentile = int(rank_below / len(comp_yoys) * 100) if comp_yoys else 50

    size_min = int(subject["sqft"] * (1 - size_tolerance_pct / 100))
    size_max = int(subject["sqft"] * (1 + size_tolerance_pct / 100))
    source_label = (
        f"neighborhood code **{subject['neighborhood_code']}**"
        if comps_source == "neighborhood"
        else f"zip code **{subject.get('situszip', '')}**"
    )

    if state.upper() == "TX":
        legal_block = (
            "Under **Texas Tax Code §41.43**, the appraisal district bears the burden of "
            "establishing value if the proposed appraisal exceeds the median appraised value "
            "of a reasonable number of comparable properties, appropriately adjusted. "
            "The evidence above demonstrates that the subject property's appraised value "
            "is materially inconsistent with comparable properties in the same area.\n\n"
            f"**Recommended action:** File a formal protest with the **{county_display} "
            "Appraisal Review Board (ARB)** before the protest deadline (typically **May 15** "
            "or **30 days after the notice date**, whichever is later). "
            "Attach this document as your comparables evidence."
        )
    else:
        legal_block = (
            "Property taxation requires uniform and equal appraisal of comparable properties. "
            "The evidence above indicates the subject property's appraised value increased "
            "materially more than comparable properties in the same area during the same "
            "appraisal cycle.\n\n"
            f"**Recommended action:** Contact the **{county_display}** appraisal authority "
            "for protest procedures, deadlines, and the appropriate review board. "
            "Attach this document as your comparables evidence."
        )

    comp_rows = "\n".join(
        f"| {c['address']} | {c['sqft']:,} | {c['year_built']} | "
        f"${c['prev_value']:,} | ${c['curr_value']:,} | "
        f"{'▲' if c['yoy_change_pct'] > 0 else '▼'} {abs(c['yoy_change_pct']):.2f}% |"
        for c in stats["comps"]
    )

    today = _date.today().strftime("%B %d, %Y")

    return f"""# Property Tax Protest Evidence Package

**Property:** {subject['address']}
**Property ID:** {subject['propid']}
**Owner:** {subject['owner']}
**Tax Year:** {subject.get('curr_year', '')}
**Prepared:** {today}

---

## 1. Subject Property

| Field | Value |
|-------|-------|
| Address | {subject['address']} |
| Owner | {subject['owner']} |
| Neighborhood Code | {subject['neighborhood_code']} |
| Property Type | {subject['propcategorycode']} (Residential) |
| Size | {subject['sqft']:,} sq ft |
| Year Built | {subject['year_built']} |
| Homestead Exemption | {'Yes' if subject['has_homestead'] else 'No'} |
| **Prior-Year Appraised Value** | **${subj_prev:,}** |
| **Current Appraised Value** | **${subj_curr:,}** |
| **Dollar Increase** | **${subj_curr - subj_prev:,}** |
| **Percent Increase** | **+{subj_yoy:.2f}%** |

---

## 2. Comparable Property Analysis

Comparables sourced from: {source_label}, property type **{subject['propcategorycode']}**, size range **{size_min:,}–{size_max:,} sq ft** (±{size_tolerance_pct}% of subject).
New-construction properties (no prior-year appraisal value) were excluded.

| Address | Sq Ft | Yr Built | Prior Value | Current Value | Change |
|---------|-------|----------|------------|--------------|--------|
{comp_rows}

*{stats['count']} comparable properties analyzed.*

---

## 3. Statistical Summary

- **Comparable properties analyzed:** {stats['count']}
- **Median YoY change:** {comp_median:+.2f}%
- **Mean YoY change:** {stats['mean_yoy_pct']:+.2f}%
- **Std deviation:** {stats['stdev_yoy_pct']:.2f} percentage points
- **Properties that increased:** {stats['pct_increased']:.1f}%
- **Properties that decreased:** {stats['pct_decreased']:.1f}%
- **Subject percentile rank:** {percentile}th percentile among comparables (ranked {rank_below + 1} of {stats['count']} by YoY change)
- **Subject increase vs. comparable median:** **+{gap_pp:.2f} percentage points above peers**

---

## 4. Basis for Protest

The subject property's appraised value increased by **{subj_yoy:.2f}%**, while {stats['count']} comparable properties experienced a median change of **{comp_median:+.2f}%**. The subject's increase exceeds the comparable median by **{gap_pp:.2f} percentage points**.

{legal_block}

---

## 5. Requested Relief

We respectfully request that the appraised value of **${subj_curr:,}** be reduced to no more than **${target_value:,}** — the value consistent with applying the comparable-set median appreciation rate ({comp_median:+.2f}%) to the prior certified value of ${subj_prev:,}. This represents a reduction of **${reduction:,}** (**{reduction_pct:.1f}%**).

---

## 6. Data Provenance

All comparable data sourced from **{county_display} CAD** official certified appraisal records via the Texas Open Data Portal (data.texas.gov), dataset ID **{dataset_id}**, retrieved on {today}.
""".strip()


@mcp.tool()
def search_properties(address: Optional[str] = None, owner: Optional[str] = None, zip_code: Optional[str] = None, subdivision: Optional[str] = None, neighborhood_code: Optional[str] = None, limit: int = 10, county: str = "collin") -> str:
    """
    Search for real estate properties by address, owner name, zip code, subdivision, or neighborhood code.
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
    if subdivision:
        subdiv_pattern = _sanitize(subdivision.lower()).replace("*", "%")
        where_clauses.append(f"lower(legalabssubname) like '%{subdiv_pattern}%'")
    if neighborhood_code:
        where_clauses.append(f"nbhdcode = '{_sanitize(neighborhood_code)}'")

    if not where_clauses:
        return json.dumps({"error": "Must provide at least one search parameter (address, owner, zip_code, subdivision, or neighborhood_code)."})

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
def comp_investigator(property_id: str, county: str = "collin", size_tolerance_pct: int = 20) -> str:
    """
    Investigate whether a property's appraisal increase is consistent with comparable
    properties in the same neighborhood. If the increase is a statistical outlier,
    generates a formatted protest evidence document ready for submission to the
    appraisal review board.

    Returns JSON with:
    - subject: subject property details and YoY change
    - comps_source: "neighborhood" (preferred) or "zip" (fallback)
    - comps_count: number of comparable properties analyzed
    - comps_summary: median/mean/stdev YoY change and per-comp breakdown
    - determination: "warranted" | "not_warranted" | "insufficient_data" | "no_increase"
    - determination_reason: plain-English explanation of the result
    - evidence_document: (only present when determination == "not_warranted") a
      markdown protest evidence package including comparable data, statistical
      analysis, state-appropriate legal framing, and a requested relief amount
    """
    try:
        reg = get_registry(county)
        domain = reg["domain"]
        dataset_id = reg["appraisal_dataset"]
        state = reg.get("state", "")
        county_display = reg.get("display_name", county.title())
        _ensure_cache(domain, reg)

        # Step 1: Fetch subject property
        records = client.fetch_page(domain, dataset_id, limit=1,
                                    where=f"propid = '{_sanitize(property_id)}'")
        if not records:
            return json.dumps({"error": f"Property ID '{property_id}' not found."})

        raw = records[0]
        try:
            prev_val = float(raw.get("prevvalmarket", 0) or 0)
            curr_val = float(raw.get("currvalmarket", 0) or 0)
            sqft     = float(raw.get("imprvmainarea", 0) or 0)
        except (ValueError, TypeError):
            return json.dumps({"error": "Property has unparseable value fields."})

        if prev_val <= 0:
            return json.dumps({"error": "Property has no prior-year value — cannot compute year-over-year change."})

        subject = {
            "propid":             raw.get("propid", property_id),
            "address":            raw.get("situsconcat", ""),
            "owner":              raw.get("ownername", ""),
            "neighborhood_code":  raw.get("nbhdcode", ""),
            "situszip":           raw.get("situszip", ""),
            "propcategorycode":   raw.get("propcategorycode", ""),
            "sqft":               int(sqft),
            "year_built":         raw.get("imprvyearbuilt", ""),
            "prev_value":         int(prev_val),
            "curr_value":         int(curr_val),
            "yoy_change_pct":     round((curr_val - prev_val) / prev_val * 100, 2),
            "has_homestead":      bool(raw.get("exempthmstdflag", False)),
            "curr_year":          raw.get("currvalyear", ""),
        }

        # Step 2: No protest basis if value didn't increase
        if curr_val <= prev_val:
            return json.dumps({
                "subject": subject,
                "determination": "no_increase",
                "determination_reason": (
                    f"Value decreased or stayed flat "
                    f"({subject['yoy_change_pct']:+.2f}%). No protest basis."
                ),
            }, indent=2)

        # Step 3: Fetch comps — Tier 1 (neighborhood), Tier 2 (zip fallback)
        nbhd     = _sanitize(raw.get("nbhdcode", ""))
        situszip = _sanitize(raw.get("situszip", ""))
        cat      = _sanitize(raw.get("propcategorycode", "A"))
        size_min = max(1, int(sqft * (1 - size_tolerance_pct / 100)))
        size_max = int(sqft * (1 + size_tolerance_pct / 100))
        base_filters = (
            f"propcategorycode = '{cat}'"
            f" AND imprvmainarea > {size_min} AND imprvmainarea < {size_max}"
            f" AND prevvalmarket > 0 AND currvalmarket > 0"
            f" AND propid != '{_sanitize(property_id)}'"
        )

        comps_source = "neighborhood"
        comps_raw: List[Dict[str, Any]] = []

        if nbhd:
            comps_raw = client.fetch_page(domain, dataset_id, limit=50,
                                          where=f"nbhdcode = '{nbhd}' AND {base_filters}")

        if len(comps_raw) < 5 and situszip:
            comps_source = "zip"
            comps_raw = client.fetch_page(domain, dataset_id, limit=75,
                                          where=f"situszip = '{situszip}' AND {base_filters}")

        # Step 4: Compute statistics
        stats = _comp_stats(comps_raw)

        if stats["count"] < 5:
            return json.dumps({
                "subject": subject,
                "comps_source": comps_source,
                "comps_count": stats["count"],
                "determination": "insufficient_data",
                "determination_reason": (
                    f"Only {stats['count']} comparable properties found "
                    f"(minimum 5 required for a reliable comparison)."
                ),
            }, indent=2)

        # Step 5: Determine warrant
        comp_median = stats["median_yoy_pct"]
        comp_stdev  = stats["stdev_yoy_pct"]
        threshold   = max(comp_stdev, 3.0)
        subject_yoy = subject["yoy_change_pct"]
        gap_pp      = round(subject_yoy - comp_median, 2)
        is_outlier  = subject_yoy > (comp_median + threshold)

        determination = "not_warranted" if is_outlier else "warranted"
        reason = (
            f"Subject increased {subject_yoy:+.2f}% vs comparable median of "
            f"{comp_median:+.2f}% — {gap_pp:+.2f} pp above peers "
            f"(outlier threshold: {comp_median + threshold:.2f}%)."
        )

        result: Dict[str, Any] = {
            "subject":              subject,
            "comps_source":         comps_source,
            "comps_count":          stats["count"],
            "comps_summary":        stats,
            "determination":        determination,
            "determination_reason": reason,
        }

        if determination == "not_warranted":
            result["evidence_document"] = _build_evidence_doc(
                subject=subject,
                stats=stats,
                state=state,
                county_display=county_display,
                dataset_id=dataset_id,
                comps_source=comps_source,
                size_tolerance_pct=size_tolerance_pct,
            )

        return json.dumps(result, indent=2)

    except ValueError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:
        logger.error(f"comp_investigator error: {e}", exc_info=True)
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
