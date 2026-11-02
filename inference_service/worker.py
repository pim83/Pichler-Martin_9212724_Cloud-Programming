"""Cloud-Worker. Start: python -m inference_service.worker"""

import logging
import os
from pathlib import Path
import signal
import tempfile
import threading

from azure.cosmos import CosmosClient
from azure.eventhub import EventHubConsumerClient, TransportType
from azure.eventhub.extensions.checkpointstoreblob import BlobCheckpointStore
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

from autoencoder.model import load_model
from inference_service.azure_store import BlobStore, CosmosResults
from inference_service.alarms import EventGridPublisher
from inference_service.processor import InvalidMessage, Processor, digest


LOG = logging.getLogger("inference")


def text_properties(values):
    def text(value):
        return value.decode("utf-8") if isinstance(value, bytes) else str(value)
    return {text(k): text(v) for k, v in values.items()}


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # Keine SDK-Debuglogs mit Verbindungsdaten oder kompletten Messwerten.
    logging.getLogger("azure").setLevel(logging.WARNING)
    credential = DefaultAzureCredential()
    blobs = BlobServiceClient(os.environ["BLOB_ACCOUNT_URL"], credential=credential)
    cosmos = CosmosClient(os.environ["COSMOS_URL"], credential=credential)
    results = CosmosResults(cosmos.get_database_client("pruefstand").get_container_client("ergebnisse"))
    store = BlobStore(blobs)

    # Modell kommt aus dem bereits hochgeladenen Blob. Der erwartete Hash wird
    # bei der Bereitstellung gesetzt. Ein unbeabsichtigter Austausch stoppt den Start.
    model_bytes = store.read("modelle", os.getenv("MODEL_BLOB", "autoencoder.npz"))
    model_sha = digest(model_bytes)
    if model_sha != os.environ["MODEL_SHA256"]:
        raise RuntimeError("Modell-Prüfsumme stimmt nicht mit der Bereitstellung überein.")
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "model.npz"
        path.write_bytes(model_bytes)
        publisher = EventGridPublisher(os.environ["EVENTGRID_TOPIC_ENDPOINT"], credential)
        processor = Processor(store, results, load_model(path), model_sha, publisher)

    checkpoint = BlobCheckpointStore(blob_account_url=os.environ["BLOB_ACCOUNT_URL"],
                                     container_name="checkpoints", credential=credential)
    # Hier ist eine Event-Hubs-kompatible ServiceConnect-Verbindung nötig.
    # Der Gerätezugang des Senders darf dafür nicht verwendet werden.
    consumer = EventHubConsumerClient.from_connection_string(
        os.environ["IOTHUB_EVENT_CONNECTION_STRING"],
        consumer_group="inferenz", checkpoint_store=checkpoint,
        transport_type=TransportType.AmqpOverWebsocket)
    lock = threading.Lock()

    def on_event(context, event):
        if event is None:
            return
        # Prototyp: genau eine Replica, Empfangs-Callbacks seriell auswerten.
        with lock:
            try:
                raw = b"".join(event.body)
                try:
                    properties = text_properties(event.properties or {})
                    system = text_properties(event.system_properties or {})
                    device = system.get("iothub-connection-device-id", "")
                    state = processor.process(device, properties, raw)
                    LOG.info("Messung %s, Abschnitt %s: %s", properties["measurement_id"],
                             properties["chunk_index"], state)
                except (InvalidMessage, UnicodeDecodeError) as exc:
                    # Fehlerhafte Nachrichten dauerhaft isolieren, damit eine
                    # einzelne defekte Nachricht nicht den ganzen Empfang blockiert.
                    name = f"rejected/{context.partition_id}/{event.sequence_number}.bin"
                    store.put_once("temporaer", name, raw)
                    LOG.warning("Nachricht abgelehnt: Partition %s, Sequenz %s, Typ %s",
                                context.partition_id, event.sequence_number, type(exc).__name__)
                # Erst nach dauerhafter Speicherung den Lesefortschritt sichern.
                context.update_checkpoint(event)
            except Exception as exc:
                LOG.error("Verarbeitung gestoppt (%s), kein neuer Checkpoint.", type(exc).__name__)
                # Das SDK kann Callback-Ausnahmen abfangen und weiterlaufen.
                # Ein harter Neustart verhindert das Überspringen dieses Events
                # durch einen späteren Checkpoint derselben Partition.
                os._exit(1)

    def stop(signum, frame):
        consumer.close()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    LOG.info("Inferenz-Service gestartet, Modell %s", model_sha)
    try:
        with consumer:
            consumer.receive(on_event=on_event, starting_position="-1")
    finally:
        blobs.close()
        cosmos.close()
        credential.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Keine ungekürzten SDK-Ausnahmen mit möglichen Verbindungsdaten loggen.
        LOG.error("Service konnte nicht gestartet werden (%s). Konfiguration prüfen.",
                  type(exc).__name__)
        raise SystemExit(1) from None
