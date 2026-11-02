"""Lokale Vertragstests ohne Azure-Zugriff. Host-Authentifizierung separat testen."""
import json
import unittest
from unittest.mock import Mock, patch

import azure.functions as func
from azure.cosmos.exceptions import CosmosResourceNotFoundError
import function_app
from service import BadRequest, ResultsService, public_result

MID = "69524208-34d0-4257-9398-57035e769d44"
DOC = {"id": MID, "device_id": "pruefstand-01", "status": "complete",
       "anomalous_fraction": 305 / 600, "measurement_anomalous": True,
       "_ts": 1792951531, "_etag": "secret", "chunk_hashes": ["internal"],
       "alarm_event": {"internal": True}, "blob_name": "pruefstand-01/test.npy"}


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.container = Mock()
        self.service = ResultsService(self.container)

    def test_list_bounded_single_partition(self):
        self.container.query_items.return_value = [DOC, DOC, DOC]
        result = self.service.list_results("pruefstand-01", "2")
        self.assertEqual(result["count"], 2)
        self.assertTrue(result["has_more"])
        self.assertEqual(len(result["items"]), 2)
        args = self.container.query_items.call_args.kwargs
        self.assertEqual(args["partition_key"], "pruefstand-01")
        self.assertEqual(args["parameters"], [{"name": "@count", "value": 3}])

    def test_invalid_inputs(self):
        for limit in ("0", "101", "-1", "1.5", "NaN", "1 OR 1=1"):
            with self.assertRaises(BadRequest):
                self.service.list_results("pruefstand-01", limit)
        for device in (None, "", "../other", "x' OR true", "a" * 129):
            with self.assertRaises(BadRequest):
                self.service.list_results(device)
        self.container.query_items.assert_not_called()

    def test_point_read_with_partition(self):
        self.container.read_item.return_value = DOC
        result = self.service.detail("pruefstand-01", MID)
        self.container.read_item.assert_called_once_with(item=MID, partition_key="pruefstand-01")
        self.assertEqual(result["anomalous_percent"], 50.83)
        self.assertEqual(result["blob_name"], DOC["blob_name"])

    def test_not_found(self):
        self.container.read_item.side_effect = CosmosResourceNotFoundError()
        self.assertIsNone(self.service.detail("pruefstand-01", MID))

    def test_invalid_measurement_id(self):
        with self.assertRaises(BadRequest):
            self.service.detail("pruefstand-01", "invalid")
        self.container.read_item.assert_not_called()

    def test_private_fields_not_exposed(self):
        result = public_result({**DOC, "future_secret": "hidden"}, detail=True)
        for field in ("_etag", "_ts", "chunk_hashes", "alarm_event", "future_secret"):
            self.assertNotIn(field, result)
        self.assertIn("updated_at", result)
        self.assertNotIn("measured_at", result)

    def test_empty_list(self):
        self.container.query_items.return_value = []
        result = self.service.list_results("pruefstand-01")
        self.assertEqual(result["items"], [])
        self.assertFalse(result["has_more"])


class HttpTests(unittest.TestCase):
    def request(self, params=None, mid=MID):
        return func.HttpRequest("GET", "https://example/api/measurements", body=b"",
                                params=params or {}, route_params={"measurement_id": mid})

    def test_missing_device_is_400_without_connection(self):
        with patch("function_app.get_service") as get:
            result = function_app.measurements(self.request())
            self.assertEqual(result.status_code, 400)
            get.assert_not_called()

    def test_list_json_and_no_cache(self):
        with patch("function_app.get_service") as get:
            get.return_value.list_results.return_value = {"items": []}
            result = function_app.measurements(self.request({"device_id": "pruefstand-01"}))
            self.assertEqual(result.status_code, 200)
            self.assertEqual(json.loads(result.get_body()), {"items": []})
            self.assertEqual(result.headers["Cache-Control"], "no-store")

    def test_detail_not_found_is_404(self):
        with patch("function_app.get_service") as get:
            get.return_value.detail.return_value = None
            result = function_app.measurement(self.request({"device_id": "pruefstand-01"}))
            self.assertEqual(result.status_code, 404)

    def test_backend_failure_sanitized(self):
        with patch("function_app.get_service", side_effect=RuntimeError("SECRET")):
            result = function_app.measurements(self.request({"device_id": "pruefstand-01"}))
            self.assertEqual(result.status_code, 503)
            self.assertNotIn(b"SECRET", result.get_body())

    def test_functions_are_get_only_and_key_protected(self):
        functions = function_app.app.get_functions()
        self.assertEqual(len(functions), 2)
        for function in functions:
            bindings = json.loads(function.get_function_json())["bindings"]
            trigger = next(b for b in bindings if b["type"] == "httpTrigger")
            self.assertEqual(trigger["authLevel"].lower(), "function")
            self.assertEqual([m.lower() for m in trigger["methods"]], ["get"])


if __name__ == "__main__":
    unittest.main()
