# Socrata Real Estate MCP Server

A high-performance Model Context Protocol (MCP) server for querying real estate property and tax data from the Socrata SODA API (specifically tailored for `data.texas.gov` and Collin County CAD). 

This server solves Socrata's lack of native `JOIN` support by securely caching massive lookup tables (Neighborhoods and Taxing Entities) into a local atomic SQLite database, providing AI assistants with instantly-resolved, human-readable JSON outputs.

## Features & Functionality

The server exposes five AI-ready MCP tools:

1. **`search_properties`**: Search for properties via address, owner name, or zip code. Automatically resolves complex IDs into readable Neighborhood names and Taxing Entity combinations.
2. **`get_property_detail`**: Perform a deep dive into a specific property record using its unique `propid`.
3. **`query_properties_near`**: Translates English addresses into exact coordinates (using the free US Census Geocoder to avoid cloud-IP bans) to verify geospatial locations.
4. **`discover_county_datasets`**: Queries the Socrata Global Catalog (`api.us.socrata.com`) to dynamically discover available datasets by county name.
5. **`refresh_cache`**: On-demand manual rebuild of the local SQLite relational cache.

---

## 🛠 Installation

1. Navigate to the project directory:
   ```bash
   cd /home/vinayb/CodeProjects/mcp-socrate-readonly
   ```
2. Create the Python virtual environment:
   ```bash
   python3 -m venv venv
   ```
3. Install the required dependencies:
   ```bash
   venv/bin/pip install -r requirements.txt
   ```

---

## 🚀 Usage Modes

This server leverages `fastmcp` and can be run in **Embedded Mode** (STDIO), **Standalone Mode** (SSE), or **Development Mode**.

### 1. Embedded Mode (STDIO) - Recommended for AI Assistants
In embedded mode, the server communicates with your AI client (like Claude Desktop, Cursor, or Cline) directly through standard input/output. This is the most secure and frictionless way to use the server.

**Configuration for your AI Client (e.g., `claude_desktop_config.json`):**
```json
{
  "mcpServers": {
    "socrata-real-estate": {
      "command": "/home/vinayb/CodeProjects/mcp-socrate-readonly/venv/bin/fastmcp",
      "args": ["run", "/home/vinayb/CodeProjects/mcp-socrate-readonly/main.py"]
    }
  }
}
```

### 2. Standalone Mode (SSE / HTTP)
If you want to host this MCP server independently, across a network, or expose it to multiple clients simultaneously, you can run it via Server-Sent Events (SSE). 

Start the server on port `8000`:
```bash
venv/bin/fastmcp run main:mcp --transport sse --port 8000
```
* Clients can now connect to this MCP server via `http://localhost:8000/sse`.

### 3. Development Mode (Built-in Web UI)
If you just want to test the tools manually in your web browser without an AI assistant, you can launch the FastMCP Inspector UI.

```bash
venv/bin/fastmcp dev main:mcp
```
* This will spin up a local web server and open a beautiful UI where you can input parameters and test the tools visually.

---

## Architecture Notes
* **Data Fetching:** SODA pagination limits are cleanly handled up to 50,000 records per page. `urllib3` retry logic protects against Socrata `429` (Rate Limit) and `500` HTTP exceptions.
* **Geocoding:** Defaults to the **US Census Geocoder** API. OpenStreetMap Nominatim is notoriously strict with blocking cloud datacenter IPs (403 Forbidden errors). The Census API requires no keys and handles cloud traffic gracefully.
