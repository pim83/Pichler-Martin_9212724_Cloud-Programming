"""Alarmformat und Veröffentlichung mit der vorhandenen Azure-Identität."""

from datetime import datetime, timezone
import logging
from urllib.parse import urlsplit
import uuid

import requests


def make_alarm(result):
    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL,
                            f"pruefstand/{result['device_id']}/{result['id']}/anomaly/v1")),
        "eventType": "Pruefstand.AnomalieErkannt",
        "subject": f"pruefstaende/{result['device_id']}/messungen/{result['id']}",
        "eventTime": datetime.now(timezone.utc).isoformat(),
        "dataVersion": "1.0",
        "data": {
            "device_id": result["device_id"],
            "measurement_id": result["id"],
            "measurement_anomalous": True,
            "anomalous_fraction": result["anomalous_fraction"],
            "anomalous_percent": round(result["anomalous_fraction"] * 100, 2),
            "anomalous_windows": result["anomalous_windows"],
            "window_count": result["window_count"],
            "alarm_fraction": result["alarm_fraction"],
            "model_sha256": result["model_sha256"],
            "blob_name": result["blob_name"],
        },
    }


class EventGridPublisher:
    def __init__(self, endpoint, credential):
        url = urlsplit(endpoint)
        if (url.scheme != "https" or not url.hostname
                or not url.hostname.endswith(".eventgrid.azure.net")
                or url.path != "/api/events" or url.username or url.password
                or url.port or url.query or url.fragment):
            raise ValueError("Ungültiger Event-Grid-Topic-Endpunkt.")
        self.endpoint, self.credential = endpoint, credential

    def publish(self, event):
        token = self.credential.get_token("https://eventgrid.azure.net/.default")
        # Begrenzte Wartezeit. Bei Fehlern bleibt das Ereignis im Ergebnisdokument
        # ausstehend und der Worker bestätigt keinen neuen IoT-Checkpoint.
        with requests.post(
            self.endpoint, params={"api-version": "2018-01-01"},
            headers={"Authorization": f"Bearer {token.token}"},
            json=[event], timeout=(10, 30), allow_redirects=False,
        ) as response:
            if response.status_code != 200:
                raise RuntimeError(f"Event Grid HTTP {response.status_code}")
        logging.getLogger("inference").info(
            "Alarm an Event Grid übergeben: %s, Messung %s",
            event["id"], event["data"]["measurement_id"])
