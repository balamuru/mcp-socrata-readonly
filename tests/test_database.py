import unittest
import database
from socrata_client import SocrataClient
from registry import get_registry

class TestDatabaseCache(unittest.TestCase):
    def setUp(self):
        self.reg_collin = get_registry("collin")
        self.reg_test = get_registry("collin_test")
        self.client = SocrataClient()
        
    def test_cache_validation_and_retrieval(self):
        domain = self.reg_collin["domain"]
        nbhd_id = self.reg_collin["neighborhood_dataset"]
        entity_id = self.reg_collin["entity_dataset"]
        
        # Ensure database is updated/populated if invalid
        if not database.is_cache_valid(nbhd_id, "neighborhoods"):
            records = self.client.fetch_all(domain, nbhd_id)
            database.update_cache(nbhd_id, "neighborhoods", records, database.insert_neighborhoods)
            
        if not database.is_cache_valid(entity_id, "entities"):
            records = self.client.fetch_all(domain, entity_id)
            database.update_cache(entity_id, "entities", records, database.insert_entities)
            
        self.assertTrue(database.is_cache_valid(nbhd_id, "neighborhoods"))
        self.assertTrue(database.is_cache_valid(entity_id, "entities"))
        
        # Test retrieve
        nh_code = database.get_cached_neighborhood(nbhd_id, "10A")
        self.assertIsInstance(nh_code, str)
            
        ent_code = database.get_cached_entity(entity_id, "GCO")
        self.assertIsInstance(ent_code, dict)
        self.assertIn('name', ent_code)
        self.assertIn('rate', ent_code)

    def test_multicounty_no_collision(self):
        # We write test data to 'collin' and 'collin_test' caches on same domain
        # and verify they don't overwrite each other because they use separate dataset_ids.
        nbhd_collin = self.reg_collin["neighborhood_dataset"]
        nbhd_test = self.reg_test["neighborhood_dataset"]
        
        mock_collin_records = [{"nbhdcode": "CODE_A", "nbhdname": "Collin Neighborhood"}]
        mock_test_records = [{"nbhdcode": "CODE_A", "nbhdname": "Test Neighborhood"}]
        
        # Populate caches
        database.update_cache(nbhd_collin, "neighborhoods", mock_collin_records, database.insert_neighborhoods)
        database.update_cache(nbhd_test, "neighborhoods", mock_test_records, database.insert_neighborhoods)
        
        # Retrieve and check
        res_collin = database.get_cached_neighborhood(nbhd_collin, "CODE_A")
        res_test = database.get_cached_neighborhood(nbhd_test, "CODE_A")
        
        self.assertEqual(res_collin, "Collin Neighborhood")
        self.assertEqual(res_test, "Test Neighborhood")

if __name__ == "__main__":
    unittest.main()
