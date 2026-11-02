"""Lesende, begrenzte Abfragen für die Prüfstandsübersicht."""
import re
import uuid
from datetime import datetime, timezone

from azure.cosmos.exceptions import CosmosResourceNotFoundError


class BadRequest(ValueError):
    pass


def device_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
        raise BadRequest("device_id muss eine gültige Prüfstand-ID sein.")
    return value


def measurement_id(value):
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise BadRequest("Ungültige Messungs-ID.") from None
    return value


def public_result(document, detail=False):
    # Explizite Freigabeliste: keine Cosmos-Systemfelder, Chunk-Hashes,
    # internen Alarmaufträge oder zukünftigen vertraulichen Felder ausgeben.
    fields = ("device_id", "status", "measurement_anomalous", "anomalous_fraction",
              "anomalous_windows", "window_count", "sample_count", "sample_rate_hz")
    result = {key: document[key] for key in fields if key in document}
    result["measurement_id"] = document["id"]
    if "anomalous_fraction" in document:
        result["anomalous_percent"] = round(document["anomalous_fraction"] * 100, 2)
    # _ts ist die letzte Cosmos-Änderung, NICHT der Messzeitpunkt.
    if "_ts" in document:
        result["updated_at"] = datetime.fromtimestamp(
            document["_ts"], timezone.utc).isoformat()
    if detail:
        for key in ("axes", "unit", "chunk_count", "mean_error", "max_error",
                    "threshold", "alarm_fraction", "model_sha256", "blob_name",
                    "archive_sha256", "alarm_status"):
            if key in document:
                result[key] = document[key]
    return result


class ResultsService:
    def __init__(self, container):
        self.container = container

    def list_results(self, device, limit="20"):
        device = device_id(device)
        if not isinstance(limit, str) or not re.fullmatch(r"[0-9]{1,3}", limit):
            raise BadRequest("limit muss zwischen 1 und 100 liegen.")
        limit = int(limit)
        if not 1 <= limit <= 100:
            raise BadRequest("limit muss zwischen 1 und 100 liegen.")
        # Ein zusätzliches Ergebnis zeigt an, ob ältere Einträge existieren.
        rows = list(self.container.query_items(
            query=("SELECT TOP @count c.id, c.device_id, c.status, "
                   "c.measurement_anomalous, c.anomalous_fraction, "
                   "c.anomalous_windows, c.window_count, c.sample_count, "
                   "c.sample_rate_hz, c._ts FROM c ORDER BY c._ts DESC"),
            parameters=[{"name": "@count", "value": limit + 1}],
            partition_key=device, max_item_count=limit + 1))
        return {"items": [public_result(row) for row in rows[:limit]],
                "count": min(len(rows), limit), "limit": limit,
                "has_more": len(rows) > limit, "order_by": "updated_at_desc"}

    def detail(self, device, measurement):
        device, measurement = device_id(device), measurement_id(measurement)
        try:
            document = self.container.read_item(item=measurement, partition_key=device)
        except CosmosResourceNotFoundError:
            return None
        return public_result(document, detail=True)
