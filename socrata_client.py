import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import logging
from typing import List, Dict, Any, Optional
from config import SOCRATA_APP_TOKEN, SOCRATA_KEY_ID, SOCRATA_KEY_SECRET

logger = logging.getLogger("socrata-mcp.client")

class SocrataClient:
    def __init__(self, app_token: Optional[str] = None, key_id: Optional[str] = None, key_secret: Optional[str] = None):
        self.app_token = app_token or SOCRATA_APP_TOKEN
        self.key_id = key_id or SOCRATA_KEY_ID
        self.key_secret = key_secret or SOCRATA_KEY_SECRET
        self.session = self._build_session()
        
    def _build_session(self) -> requests.Session:
        session = requests.Session()
        
        if self.app_token:
            session.headers.update({"X-App-Token": self.app_token})
            
        if self.key_id and self.key_secret:
            session.auth = (self.key_id, self.key_secret)
            
        # Retry strategy for 429 (Rate Limit) and 50x (Server Errors)
        retries = Retry(
            total=3,
            backoff_factor=1,  # Wait 1s, 2s, 4s between retries
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        adapter = HTTPAdapter(max_retries=retries)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def fetch_page(self, domain: str, dataset_id: str, limit: int = 1000, offset: int = 0, select: str = None, where: str = None, order: str = None, group: str = None) -> List[Dict[str, Any]]:
        """Fetch a single page of results using SODA API."""
        url = f"https://{domain}/resource/{dataset_id}.json"
        params = {
            "$limit": limit,
            "$offset": offset
        }
        if select: params["$select"] = select
        if where: params["$where"] = where
        if order: params["$order"] = order
        if group: params["$group"] = group
        
        logger.info(f"Fetching {url} limit={limit} offset={offset}")
        response = self.session.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    def fetch_all(self, domain: str, dataset_id: str, select: str = None, where: str = None) -> List[Dict[str, Any]]:
        """Fetch all records by paginating through the dataset automatically (up to SODA limits)."""
        all_records = []
        limit = 50000  # Max SODA limit per page
        offset = 0
        
        while True:
            records = self.fetch_page(domain, dataset_id, limit=limit, offset=offset, select=select, where=where)
            if not records:
                break
            
            all_records.extend(records)
            if len(records) < limit:
                # We reached the last page (fewer records returned than the limit)
                break
            
            offset += limit
            
        logger.info(f"Successfully fetched {len(all_records)} total records from {dataset_id}")
        return all_records
