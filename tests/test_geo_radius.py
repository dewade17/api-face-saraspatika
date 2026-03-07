import unittest

from app.utils.geo import haversine_m, is_within_radius_m


class GeoRadiusValidationTest(unittest.TestCase):
    def test_haversine_same_point_is_zero(self):
        distance_m = haversine_m(115.216667, -8.65, 115.216667, -8.65)
        self.assertAlmostEqual(distance_m, 0.0, places=6)

    def test_is_within_radius_true_when_inside(self):
        # Delta latitude 0.0004 derajat ~ 44 meter
        self.assertTrue(is_within_radius_m(0.0, 0.0, 0.0, 0.0004, 50.0))

    def test_is_within_radius_true_on_boundary(self):
        boundary_distance = haversine_m(0.0, 0.0, 0.0, 0.0004)
        self.assertTrue(is_within_radius_m(0.0, 0.0, 0.0, 0.0004, boundary_distance))

    def test_is_within_radius_false_when_outside(self):
        # Delta latitude 0.001 derajat ~ 111 meter
        self.assertFalse(is_within_radius_m(0.0, 0.0, 0.0, 0.001, 100.0))

    def test_is_within_radius_raises_for_negative_radius(self):
        with self.assertRaises(ValueError):
            is_within_radius_m(0.0, 0.0, 0.0, 0.001, -1.0)


if __name__ == "__main__":
    unittest.main()
