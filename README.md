# Socrata Real Estate MCP Server

A high-performance Model Context Protocol (MCP) server for querying real estate property and tax data from the Socrata SODA API (specifically tailored for `data.texas.gov` and Collin County CAD). 

This server solves Socrata's lack of native `JOIN` support by securely caching massive lookup tables (Neighborhoods and Taxing Entities) into a local atomic SQLite database, providing AI assistants with instantly-resolved, human-readable JSON outputs.

## Features & Functionality

The server exposes seven AI-ready MCP tools:

1. **`list_supported_locations`**: Browse geographic coverage hierarchically — state → county → cities with zip codes. Call with no arguments to see supported states, pass `state="TX"` to see counties, or pass `county="collin"` to get every city and zip code available in that county's dataset. City/zip results are cached in SQLite using the same TTL as other lookup tables.
2. **`search_properties`**: Search for properties via address, owner name, or zip code. Automatically resolves complex IDs into readable Neighborhood names and Taxing Entity combinations.
3. **`get_property_detail`**: Perform a deep dive into a specific property record using its unique `propid`.
4. **`query_properties_near`**: Translates English addresses into exact coordinates (using the free US Census Geocoder to avoid cloud-IP bans) to verify geospatial locations.
5. **`discover_county_datasets`**: Queries the Socrata Global Catalog (`api.us.socrata.com`) to dynamically discover available datasets by county name.
6. **`refresh_cache`**: On-demand manual rebuild of the local SQLite relational cache.
7. **`comp_investigator`**: Analyzes whether a property's year-over-year appraisal increase is consistent with comparable properties in the same neighborhood. Compares the subject against up to ±20% size-matched neighbors (falling back to zip code if the neighborhood has too few comps) and runs a statistical outlier test. Returns a `determination` of `warranted`, `not_warranted`, `insufficient_data`, or `no_increase`. When the increase is an outlier, also generates a ready-to-submit markdown protest evidence package — including a comparable-property table, statistical summary, Texas Tax Code §41.43 legal framing, and a specific requested relief amount.

---

## 🎯 Gap Analysis: What This Server Solves

Unlike generic Socrata MCP servers or direct REST API integrations, this server is specifically engineered to overcome the structural, relational, and geospatial limitations of open data portals:

| Feature / Gap | Raw Socrata API | Standard MCP Servers | This Real Estate MCP Server |
| :--- | :--- | :--- | :--- |
| **Relational Joins (`JOIN`)** | **None.** HTTP SODA has no relational join syntax over REST. | **None.** Standard MCPs can only query one dataset/table at a time. | **Resolved Locally.** Downloads and caches lookup tables (Neighborhoods, Taxing Entities) in a local SQLite database for instant, zero-latency joining. |
| **Geospatial Resolution** | Needs pre-computed coordinates (`lat`/`lon`) for queries like `within_circle`. | Cannot resolve addresses or locations to coordinates. | **Integrated Geocoder.** Resolves standard street addresses to GPS coordinates using the US Census Geocoding API (preventing cloud-IP rate-limiting/blocking). |
| **Code Translation** | Returns raw internal codes (e.g., Neighborhood `1001` or Tax Entity `GCO`). | Returns raw codes directly to the LLM, consuming context and reasoning. | **Human-Readable Outputs.** Translates abstract codes into actual entity names and adjustment values before presenting results to the LLM. |
| **Token Limit Overflow** | Returns raw JSON payloads that can exceed 100MB+ for large queries. | Dumps massive raw JSON payloads directly into the prompt context, causing crashes. | **Intelligent Payload Control.** Cleans and structures data, returning concise summaries and resolving relational fields to keep tokens low. |

---

## 🛠 Installation

1. Navigate to the project directory:
   ```bash
   cd /path/to/mcp-socrata-readonly
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

## ⚙️ Configuration

The server requires configuration via environment variables. How you provide these variables depends **entirely** on which Usage Mode you are using.

### 1. Embedded Mode (STDIO)
**Do NOT use a `.env` file.** AI clients (like Claude Desktop, Antigravity IDE, Cursor) spawn the MCP server from arbitrary system directories, meaning a local `.env` file in the project root often won't be found. 
Instead, you **must** pass environment variables directly in the client's configuration JSON using the `"env"` block.

### 2. Standalone (SSE) & Development Mode
**Use a `.env` file.** Because you are manually running the server from within the project's root directory, the server will automatically find and load variables from a local `.env` file. 

To set this up, copy the provided template:
```bash
cp env.template .env
```

### Configuration Variables

| Environment Variable | Description | Default / Fallback |
| :--- | :--- | :--- |
| `SOCRATA_APP_TOKEN` | Optional. Your Socrata App Token to bypass public API rate limits (highly recommended for production). | `None` (Public access) |
| `SOCRATA_KEY_ID` | Optional. Your Socrata API Key ID for Basic Authentication. | `None` |
| `SOCRATA_KEY_SECRET` | Optional. Your Socrata API Key Secret for Basic Authentication. | `None` |
| `USER_AGENT_EMAIL` | Optional. Email sent in the User-Agent header (required/polite for Nominatim fallbacks or other APIs). | `socrata_mcp_default@example.com` |
| `CACHE_TTL_DAYS` | Optional. The number of days before the local SQLite cache is considered expired. | `7` |

> [!NOTE]
> **Authentication Setup**:
> * To authenticate, you can either use an **App Token** (`SOCRATA_APP_TOKEN`) or an **API Key & Secret** pair (`SOCRATA_KEY_ID` and `SOCRATA_KEY_SECRET`).
> * You do **not** need both. If you only have the API Key & Secret, you can leave `SOCRATA_APP_TOKEN` blank, and the client will use HTTP Basic Authentication.

### Client Configuration Example (e.g., `claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "mcp-socrata-readonly": {
      "command": "/path/to/mcp-socrata-readonly/venv/bin/fastmcp",
      "args": ["run", "/path/to/mcp-socrata-readonly/main.py"],
      "env": {
        "SOCRATA_APP_TOKEN": "YOUR_SOCRATA_APP_TOKEN_HERE",
        "SOCRATA_KEY_ID": "YOUR_API_KEY_ID_HERE",
        "SOCRATA_KEY_SECRET": "YOUR_API_KEY_SECRET_HERE",
        "USER_AGENT_EMAIL": "your-email@example.com"
      }
    }
  }
}
```

### Claude Code Configuration:

For **Claude Code**, MCP servers are configured via the CLI using one of three scopes:

| Scope | Flag | Stored In | Visibility |
| :--- | :--- | :--- | :--- |
| Local (default) | `--scope local` | `~/.claude.json` (project-keyed) | You only, this project |
| User | `--scope user` | `~/.claude.json` (top-level) | You only, all projects |
| Project | `--scope project` | `.mcp.json` in project root | Everyone who clones the repo |

> [!NOTE]
> `mcpServers` in `.claude/settings.json` is **not** a valid MCP configuration location for Claude Code. That file is only for general settings (permissions, hooks, etc.). Always use `claude mcp add` or `.mcp.json`.

The recommended way is to use the Claude Code CLI (credentials stay private in `~/.claude.json`):

```bash
claude mcp add --scope local \
  -e SOCRATA_APP_TOKEN=YOUR_SOCRATA_APP_TOKEN_HERE \
  -e SOCRATA_KEY_ID=YOUR_API_KEY_ID_HERE \
  -e SOCRATA_KEY_SECRET=YOUR_API_KEY_SECRET_HERE \
  -e USER_AGENT_EMAIL=your-email@example.com \
  mcp-socrata-readonly \
  /path/to/mcp-socrata-readonly/venv/bin/fastmcp \
  run /path/to/mcp-socrata-readonly/main.py
```

To share the server config with your team (without credentials), use `--scope project`, which writes to `.mcp.json` in the project root — commit that file and let each developer supply their own credentials via `.env` or `claude mcp add --scope local`.

You can verify the server is connected with:
```bash
claude mcp list
```

---


## 🚀 Usage Modes

This server leverages `fastmcp` and can be run in three different modes depending on your architecture needs:

*   **Embedded Mode (STDIO)**: The AI client (e.g., Claude Desktop, Antigravity IDE, Cursor) runs the server as a child process and communicates via standard input/output. This is typically used for local, single-user setups. It's the most secure and frictionless method because the server starts and stops with the client, requiring no network ports.
*   **Standalone Mode (SSE / HTTP)**: The server runs independently as a long-running web process, communicating via Server-Sent Events over HTTP. This is required if the server and the AI client are on different machines, or if you want to expose a single server instance to multiple clients simultaneously over a network.
*   **Development Mode**: A built-in web UI to manually test the tools in a browser.

### 1. Embedded Mode (STDIO) - Recommended for AI Assistants
In embedded mode, the server communicates with your AI client directly through standard input/output.

**Configuration for Antigravity IDE:**
You can add this server in Antigravity IDE's MCP configuration settings using the following JSON:
```json
{
  "mcpServers": {
    "mcp-socrata-readonly": {
      "command": "/path/to/mcp-socrata-readonly/venv/bin/fastmcp",
      "args": ["run", "/path/to/mcp-socrata-readonly/main.py"],
      "env": {
        "SOCRATA_APP_TOKEN": "YOUR_SOCRATA_APP_TOKEN_HERE"
      }
    }
  }
}
```

**Configuration for other AI Clients (e.g., `claude_desktop_config.json`, Cursor):**
```json
{
  "mcpServers": {
    "mcp-socrata-readonly": {
      "command": "/path/to/mcp-socrata-readonly/venv/bin/fastmcp",
      "args": ["run", "/path/to/mcp-socrata-readonly/main.py"]
    }
  }
}
```

**Configuration for Claude Code:**

Add this configuration using the CLI command (see [Claude Code Configuration](#claude-code-configuration) for scope options):
```bash
claude mcp add --scope local \
  mcp-socrata-readonly \
  /path/to/mcp-socrata-readonly/venv/bin/fastmcp \
  run /path/to/mcp-socrata-readonly/main.py
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

## 🏗 Architecture & Data Flow

```mermaid
flowchart TD
    User(["User Prompt"]) --> |Query properties / tax info| Client["AI Client / LLM"]
    Client --> |MCP Tool Call| Server["Real Estate MCP Server"]

    subgraph Server ["Real Estate MCP Server"]
        Tools["MCP Tools: search_properties, get_property_detail, query_properties_near, ..."]
        
        subgraph Logic ["Execution Logic"]
            GeocoderClient["US Census Geocoder Client"]
            SODAClient["Socrata SODA Client"]
            DB[("Local SQLite Cache: socrata_cache.db")]
            Resolver["Relational Join & Code Resolver"]
        end
    end

    %% External Connections
    GeocoderClient <--> |Geocode Address| Census["US Census Geocoding API"]
    SODAClient <--> |SoQL Queries / Fetch Records| SODA_API["Socrata SODA API (data.texas.gov)"]
    
    %% Internal Flow
    Tools --> GeocoderClient
    Tools --> SODAClient
    SODAClient --> Resolver
    DB --> |Lookup Neighborhood & Tax Rates| Resolver
    Resolver --> |Enriched Human-Readable JSON| Client
```

---

## 🧪 Running Tests

A complete suite of integration tests is located in the `tests/` directory. You can run all tests using Python's built-in `unittest` module:

```bash
venv/bin/python -m unittest discover -s tests
```

---

## 📦 Packaging & Distribution

This server is fully configured as a standard Python package using `pyproject.toml`. It exposes a global console script `mcp-socrata` so it can be installed and run easily.

### Option A: Install Directly from GitHub
Others can install the server directly from GitHub without publishing to PyPI first:
```bash
pip install git+https://github.com/balamuru/mcp-socrata-readonly.git
```
Then configure it in the client config (e.g., `claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "mcp-socrata-readonly": {
      "command": "mcp-socrata",
      "env": {
        "SOCRATA_APP_TOKEN": "YOUR_SOCRATA_APP_TOKEN"
      }
    }
  }
}
```

### Option B: Build and Publish to PyPI
To publish the package so that others can install it via `pip install mcp-socrata-readonly`:

1. Install build tools:
   ```bash
   pip install --upgrade build twine
   ```
2. Build the package wheel and tarball:
   ```bash
   python -m build
   ```
3. Upload the package to PyPI (requires PyPI credentials):
   ```bash
   python -m twine upload dist/*
   ```

---

## 🗺 Multi-County Support & Caching Behavior

### 1. Collin County Specificity
This MCP server is pre-configured out-of-the-box for **Collin County, TX** (appraisal data, neighborhoods, and tax entities hosted on `data.texas.gov`).

### 2. How to Support Other Counties
To support other counties:
1. Locate the county's appraisal, neighborhood, and entity datasets on Socrata (e.g., Dallas County CAD or Travis County CAD on `data.texas.gov` or a separate portal).
2. Note their Socrata domain (e.g. `data.texas.gov`) and unique 9-character dataset IDs (e.g., `vffy-snc6`).
3. Add the new county configuration to the registry dictionary `COUNTY_REGISTRY` in `registry.py`:
   ```python
   "dallas": {
       "domain": "data.texas.gov",
       "appraisal_dataset": "xxxx-xxxx",
       "neighborhood_dataset": "yyyy-yyyy",
       "entity_dataset": "zzzz-zzzz",
   }
   ```
4. Now, the tools can be invoked with `county="dallas"` (e.g., `search_properties(address="123 Main St", county="dallas")`).

### 3. Concurrent County Access & Cache Isolation
* **Concurrent Execution**: Yes, you can query multiple registered counties concurrently by passing the corresponding `county` parameter in separate tool calls.
* **Cache Isolation**: The local SQLite cache (`socrata_cache.db`) namespaces all lookup caches (Neighborhoods and Taxing Entities) using unique Socrata **`dataset_id`** values (which are globally unique). This guarantees that even if multiple configured counties share the exact same Socrata domain (e.g., Collin County and a future Dallas County both hosted on `data.texas.gov`), their lookup tables will remain isolated and will never collide or overwrite each other in the database.

---

## Architecture Notes
* **Data Fetching:** SODA pagination limits are cleanly handled up to 50,000 records per page. `urllib3` retry logic protects against Socrata `429` (Rate Limit) and `500` HTTP exceptions.
* **Geocoding:** Defaults to the **US Census Geocoder** API. OpenStreetMap Nominatim is notoriously strict with blocking cloud datacenter IPs (403 Forbidden errors). The Census API requires no keys and handles cloud traffic gracefully.
