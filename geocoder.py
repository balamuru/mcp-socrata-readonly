import requests
import logging
from typing import Optional, Tuple
from config import logger

class Geocoder:
    def __init__(self):
        # US Census Geocoder does not have a strict 1 req/sec limit, but we should still be polite.
        # No API key required.
        pass

    def geocode(self, address: str) -> Optional[Tuple[float, float]]:
        """
        Translates a natural language address into (latitude, longitude) using the US Census Geocoder.
        Returns None if the address cannot be found.
        """
        url = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
        params = {
            "address": address,
            "benchmark": "Public_AR_Current",
            "format": "json"
        }
        
        logger.info(f"Geocoding address via US Census: '{address}'")
        try:
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            matches = data.get("result", {}).get("addressMatches", [])
            if not matches:
                logger.warning(f"Address not found: '{address}'")
                return None
                
            # Census returns x for longitude and y for latitude
            coords = matches[0].get("coordinates", {})
            lon = float(coords.get("x"))
            lat = float(coords.get("y"))
            logger.info(f"Geocoded '{address}' to ({lat}, {lon})")
            return (lat, lon)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Geocoding network error for '{address}': {e}")
            return None
        except Exception as e:
            logger.error(f"Geocoding failed for '{address}': {e}")
            return None
