import unittest
import json
from main import search_properties, get_property_detail, discover_county_datasets

class TestMCPApi(unittest.TestCase):
    def test_discover_county_datasets(self):
        datasets_str = discover_county_datasets("Collin")
        datasets = json.loads(datasets_str)
        self.assertIsInstance(datasets, list)
        self.assertGreater(len(datasets), 0)
        self.assertIn('name', datasets[0])
        self.assertIn('id', datasets[0])
        
    def test_search_properties_and_detail(self):
        results_str = search_properties(address="ELDORADO", limit=1)
        results = json.loads(results_str)
        self.assertIsInstance(results, list)
        if results:
            prop = results[0]
            self.assertIn('situsconcat', prop)
            self.assertIn('propid', prop)
            
            # Get property detail
            propid = prop.get('propid')
            detail_str = get_property_detail(propid)
            detail = json.loads(detail_str)
            self.assertIsInstance(detail, dict)
            self.assertEqual(detail.get('propid'), propid)

if __name__ == "__main__":
    unittest.main()
