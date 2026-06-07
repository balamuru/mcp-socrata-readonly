import unittest
from geocoder import Geocoder

class TestGeocoder(unittest.TestCase):
    def setUp(self):
        self.geocoder = Geocoder()
        
    def test_valid_address(self):
        coords = self.geocoder.geocode("250 Eldorado Pkwy, McKinney, TX 75069")
        self.assertIsNotNone(coords)
        self.assertEqual(len(coords), 2)
        self.assertIsInstance(coords[0], float)
        self.assertIsInstance(coords[1], float)
        
    def test_invalid_address(self):
        coords = self.geocoder.geocode("FakeStreet XYZ 999999999 Nowhere")
        self.assertIsNone(coords)

if __name__ == "__main__":
    unittest.main()
