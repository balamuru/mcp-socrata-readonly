import os
import sqlite3
import time
from typing import List, Dict, Any, Callable
from config import logger, CACHE_TTL_DAYS

_CACHE_DIR = os.path.expanduser("~/.cache/mcp-socrata-readonly")
os.makedirs(_CACHE_DIR, exist_ok=True)
DB_PATH = os.path.join(_CACHE_DIR, "socrata_cache.db")

def get_connection() -> sqlite3.Connection:
    """Get a connection to the SQLite cache database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the SQLite tables if they do not exist."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Migrating old schema if needed (checking if old 'domain' column exists)
        try:
            cursor.execute("SELECT domain FROM metadata LIMIT 1")
            # If the above line runs without raising OperationalError, we have the old schema.
            # Drop old tables to migrate to dataset_id schema.
            logger.info("Migrating SQLite cache schema from domain key to dataset_id key...")
            cursor.execute("DROP TABLE IF EXISTS metadata")
            cursor.execute("DROP TABLE IF EXISTS neighborhoods")
            cursor.execute("DROP TABLE IF EXISTS entities")
        except sqlite3.OperationalError:
            # Table doesn't exist or is already migrated (no domain column)
            pass
            
        # Metadata table to track cache expiration
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS metadata (
                dataset_id TEXT,
                table_name TEXT,
                last_updated INTEGER,
                PRIMARY KEY (dataset_id, table_name)
            )
        ''')
        
        # Neighborhoods table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS neighborhoods (
                dataset_id TEXT,
                neighborhood_code TEXT,
                neighborhood_description TEXT,
                PRIMARY KEY (dataset_id, neighborhood_code)
            )
        ''')
        
        # Tax Entities table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS entities (
                dataset_id TEXT,
                entity_code TEXT,
                entity_description TEXT,
                tax_rate REAL,
                PRIMARY KEY (dataset_id, entity_code)
            )
        ''')

        # Cities/zip codes table (for list_supported_locations)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cities (
                dataset_id TEXT,
                city_name  TEXT,
                zip_code   TEXT,
                PRIMARY KEY (dataset_id, city_name, zip_code)
            )
        ''')
        conn.commit()

def is_cache_valid(dataset_id: str, table_name: str) -> bool:
    """Check if the cache for a specific table is still valid based on TTL."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT last_updated FROM metadata WHERE dataset_id = ? AND table_name = ?', (dataset_id, table_name))
        row = cursor.fetchone()
        
        if not row:
            return False
            
        last_updated = row['last_updated']
        age_seconds = time.time() - last_updated
        ttl_seconds = CACHE_TTL_DAYS * 24 * 60 * 60
        
        return age_seconds < ttl_seconds

def update_cache(dataset_id: str, table_name: str, records: List[Dict[str, Any]], insert_func: Callable[[sqlite3.Cursor, str, List[Dict[str, Any]]], None]):
    """Atomically update a cache table within a transaction."""
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            # Clear old records
            cursor.execute(f"DELETE FROM {table_name} WHERE dataset_id = ?", (dataset_id,))
            
            # Insert new records using the provided mapping function
            insert_func(cursor, dataset_id, records)
            
            # Update metadata
            now = int(time.time())
            cursor.execute('''
                INSERT INTO metadata (dataset_id, table_name, last_updated)
                VALUES (?, ?, ?)
                ON CONFLICT(dataset_id, table_name) DO UPDATE SET last_updated = excluded.last_updated
            ''', (dataset_id, table_name, now))
            
            conn.commit()
            logger.info(f"Successfully updated SQLite cache for {dataset_id}.{table_name}")
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update cache for {table_name}: {e}")
            raise

def insert_neighborhoods(cursor: sqlite3.Cursor, dataset_id: str, records: List[Dict[str, Any]]):
    """Mapping function for neighborhoods."""
    for r in records:
        code = r.get("nbhdcode")
        desc = r.get("nbhdname", "Unknown")
        if code:
            cursor.execute('''
                INSERT OR REPLACE INTO neighborhoods (dataset_id, neighborhood_code, neighborhood_description)
                VALUES (?, ?, ?)
            ''', (dataset_id, code, desc))

def insert_entities(cursor: sqlite3.Cursor, dataset_id: str, records: List[Dict[str, Any]]):
    """Mapping function for taxing entities."""
    for r in records:
        code = r.get("entitycode")
        desc = r.get("entityname", "Unknown")
        
        # Safe extraction of tax rate
        try:
            rate = float(r.get("tax_rate", 0.0))
        except (ValueError, TypeError):
            rate = 0.0
            
        if code:
            cursor.execute('''
                INSERT OR REPLACE INTO entities (dataset_id, entity_code, entity_description, tax_rate)
                VALUES (?, ?, ?, ?)
            ''', (dataset_id, code, desc, rate))

def insert_cities(cursor: sqlite3.Cursor, dataset_id: str, records: List[Dict[str, Any]]):
    """Mapping function for city/zip pairs from the appraisal dataset."""
    for r in records:
        city = (r.get("situscity") or "").strip().upper()
        zip_code = (r.get("situszip") or "").strip()
        if city and zip_code:
            cursor.execute('''
                INSERT OR REPLACE INTO cities (dataset_id, city_name, zip_code)
                VALUES (?, ?, ?)
            ''', (dataset_id, city, zip_code))

def get_cached_cities(dataset_id: str) -> List[Dict[str, Any]]:
    """Return all city/zip pairs for a dataset, grouped by city with sorted zip lists."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'SELECT city_name, zip_code FROM cities WHERE dataset_id = ? ORDER BY city_name, zip_code',
            (dataset_id,)
        )
        rows = cursor.fetchall()

    grouped: Dict[str, List[str]] = {}
    for row in rows:
        grouped.setdefault(row["city_name"], []).append(row["zip_code"])
    return [{"city": city, "zip_codes": zips} for city, zips in grouped.items()]

def get_cached_neighborhood(dataset_id: str, code: str) -> str:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT neighborhood_description FROM neighborhoods WHERE dataset_id = ? AND neighborhood_code = ?', (dataset_id, code))
        row = cursor.fetchone()
        return row['neighborhood_description'] if row else code

def get_cached_entity(dataset_id: str, code: str) -> Dict[str, Any]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT entity_description, tax_rate FROM entities WHERE dataset_id = ? AND entity_code = ?', (dataset_id, code))
        row = cursor.fetchone()
        if row:
            return {"name": row['entity_description'], "rate": row['tax_rate']}
        return {"name": code, "rate": 0.0}

# Initialize tables when module is imported
init_db()
