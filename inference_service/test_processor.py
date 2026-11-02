"""Persistenz, Wiederholung und Fehlerfälle mit echten Testmessdaten prüfen."""

import io
import tempfile
import unittest
import uuid
from copy import deepcopy
from unittest.mock import Mock
from pathlib import Path

import numpy as np

from autoencoder.model import load_model, analyze
from iot_sender.send_measurement import load_measurement, make_chunks
from inference_service.local_check import FileStore, FileResults
from inference_service.processor import Processor, InvalidMessage, digest


ROOT = Path(__file__).resolve().parents[1]


class ProcessorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "inference_service")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.model_path = ROOT / "autoencoder/modell_v2/autoencoder.npz"
        self.model = load_model(self.model_path)
        self.model_sha = digest(self.model_path.read_bytes())
        self.mid = str(uuid.uuid4())
        self.file = ROOT / "messdatengenerator/beispieldaten/messung_gut.npy"
        self.data = load_measurement(self.file)
        self.chunks = list(make_chunks(self.data, self.mid))
        self.restart()

    def restart(self):
        # Neue Objekte greifen ausschließlich auf die gespeicherten Dateien zu.
        self.store = FileStore(self.root)
        self.results = FileResults(self.root / "ergebnisse")
        self.processor = Processor(self.store, self.results, self.model, self.model_sha)

    def send(self, i):
        body, props = self.chunks[i]
        return self.processor.process("pruefstand-01", props, body)

    def result(self):
        return self.results.get("pruefstand-01", self.mid)

    def test_normal_and_fault_match_existing_model(self):
        for name in ("messung_gut", "messung_schlecht"):
            with self.subTest(name=name):
                self.mid = str(uuid.uuid4())
                path = self.file.with_name(name + ".npy")
                data = load_measurement(path)
                self.chunks = list(make_chunks(data, self.mid))
                for i in reversed(range(60)):
                    self.send(i)
                result = self.result()
                expected, _ = analyze(path, self.model)
                self.assertEqual(result["anomalous_windows"], expected["anomalous_windows"])
                self.assertEqual(result["measurement_anomalous"], expected["measurement_anomalous"])
                archive = self.store.read("messdaten", result["blob_name"])
                np.testing.assert_array_equal(np.load(io.BytesIO(archive), allow_pickle=False), data)
                self.assertEqual(self.store.list_chunks(f"pruefstand-01/{self.mid}/"), [])

    def test_restart_and_duplicate(self):
        for i in range(30):
            self.send(i)
        self.assertEqual(self.send(0), "pending")
        self.restart()
        for i in range(30, 60):
            self.send(i)
        before = self.result()
        self.assertEqual(self.send(0), "duplicate")
        self.assertEqual(self.result(), before)

    def test_missing_chunk_never_completes(self):
        for i in range(59):
            self.send(i)
        self.assertIsNone(self.result())
        self.assertFalse((self.root / "messdaten").exists())
        self.assertEqual(len(self.store.list_chunks(f"pruefstand-01/{self.mid}/")), 59)

    def test_corrupt_payload_rejected(self):
        body, props = self.chunks[0]
        with self.assertRaises(InvalidMessage):
            self.processor.process("pruefstand-01", props, b"wrong" + body[5:])

    def test_conflicting_duplicate_rejected(self):
        self.send(0)
        body, props = self.chunks[0]
        raw = np.zeros((10000, 3), dtype="<f4").tobytes()
        with self.assertRaises(InvalidMessage):
            self.processor.process("pruefstand-01", {**props, "sha256": digest(raw)}, raw)

    def test_result_failure_preserves_chunks_and_retry_completes(self):
        for i in range(59):
            self.send(i)
        def unavailable(document):
            raise ConnectionError("simulierter Ausfall")
        self.results.save = unavailable
        with self.assertRaises(ConnectionError):
            self.send(59)
        self.assertEqual(len(self.store.list_chunks(f"pruefstand-01/{self.mid}/")), 60)
        self.restart()
        self.assertEqual(self.send(59), "complete")

    def test_cleanup_failure_retried_without_duplicate_result(self):
        for i in range(59):
            self.send(i)
        def unavailable(prefix):
            raise ConnectionError("simulierter Ausfall")
        self.store.cleanup = unavailable
        with self.assertRaises(ConnectionError):
            self.send(59)
        self.assertIsNotNone(self.result())
        self.restart()
        self.assertEqual(self.send(59), "duplicate")
        self.assertEqual(self.store.list_chunks(f"pruefstand-01/{self.mid}/"), [])

    def prepare_alarm(self):
        self.chunks = list(make_chunks(load_measurement(
            self.file.with_name("messung_schlecht.npy")), self.mid))
        publisher = Mock()
        self.processor.publisher = publisher
        for i in range(59):
            self.send(i)
        publisher.publish.assert_not_called()
        return publisher

    def test_alarm_normal_silent_fault_published_and_duplicate_silent(self):
        publisher = Mock()
        self.processor.publisher = publisher
        for i in range(60):
            self.send(i)
        publisher.publish.assert_not_called()
        self.mid = str(uuid.uuid4())
        publisher = self.prepare_alarm()
        self.send(59)
        event = publisher.publish.call_args.args[0]
        self.assertEqual(event["eventType"], "Pruefstand.AnomalieErkannt")
        self.assertEqual(event["data"]["measurement_id"], self.mid)
        self.assertEqual(event["data"]["anomalous_percent"], 50.83)
        self.assertEqual(self.result()["alarm_status"], "published")
        self.restart()
        self.processor.publisher = publisher
        self.send(59)
        publisher.publish.assert_called_once()

    def test_publish_failure_persists_pending_and_restart_retries_same_event(self):
        publisher = self.prepare_alarm()
        publisher.publish.side_effect = ConnectionError("offline")
        with self.assertRaises(ConnectionError):
            self.send(59)
        pending = self.result()
        self.assertEqual(pending["alarm_status"], "pending")
        self.assertEqual(len(self.store.list_chunks(f"pruefstand-01/{self.mid}/")), 60)
        self.restart()
        self.processor.publisher = Mock()
        self.send(59)
        self.processor.publisher.publish.assert_called_once_with(pending["alarm_event"])
        self.assertEqual(self.result()["alarm_status"], "published")

    def test_status_save_failure_retries_with_identical_event(self):
        publisher = self.prepare_alarm()
        sent = []
        publisher.publish.side_effect = lambda event: sent.append(deepcopy(event))
        save = self.results.save
        def fail_published(document):
            if document.get("alarm_status") == "published":
                raise ConnectionError("Cosmos offline")
            save(document)
        self.results.save = fail_published
        with self.assertRaises(ConnectionError):
            self.send(59)
        self.assertEqual(self.result()["alarm_status"], "pending")
        self.restart()
        self.processor.publisher = publisher
        self.send(59)
        self.assertEqual(len(sent), 2)
        self.assertEqual(sent[0], sent[1])

    def test_legacy_result_not_retroactively_published(self):
        self.chunks = list(make_chunks(load_measurement(
            self.file.with_name("messung_schlecht.npy")), self.mid))
        for i in range(60):
            self.send(i)
        self.processor.publisher = Mock()
        self.send(59)
        self.processor.publisher.publish.assert_not_called()


if __name__ == "__main__":
    unittest.main()
