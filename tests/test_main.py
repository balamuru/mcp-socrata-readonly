import unittest
import json
from main import search_properties, get_property_detail, discover_county_datasets, list_supported_locations

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

            propid = prop.get('propid')
            detail_str = get_property_detail(propid)
            detail = json.loads(detail_str)
            self.assertIsInstance(detail, dict)
            self.assertEqual(detail.get('propid'), propid)

    # --- list_supported_locations ---

    def test_list_supported_locations_no_args_returns_states(self):
        result = json.loads(list_supported_locations())
        self.assertEqual(result["level"], "states")
        self.assertIn("supported_states", result)
        self.assertIsInstance(result["supported_states"], list)
        self.assertIn("TX", result["supported_states"])

    def test_list_supported_locations_state_returns_counties(self):
        result = json.loads(list_supported_locations(state="TX"))
        self.assertEqual(result["level"], "counties")
        self.assertEqual(result["state"], "TX")
        self.assertIsInstance(result["counties"], list)
        self.assertGreater(len(result["counties"]), 0)
        county = result["counties"][0]
        self.assertIn("key", county)
        self.assertIn("display_name", county)
        self.assertIn("state", county)

    def test_list_supported_locations_unknown_state_returns_error(self):
        result = json.loads(list_supported_locations(state="ZZ"))
        self.assertIn("error", result)

    def test_list_supported_locations_county_returns_cities(self):
        result = json.loads(list_supported_locations(county="collin"))
        self.assertEqual(result["level"], "cities")
        self.assertEqual(result["county"], "collin")
        self.assertIn("display_name", result)
        self.assertIn("state", result)
        self.assertIsInstance(result["cities"], list)
        self.assertGreater(len(result["cities"]), 0)
        city = result["cities"][0]
        self.assertIn("city", city)
        self.assertIn("zip_codes", city)
        self.assertIsInstance(city["zip_codes"], list)
        self.assertGreater(len(city["zip_codes"]), 0)
        city_names = [c["city"] for c in result["cities"]]
        self.assertIn("ALLEN", city_names)
        self.assertIn("FRISCO", city_names)
        self.assertIn("MCKINNEY", city_names)

    def test_list_supported_locations_invalid_county_returns_error(self):
        result = json.loads(list_supported_locations(county="atlantis"))
        self.assertIn("error", result)

if __name__ == "__main__":
    unittest.main()
