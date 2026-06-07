import unittest
import database
from socrata_client import SocrataClient
from registry import get_registry

class TestDatabaseCache(unittest.TestCase):
    def setUp(self):
        self.county = "collin"
        self.reg = get_registry(self.county)
        self.domain = self.reg["domain"]
        self.client = SocrataClient()
        
    def test_cache_validation_and_retrieval(self):
        # Ensure database is updated/populated if invalid
        if not database.is_cache_valid(self.domain, "neighborhoods"):
            records = self.client.fetch_all(self.domain, self.reg["neighborhood_dataset"])
            database.update_cache(self.domain, "neighborhoods", records, database.insert_neighborhoods)
            
        if not database.is_cache_valid(self.domain, "entities"):
            records = self.client.fetch_all(self.domain, self.reg["entity_dataset"])
            database.update_cache(self.domain, "entities", records, database.insert_entities)
            
        self.assertTrue(database.is_cache_valid(self.domain, "neighborhoods"))
        self.assertTrue(database.is_cache_valid(self.domain, "entities"))
        
        # Test retrieve
        nh_code = database.get_cached_neighborhood(self.domain, "10A")
        self.assertIsInstance(nh_code, str)
            
        ent_code = database.get_cached_entity(self.domain, "GCO")
        self.assertIsInstance(ent_code, dict)
        self.assertIn('name', ent_code)
        self.assertIn('rate', ent_code)

if __name__ == "__main__":
    unittest.main()
