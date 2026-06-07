import sqlite3
import time
from typing import List, Dict, Any, Callable
from config import logger, CACHE_TTL_DAYS

DB_PATH = "socrata_cache.db"

def get_connection() -> sqlite3.Connection:
    """Get a connection to the SQLite cache database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the SQLite tables if they do not exist."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Metadata table to track cache expiration
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS metadata (
                domain TEXT,
                table_name TEXT,
                last_updated INTEGER,
                PRIMARY KEY (domain, table_name)
            )
        ''')
        
        # Neighborhoods table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS neighborhoods (
                domain TEXT,
                neighborhood_code TEXT,
                neighborhood_description TEXT,
                PRIMARY KEY (domain, neighborhood_code)
            )
        ''')
        
        # Tax Entities table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS entities (
                domain TEXT,
                entity_code TEXT,
                entity_description TEXT,
                tax_rate REAL,
                PRIMARY KEY (domain, entity_code)
            )
        ''')
        conn.commit()

def is_cache_valid(domain: str, table_name: str) -> bool:
    """Check if the cache for a specific table is still valid based on TTL."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT last_updated FROM metadata WHERE domain = ? AND table_name = ?', (domain, table_name))
        row = cursor.fetchone()
        
        if not row:
            return False
            
        last_updated = row['last_updated']
        age_seconds = time.time() - last_updated
        ttl_seconds = CACHE_TTL_DAYS * 24 * 60 * 60
        
        return age_seconds < ttl_seconds

def update_cache(domain: str, table_name: str, records: List[Dict[str, Any]], insert_func: Callable[[sqlite3.Cursor, str, List[Dict[str, Any]]], None]):
    """Atomically update a cache table within a transaction."""
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            # Clear old records
            cursor.execute(f"DELETE FROM {table_name} WHERE domain = ?", (domain,))
            
            # Insert new records using the provided mapping function
            insert_func(cursor, domain, records)
            
            # Update metadata
            now = int(time.time())
            cursor.execute('''
                INSERT INTO metadata (domain, table_name, last_updated)
                VALUES (?, ?, ?)
                ON CONFLICT(domain, table_name) DO UPDATE SET last_updated = excluded.last_updated
            ''', (domain, table_name, now))
            
            conn.commit()
            logger.info(f"Successfully updated SQLite cache for {domain}.{table_name}")
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update cache for {table_name}: {e}")
            raise

def insert_neighborhoods(cursor: sqlite3.Cursor, domain: str, records: List[Dict[str, Any]]):
    """Mapping function for neighborhoods."""
    for r in records:
        code = r.get("nbhdcode")
        desc = r.get("nbhdname", "Unknown")
        if code:
            cursor.execute('''
                INSERT OR REPLACE INTO neighborhoods (domain, neighborhood_code, neighborhood_description)
                VALUES (?, ?, ?)
            ''', (domain, code, desc))

def insert_entities(cursor: sqlite3.Cursor, domain: str, records: List[Dict[str, Any]]):
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
                INSERT OR REPLACE INTO entities (domain, entity_code, entity_description, tax_rate)
                VALUES (?, ?, ?, ?)
            ''', (domain, code, desc, rate))

def get_cached_neighborhood(domain: str, code: str) -> str:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT neighborhood_description FROM neighborhoods WHERE domain = ? AND neighborhood_code = ?', (domain, code))
        row = cursor.fetchone()
        return row['neighborhood_description'] if row else code

def get_cached_entity(domain: str, code: str) -> Dict[str, Any]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT entity_description, tax_rate FROM entities WHERE domain = ? AND entity_code = ?', (domain, code))
        row = cursor.fetchone()
        if row:
            return {"name": row['entity_description'], "rate": row['tax_rate']}
        return {"name": code, "rate": 0.0}

# Initialize tables when module is imported
init_db()
