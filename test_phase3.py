import logging
import time
from config import logger
from geocoder import Geocoder

def main():
    logger.setLevel(logging.INFO)
    geo = Geocoder()
    
    # Test UC 3.1: Valid address
    print("\n--- Testing UC 3.1: Valid Address ---")
    start = time.time()
    coords = geo.geocode("250 Eldorado Pkwy, McKinney, TX 75069")
    print(f"Result: {coords} (Took {time.time() - start:.2f}s)")
    
    # Test UC 3.3: Invalid address graceful failure
    print("\n--- Testing UC 3.3: Invalid Address ---")
    start = time.time()
    coords3 = geo.geocode("FakeStreet XYZ 999999999 Nowhere")
    print(f"Result: {coords3} (Took {time.time() - start:.2f}s)")

if __name__ == "__main__":
    main()
