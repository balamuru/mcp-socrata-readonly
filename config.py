import os
import logging
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

# Set up global logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("socrata-mcp")

# Environment configurations
SOCRATA_APP_TOKEN = os.getenv("SOCRATA_APP_TOKEN", None)
# Used for Nominatim geocoding (they require an email in the User-Agent)
USER_AGENT_EMAIL = os.getenv("USER_AGENT_EMAIL", "socrata_mcp_default@example.com")
# Cache expiration time
CACHE_TTL_DAYS = int(os.getenv("CACHE_TTL_DAYS", "7"))
