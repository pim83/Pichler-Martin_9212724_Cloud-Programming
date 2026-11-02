"""Gesamte Verarbeitung lokal mit Dateispeichern statt Azure prüfen."""

import argparse
import json
from pathlib import Path
import uuid

from autoencoder.model import load_model
from iot_sender.send_measurement import load_measurement, make_chunks
from inference_service.processor import Processor, digest


class FileStore:
    def __init__(self, root):
        self.root = Path(root)

    def put_once(self, container, name, data):
        path = self.root / container / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            return False
        # Lokaler Einzelprozess-Testadapter. Azure verwendet atomare Blob-Uploads.
        path.write_bytes(data)
        return True

    def read(self, container, name):
        return (self.root / container / name).read_bytes()

    def list_chunks(self, prefix):
        base = self.root / "temporaer"
        directory = base / prefix
        return [p.relative_to(base).as_posix() for p in directory.glob("*.bin")]

    def cleanup(self, prefix):
        for name in self.list_chunks(prefix):
            (self.root / "temporaer" / name).unlink(missing_ok=True)


class FileResults:
    def __init__(self, root):
        self.root = Path(root)

    def get(self, device, measurement):
        path = self.root / device / f"{measurement}.json"
        return json.loads(path.read_text()) if path.exists() else None

    def save(self, document):
        path = self.root / document["device_id"] / f"{document['id']}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, indent=2, allow_nan=False), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("inference_service/local_check"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    model_path = root / "autoencoder/modell_v2/autoencoder.npz"
    store = FileStore(args.output)
    results = FileResults(args.output / "ergebnisse")
    processor = Processor(store, results, load_model(model_path), digest(model_path.read_bytes()))
    for name in ("messung_gut", "messung_schlecht"):
        signal = load_measurement(root / f"messdatengenerator/beispieldaten/{name}.npy")
        measurement = str(uuid.uuid4())
        for body, properties in make_chunks(signal, measurement):
            processor.process("pruefstand-01", properties, body)
        result = results.get("pruefstand-01", measurement)
        print(f"{name}: {result['anomalous_windows']}/{result['window_count']} auffällig, "
              f"Alarm={result['measurement_anomalous']}, ID={measurement}")
    print(f"Lokale Ergebnisse: {args.output.resolve()}")
    print("Keine Verbindung zu Azure aufgebaut.")


if __name__ == "__main__":
    main()
