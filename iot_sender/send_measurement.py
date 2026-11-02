"""Messdateien in Ein-Sekunden-Abschnitten versenden. Ohne --send nur prüfen."""

import argparse
import getpass
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid

import numpy as np


DEFAULT_FILE = Path(__file__).resolve().parents[1] / "messdatengenerator/beispieldaten/messung_gut.npy"
EXPECTED_HUB = "iot-pruefstand-a23c51c917a9.azure-devices.net"
EXPECTED_DEVICE = "pruefstand-01"


def load_measurement(path):
    """Nur technische Metadaten verwenden, keine Fehlerlabels übertragen."""
    meta = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    signal = np.load(path, allow_pickle=False)
    if signal.ndim != 2 or signal.shape[1] != 3 or len(signal) == 0:
        raise ValueError("Die Messung muss ein nicht leeres Array mit drei Achsen sein.")
    if signal.dtype.kind != "f" or signal.dtype.itemsize != 4 or not np.isfinite(signal).all():
        raise ValueError("Die Messwerte müssen endliche float32-Zahlen sein.")
    if meta.get("sample_rate_hz") != 10000:
        raise ValueError("Das bestehende Modell benötigt eine Abtastrate von 10000 Hz.")
    if meta.get("axes") != ["x", "y", "z"] or meta.get("unit") != "m/s^2":
        raise ValueError("Achsen oder Einheit stimmen nicht mit dem Modell überein.")
    if meta.get("sample_count") != len(signal) or len(signal) % 10000:
        raise ValueError("Messwertzahl prüfen. Es werden vollständige Sekunden erwartet.")
    # Festes Byteformat: Little Endian, zeilenweise x/y/z. So kann die Cloud
    # die Originalwerte unabhängig von ihrem Betriebssystem wiederherstellen.
    return np.ascontiguousarray(signal, dtype="<f4")


def make_chunks(signal, measurement_id):
    """Binäre Rohdaten und kleine, als Text übertragene Nachrichteneigenschaften."""
    total = len(signal) // 10000
    for index in range(total):
        body = signal[index * 10000:(index + 1) * 10000].tobytes(order="C")
        properties = {
            "schema_version": "1",
            "measurement_id": measurement_id,
            "chunk_index": str(index),  # Zählung beginnt bei null.
            "chunk_count": str(total),  # Auch beim Einzeltest die echte Gesamtzahl.
            "sample_offset": str(index * 10000),
            "sample_count": "10000",
            "total_samples": str(len(signal)),
            "sample_rate_hz": "10000",
            "dtype": "float32-le",
            "axes": "xyz",
            "unit": "m/s^2",
            "sha256": hashlib.sha256(body).hexdigest(),
        }
        # Gleiche Messungs-ID und Abschnittsnummer ermöglichen später das
        # Erkennen von Wiederholungen. Die Prüfsumme erkennt Inhaltsabweichungen.
        yield body, properties


def create_client():
    """Gerätezugang aus Umgebung oder verdeckter Eingabe, niemals aus dem Code."""
    from azure.iot.device import IoTHubDeviceClient

    connection = os.environ.get("IOTHUB_DEVICE_CONNECTION_STRING")
    if not connection:
        connection = getpass.getpass("Geräte-Verbindungszeichenfolge (verdeckt): ").strip()
    fields = dict(part.split("=", 1) for part in connection.split(";") if "=" in part)
    if fields.get("HostName") != EXPECTED_HUB or fields.get("DeviceId") != EXPECTED_DEVICE:
        raise ValueError("Bitte den Gerätezugang für pruefstand-01 im Projekt-IoT-Hub verwenden.")
    # WebSockets verwendet Port 443 und transportiert MQTT verschlüsselt.
    # Eine Verbindung wird für die gesamte Messung wiederverwendet.
    return IoTHubDeviceClient.create_from_connection_string(connection, websockets=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE, help="NPY-Datei mit gleichnamiger JSON-Datei")
    parser.add_argument("--send", action="store_true", help="Tatsächlich zum IoT Hub senden")
    parser.add_argument("--limit", type=int, help="Nur die ersten N Abschnitte prüfen oder senden")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit muss mindestens 1 sein.")

    client = None
    try:
        signal = load_measurement(args.file)
        # Jeder Aufruf ist eine neue Übertragung. Test und Vollmessung werden
        # deshalb in der Cloud nicht versehentlich miteinander vermischt.
        measurement_id = str(uuid.uuid4())
        total = len(signal) // 10000
        count = min(args.limit, total) if args.limit else total
        print(f"Modus: {'AZURE-VERSAND' if args.send else 'LOKALER PROBELAUF'}")
        print(f"Messungs-ID: {measurement_id}")
        print(f"Datei: {args.file.name}, {total} Sekunden, {signal.nbytes} Byte Rohdaten")
        print(f"Geplant: {count} von {total} Abschnitten")
        if count < total:
            print("Teiltest: Diese Übertragung ergibt keine vollständige Messung.")
        if args.send:
            from azure.iot.device import Message
            client = create_client()
            client.connect()

        for index, (body, properties) in enumerate(make_chunks(signal, measurement_id)):
            if index >= count:
                break
            if client:
                message = Message(body)
                message.content_type = "application/octet-stream"
                message.message_id = f"{measurement_id}:{index}"
                message.correlation_id = measurement_id
                message.custom_properties.update(properties)
                # Ein Fehler bricht ab. Ein erfolgreicher Versand bestätigt nur
                # die Hub-Annahme, nicht die spätere Speicherung oder Inferenz.
                client.send_message(message)
            print(f"Abschnitt {index + 1}/{total}: {len(body)} Byte "
                  f"{'vom Hub angenommen' if client else 'lokal geprüft'}")
            if client and index + 1 < count:
                # Gespeicherte Messungen nicht schlagartig als große Last senden.
                time.sleep(1)
        print("Versand beendet." if client else "Probelauf beendet. Keine Daten an Azure gesendet.")
        return 0
    except KeyboardInterrupt:
        print("Abgebrochen. Die Übertragung kann unvollständig sein.", file=sys.stderr)
        return 130
    except Exception as exc:
        # SDK-Fehlertexte können Zugangsdaten enthalten. Daher keine rohe
        # Fehlermeldung ausgeben. Lokale Validierungsfehler bleiben verständlich.
        if isinstance(exc, ValueError) and client is None:
            print("Eingaben oder Messdatei prüfen.", file=sys.stderr)
        print(f"Fehler ({type(exc).__name__}). Datei, Gerätezugang und Verbindung prüfen. "
              "Keine vollständige Übertragung bestätigt.", file=sys.stderr)
        return 1
    finally:
        if client is not None:
            try:
                client.shutdown()
            except Exception:
                print("Verbindung konnte nicht sauber beendet werden.", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
