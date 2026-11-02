"""Azure Functions Python v2: ausschließlich authentifizierte GET-Aufrufe."""
import json
import logging
import os
from functools import lru_cache

import azure.functions as func
from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential

from service import BadRequest, ResultsService, device_id, measurement_id

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


@lru_cache(maxsize=1)
def get_service():
    credential = DefaultAzureCredential()
    client = CosmosClient(os.environ["COSMOS_URL"], credential=credential,
                          connection_timeout=5, request_timeout=10, retry_total=2)
    container = client.get_database_client("pruefstand").get_container_client("ergebnisse")
    return ResultsService(container)


def response(data, status=200):
    return func.HttpResponse(json.dumps(data, ensure_ascii=False, allow_nan=False),
                             status_code=status, mimetype="application/json",
                             headers={"Cache-Control": "no-store",
                                      "X-Content-Type-Options": "nosniff"})


def handle(operation):
    try:
        data = operation()
        if data is None:
            return response({"error": "Messung nicht gefunden."}, 404)
        return response(data)
    except BadRequest as exc:
        return response({"error": str(exc)}, 400)
    except Exception as exc:
        # Keine Tokens, Connection Strings oder SDK-Antworten im HTTP-Body.
        logging.error("Ergebnisabfrage fehlgeschlagen (%s)", type(exc).__name__)
        return response({"error": "Ergebnisse derzeit nicht verfügbar."}, 503)


@app.route(route="measurements", methods=["GET"])
def measurements(req: func.HttpRequest) -> func.HttpResponse:
    def operation():
        device = device_id(req.params.get("device_id"))
        return get_service().list_results(device, req.params.get("limit", "20"))
    return handle(operation)


@app.route(route="measurements/{measurement_id}", methods=["GET"])
def measurement(req: func.HttpRequest) -> func.HttpResponse:
    def operation():
        device = device_id(req.params.get("device_id"))
        mid = measurement_id(req.route_params.get("measurement_id"))
        return get_service().detail(device, mid)
    return handle(operation)
