"""
Unit tests for the haversine distance helper (utils/geo.py).
"""

import unittest

from utils.geo import calculate_distance


class CalculateDistanceTests(unittest.TestCase):
    def test_north_south_offset_is_measured(self):
        # One degree of latitude is ~111.2 km on a 6,371 km sphere.
        self.assertAlmostEqual(calculate_distance(7.0, 125.0, 8.0, 125.0), 111195, delta=5)

    def test_east_west_offset_at_equator(self):
        self.assertAlmostEqual(calculate_distance(0.0, 125.0, 0.0, 126.0), 111195, delta=5)

    def test_short_panabo_distance(self):
        # ~340 m due north of Panabo City Hall area (the default scan radius).
        self.assertAlmostEqual(calculate_distance(7.3000, 125.6800, 7.3030577, 125.6800), 340, delta=1)

    def test_zero_distance(self):
        self.assertEqual(calculate_distance(7.3, 125.68, 7.3, 125.68), 0.0)


if __name__ == "__main__":
    unittest.main()
