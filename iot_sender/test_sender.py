"""Lokale Tests ohne Azure-Verbindung und ohne Zugangsschlüssel."""

import hashlib
from pathlib import Path
import sys
import unittest

import numpy as np
from azure.iot.device import Message

from send_measurement import DEFAULT_FILE, load_measurement, make_chunks

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "autoencoder"))
from model import extract_features, load_model, reconstruction_errors


class SenderTests(unittest.TestCase):
    def test_roundtrip_and_inference(self):
        model = load_model(ROOT / "autoencoder/modell_v2/autoencoder.npz")
        for name in ("messung_gut.npy", "messung_schlecht.npy"):
            with self.subTest(measurement=name):
                original = load_measurement(DEFAULT_FILE.with_name(name))
                chunks = list(make_chunks(original, "test-measurement"))
                self.assertEqual(len(chunks), 60)
                restored = []
                window_features = []
                for index, (body, props) in enumerate(chunks):
                    self.assertEqual(len(body), 120000)
                    self.assertEqual(int(props["chunk_index"]), index)
                    self.assertEqual(int(props["chunk_count"]), 60)
                    self.assertEqual(props["sha256"], hashlib.sha256(body).hexdigest())
                    # SDK akzeptiert denselben binären Nachrichtentyp wie im Sender.
                    message = Message(body)
                    message.custom_properties.update(props)
                    decoded = np.frombuffer(message.data, dtype="<f4").reshape(-1, 3)
                    restored.append(decoded)
                    window_features.append(extract_features(decoded, 10000, 0.1))
                np.testing.assert_array_equal(np.concatenate(restored), original)
                full = extract_features(original, 10000, 0.1)
                streamed = np.concatenate(window_features)
                np.testing.assert_array_equal(streamed, full)
                np.testing.assert_allclose(reconstruction_errors(streamed, model),
                                           reconstruction_errors(full, model), rtol=1e-12)

    def test_labels_are_rejected(self):
        with self.assertRaises((FileNotFoundError, ValueError)):
            load_measurement(DEFAULT_FILE.with_name("messung_gut_labels.npy"))


if __name__ == "__main__":
    unittest.main()
