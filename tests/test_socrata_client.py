import unittest
from socrata_client import SocrataClient

class TestSocrataClient(unittest.TestCase):
    def setUp(self):
        self.client = SocrataClient()
        
    def test_fetch_page(self):
        # Fetching 5 records from Collin CAD Entity List
        records = self.client.fetch_page("data.texas.gov", "rwqz-r4mp", limit=5)
        self.assertIsNotNone(records)
        self.assertLessEqual(len(records), 5)
        if records:
            self.assertIn('entitycode', records[0])
            self.assertIn('entityname', records[0])
            
    def test_fetch_all(self):
        # Fetching all records from Collin CAD Entity List (typically small lookup table)
        all_records = self.client.fetch_all("data.texas.gov", "rwqz-r4mp")
        self.assertIsNotNone(all_records)
        self.assertGreater(len(all_records), 0)

if __name__ == "__main__":
    unittest.main()
