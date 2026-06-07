# Gap Analysis: Socrata REST API vs. Existing Socrata MCP Servers
## For Real Estate Data Reading (Focus: Collin County, TX)

This analysis evaluates the gap between what the native **Socrata Open Data (SODA) REST API** provides and what is supported by existing **Socrata MCP servers** (e.g., `Thomas-TyTech/Socrata-MCP` or `@cyanheads/socrata-mcp-server`), specifically in the context of reading and analyzing real estate appraisal data.

---

## 1. Feature Comparison Table

| Capability / Feature | Socrata SODA REST API | Existing Socrata MCP Servers | Gap / Analysis |
| :--- | :--- | :--- | :--- |
| **Data Format Support** | JSON, CSV, XML, RDF, GeoJSON, XLS | JSON, CSV, GeoJSON (returned as text strings) | **Low Gap:** LLMs work best with JSON/CSV. However, large GeoJSON objects are bulky and hard for LLMs to digest directly. |
| **Catalog / Dataset Discovery** | Rich Discovery API (`/api/catalog/v1`) with sorting by relevance/views, and filtering by tags, domain, and type. | Keyword search (`search_datasets`) limited to a specific domain or basic string matching. | **Medium Gap:** Portals like the Texas Open Data Portal (`data.texas.gov`) host thousands of datasets. Existing MCPs struggle to locate related datasets (e.g., matching appraisal tables with entity rate tables) without user intervention. |
| **Authentication & Rate Limits** | Public access, App Tokens (`X-App-Token`), HTTP Basic Auth, and OAuth 2.0. | Single static App Token configured via environment variables at server startup. | **Medium Gap:** Cannot easily pass user-specific tokens dynamically or read private datasets without redeploying the MCP. |
| **SoQL Query Features** | Full support for `$select`, `$where`, `$order`, `$limit`, `$offset`, `$group`, `$having`, `$q`, and `$query` (subqueries). | Executes SoQL query strings directly via a tool (e.g., `query_dataset`). | **Low Gap:** Excellent SQL-like expressiveness, but the burden of writing complex SoQL syntax falls entirely on the LLM. |
| **Spatial / Geospatial Queries** | Server-side geocoding and GIS functions: `within_circle`, `within_box`, `within_polygon`, `distance_in_meters`, `intersects`. | Supports passing spatial conditions in SoQL query strings, but has no helper tools. | **High Gap:** The LLM cannot translate an address like `"123 Main St, McKinney, TX"` into GPS coordinates (`lat`/`lon`) or school district boundaries to construct a GIS query. |
| **Join Operations** | **No native `$join` parameter over HTTP SODA.** Joins are only supported internally in the Enterprise Canvas/Query Editor. | None. Standard MCP servers can only query one dataset at a time. | **High Gap:** Real estate data is normalized (e.g., CCAD maps neighborhood IDs to adjustments, and taxing entity IDs to rates). LLMs must issue multiple queries and perform client-side joins in context. |
| **Large Payload Handling** | Supports pagination up to 50k records per page, but payloads can exceed 100MB. | Raw data dump. Standard tools retrieve data and dump it directly into the prompt context. | **High Gap:** Collin County Appraisal Data contains hundreds of thousands of parcels. Querying raw data easily overflows the LLM's context window. |

---

## 2. Key Gaps for Real Estate Data Queries

Real estate analysis (specifically for **Collin County, TX**, via the Texas Open Data Portal at `data.texas.gov`) exposes three critical gaps in standard MCP implementations:

### A. Geocoding & Geospatial Operations (Crucial)
Real estate queries are heavily location-dependent (e.g., *"Find the average home value within 2 miles of McKinney High School"*).
* **The REST API** supports: `within_circle(location, lat, lon, radius_in_meters)`.
* **The Existing MCP** does not perform geocoding.
* **The Gap:** The LLM cannot resolve `"McKinney High School"` or an arbitrary address to its `(lat, lon)` values, making spatial queries unusable without external tools.

### B. Normalized Code Joins (Lookups)
The Collin Central Appraisal District (CCAD) certified data publishes separate, normalized tables on `data.texas.gov`:
1. `Collin CAD Appraisal Data - 2025` (main dataset - lists properties, land sizes, and code values).
2. `Collin CAD Neighborhood List` (translates neighborhood codes to valuation adjustments).
3. `Collin CAD Entity List` (translates entity codes like `GCO` to taxing authorities like `Collin County` and tax rates).

* **The REST API** requires client-side joins because the HTTP endpoints do not support relational SQL Joins.
* **The Existing MCP** forces the LLM to make 3 separate network calls and manually join them. This consumes significant context window space.
* **The Gap:** There is no automated local join or code translation utility.

### C. Context Overrun on Large Datasets
Collin County has over 350,000 parcels. A query like *"Show me all single-family homes in zip code 75070"* will return thousands of rows.
* **The REST API** will happily return a 15MB JSON file.
* **The Existing MCP** will dump the entire payload into the prompt, crashing the conversation or exceeding token limits.
* **The Gap:** Standard MCP servers lack intelligent **data aggregation, binning, or pagination summaries** before returning the results to the LLM.

---

## 3. Proposal: A Specialized Read-Only Real Estate MCP Server

To bridge these gaps, you should build a specialized, read-only MCP server tailored to county appraisal data. It would use standard SODA requests under the hood but add local helper steps:

```mermaid
flowchart TD
    User([User Prompt: "Find properties near 123 Main St"]) --> LLM[AI Assistant]
    LLM --> |Tool Call: query_properties_near| RealEstateMCP[Custom Real Estate MCP Server]
    
    subgraph RealEstateMCP [Real Estate MCP Server]
        Geocoder[1. Local Geocoding Helper]
        Registry[2. Regional Registry Map]
        QueryBuilder[3. SoQL Query Builder]
        Joiner[4. Code Resolver / Local Joiner]
        Summarizer[5. Data Aggregator]
    end

    GeocodingAPI[(Nominatim / Maps API)]
    SODA[Socrata SODA API]
    
    Geocoder <--> |Geocode Address| GeocodingAPI
    Registry --> |Resolve "Collin County" to data.texas.gov| QueryBuilder
    QueryBuilder --> |Fetch raw data| SODA
    SODA --> |Raw records| Joiner
    Joiner --> |Lookup codes & merge| Summarizer
    Summarizer --> |Clean & condensed summary| LLM
```

### Recommended Tools for Your Custom MCP Server

1. **`search_properties`**
   * **Purpose:** High-level search for property records.
   * **Parameters:** `county`, `state`, `owner_name`, `address_keyword`, `zip_code`.
   * **Logic:** Automatically resolves the target county to the correct Socrata domain (e.g., `Collin County, TX` -> `data.texas.gov`) and dataset ID, issues the query, and formats the output.

2. **`query_properties_geospatial`**
   * **Purpose:** Query properties within a radius or bounding box.
   * **Parameters:** `address`, `radius_miles`, `property_type` (e.g., residential, commercial).
   * **Logic:** Internally geocodes the `address` to `(lat, lon)` using a free service (like OSM/Nominatim), calculates the distance in meters, and queries SODA using `within_circle(location, lat, lon, meters)`.

3. **`get_property_detail`**
   * **Purpose:** Get full details for a single parcel, resolving all codes.
   * **Parameters:** `parcel_id` or `property_id`.
   * **Logic:** Fetches the parcel record, fetches lookup tables (Neighborhood, Entity tax exemptions), merges the data locally, and returns a clean, fully-joined JSON response.

4. **`get_market_trends`**
   * **Purpose:** Run analytical aggregations directly on Socrata without pulling raw row data.
   * **Parameters:** `county`, `zip_code`, `property_type`.
   * **Logic:** Formats a grouped SoQL query (e.g. `SELECT zip_code, AVG(market_value), COUNT(*) GROUP BY zip_code`) so only the aggregated statistics are sent back, avoiding token overflow.
