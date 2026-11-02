"""Verarbeitung unabhängig von Azure, damit Fehlerfälle lokal prüfbar sind."""

import hashlib
import io
import json
import re
import uuid

import numpy as np

from autoencoder.model import extract_features, reconstruction_errors
from inference_service.alarms import make_alarm


class InvalidMessage(ValueError):
    """Ungültige Nutzdaten, die nicht erneut ausgewertet werden dürfen."""


def digest(data):
    return hashlib.sha256(data).hexdigest()


def validate(device, props, body):
    """Geräte-ID stammt aus IoT-Hub-Systemeigenschaften, nicht aus dem Body."""
    try:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", device):
            raise ValueError()
        measurement = str(uuid.UUID(props["measurement_id"]))
        if measurement != props["measurement_id"]:
            raise ValueError()
        expected = {"schema_version": "1", "sample_rate_hz": "10000",
                    "sample_count": "10000", "dtype": "float32-le",
                    "axes": "xyz", "unit": "m/s^2"}
        if any(props.get(k) != v for k, v in expected.items()):
            raise ValueError()
        index, count = int(props["chunk_index"]), int(props["chunk_count"])
        # Begrenzung verhindert unbeabsichtigt riesige Messungen im Prototyp.
        if not 0 <= index < count <= 60:
            raise ValueError()
        if int(props["sample_offset"]) != index * 10000:
            raise ValueError()
        if int(props["total_samples"]) != count * 10000:
            raise ValueError()
        if len(body) != 120000 or props["sha256"] != digest(body):
            raise ValueError()
        signal = np.frombuffer(body, dtype="<f4").reshape(10000, 3)
        if not np.isfinite(signal).all():
            raise ValueError()
        return measurement, index, count, signal
    except (ValueError, KeyError, TypeError):
        raise InvalidMessage("Nachrichtenformat oder Prüfsumme ungültig.") from None


class Processor:
    def __init__(self, store, results, model, model_sha, publisher=None):
        self.store, self.results = store, results
        self.publisher = publisher
        self.model, self.model_sha = model, model_sha
        config = model["config"]
        if config["sample_rate_hz"] != 10000 or config["window_seconds"] != 0.1:
            raise ValueError("Modell passt nicht zum Nachrichtenformat.")

    def publish_pending(self, result):
        # Alte Ergebnisse ohne Alarmauftrag werden nicht nachträglich versendet.
        if result.get("alarm_status") != "pending":
            return
        if self.publisher is None:
            raise RuntimeError("Ausstehender Alarm ohne Publisher.")
        self.publisher.publish(result["alarm_event"])
        result["alarm_status"] = "published"
        self.results.save(result)
        # Absturz zwischen Senden und Speichern kann erneut senden. Event Grid
        # garantiert ebenfalls keine einmalige Zustellung. Die ID bleibt gleich.

    def process(self, device, props, body):
        measurement, index, count, signal = validate(device, props, body)
        prefix = f"{device}/{measurement}/"
        # Nach Abschluss dienen die gespeicherten Prüfsummen als Duplikatnachweis.
        completed = self.results.get(device, measurement)
        if completed:
            if completed["chunk_count"] != count or completed["chunk_hashes"][index] != digest(body):
                raise InvalidMessage("Widersprüchliche Wiederholung einer fertigen Messung.")
            self.publish_pending(completed)
            self.store.cleanup(prefix)
            return "duplicate"

        features = extract_features(signal, 10000, 0.1)
        errors = reconstruction_errors(features, self.model)
        record = {"properties": props, "model_sha256": self.model_sha,
                  "errors": errors.tolist()}
        # Ein Blob pro Abschnitt enthält Rohdaten UND Ergebnisse. Ein atomarer
        # Upload vermeidet halbe Abschnittsdateien. Erst danach darf der Worker
        # seinen Empfangsfortschritt bestätigen.
        encoded = json.dumps(record, sort_keys=True, allow_nan=False).encode() + b"\n" + body
        key = f"{prefix}{index:03d}.bin"
        if not self.store.put_once("temporaer", key, encoded):
            previous = self.store.read("temporaer", key)
            if previous != encoded:
                raise InvalidMessage("Abschnitt existiert mit anderem Inhalt oder Modell.")

        keys = [f"{prefix}{i:03d}.bin" for i in range(count)]
        if not set(keys).issubset(self.store.list_chunks(prefix)):
            return "pending"

        signals, all_errors, hashes = [], [], []
        for expected_index, name in enumerate(keys):
            packed = self.store.read("temporaer", name)
            header, raw = packed.split(b"\n", 1)
            saved = json.loads(header)
            mid, part, total, values = validate(device, saved["properties"], raw)
            if (mid, part, total) != (measurement, expected_index, count):
                raise InvalidMessage("Abschnitte gehören nicht zur selben Messung.")
            if saved["model_sha256"] != self.model_sha:
                raise InvalidMessage("Modellwechsel innerhalb einer Messung.")
            signals.append(values)
            all_errors.extend(saved["errors"])
            hashes.append(digest(raw))

        combined = np.concatenate(signals)
        stream = io.BytesIO()
        # NPY erhält die ursprünglichen float32-Werte exakt und benötigt keine
        # Pickle-Objekte. Metadaten und Auswertung stehen im Cosmos-Dokument.
        np.save(stream, combined, allow_pickle=False)
        archive = stream.getvalue()
        blob_name = f"{device}/{measurement}.npy"
        if not self.store.put_once("messdaten", blob_name, archive):
            if self.store.read("messdaten", blob_name) != archive:
                raise InvalidMessage("Archivdatei widerspricht den empfangenen Daten.")

        errors = np.asarray(all_errors)
        cfg = self.model["config"]
        anomalous = int(np.sum(errors > cfg["threshold"]))
        fraction = anomalous / len(errors)
        result = {"id": measurement, "device_id": device, "status": "complete",
                  "chunk_count": count, "chunk_hashes": hashes,
                  "sample_rate_hz": 10000, "sample_count": len(combined),
                  "axes": ["x", "y", "z"], "unit": "m/s^2",
                  "model_sha256": self.model_sha, "window_count": len(errors),
                  "anomalous_windows": anomalous, "anomalous_fraction": fraction,
                  "measurement_anomalous": fraction >= cfg["alarm_fraction"],
                  "mean_error": float(errors.mean()), "max_error": float(errors.max()),
                  "threshold": cfg["threshold"], "alarm_fraction": cfg["alarm_fraction"],
                  "blob_name": blob_name, "archive_sha256": digest(archive)}
        # Reihenfolge ist entscheidend: Archiv, Ergebnis, dann Aufräumen.
        # Scheitert Cosmos DB, bleiben alle temporären Abschnitte erhalten.
        if self.publisher is not None and result["measurement_anomalous"]:
            result["alarm_status"] = "pending"
            result["alarm_event"] = make_alarm(result)
        self.results.save(result)
        self.publish_pending(result)
        self.store.cleanup(prefix)
        return "complete"
