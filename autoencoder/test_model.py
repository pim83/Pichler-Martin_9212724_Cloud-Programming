"""Kleine fachliche Prüfungen für die gemeinsame Merkmalsberechnung."""

import unittest

import numpy as np

from model import extract_features


class FeatureTests(unittest.TestCase):
    def test_constant_signal_has_known_features(self):
        # Bei konstanten Werten entsprechen RMS und Spitze dem Absolutwert;
        # der Crest-Faktor ist eins. Die Achsenreihenfolge muss erhalten bleiben.
        signal = np.tile([2.0, -3.0, 4.0], (2000, 1))
        features = extract_features(signal, 10000, 0.1)
        expected = np.tile([2, 3, 4, 2, 3, 4, 1, 1, 1], (2, 1))
        np.testing.assert_allclose(features, expected)

    def test_zero_signal_is_finite(self):
        features = extract_features(np.zeros((1000, 3)), 10000, 0.1)
        np.testing.assert_array_equal(features, np.zeros((1, 9)))

    def test_impulse_remains_in_its_window(self):
        signal = np.zeros((2000, 3))
        signal[999, 0] = 10
        features = extract_features(signal, 10000, 0.1)
        self.assertAlmostEqual(features[0, 0], 10 / np.sqrt(1000))
        self.assertEqual(features[0, 3], 10)
        np.testing.assert_array_equal(features[1], np.zeros(9))

    def test_invalid_input_is_rejected(self):
        for signal in [np.zeros((999, 3)), np.zeros((1000, 2)), np.full((1000, 3), np.nan)]:
            with self.assertRaises(ValueError):
                extract_features(signal, 10000, 0.1)
        with self.assertRaises(ValueError):
            extract_features(np.zeros((1000, 3)), 10000, 0.10005)


if __name__ == "__main__":
    unittest.main()
