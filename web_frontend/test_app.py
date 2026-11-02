import os
import hashlib
import unittest
from unittest.mock import Mock, patch

from werkzeug.security import generate_password_hash

from app import ApiUnavailable, ResultsApi, create_app

MID = "69524208-34d0-4257-9398-57035e769d44"
HEADERS = {}
TEST_HASH = generate_password_hash("test-only-password")
TEST_KEY = "test-only-session-signing-key-32-characters"
ROW = dict(measurement_id=MID, device_id="pruefstand-01", measurement_anomalous=True,
           anomalous_percent=50.83, updated_at="2026-10-27T12:00:00Z", anomalous_windows=305,
           window_count=600, alarm_fraction=.1, mean_error=105.5, threshold=1.0965,
           sample_count=600000, sample_rate_hz=10000, axes=["x", "y", "z"],
           unit="m/s²", model_sha256="abc")


class FrontendTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, PUBLIC_DEVICE_IDS="pruefstand-01",
                              DASHBOARD_PASSWORD_HASH=TEST_HASH, DASHBOARD_SESSION_KEY=TEST_KEY)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.api = Mock()
        self.api.get.return_value = {"items": [ROW], "has_more": False}
        self.app = create_app(self.api)
        self.client = self.app.test_client()
        with self.client.session_transaction() as state:
            state["authenticated"] = hashlib.sha256(TEST_HASH.encode()).hexdigest()
            state["csrf"] = "test-csrf"

    def test_anonymous_access_redirects_without_api_call(self):
        visitor = self.app.test_client()
        for path in ("/", "/measurements/" + MID):
            self.assertEqual(visitor.get(path).status_code, 302)
        self.api.get.assert_not_called()

    def test_other_device_blocked_before_api_call(self):
        self.assertEqual(self.client.get("/?device_id=private-device").status_code, 404)
        self.assertEqual(self.client.get("/measurements/" + MID + "?device_id=private-device").status_code, 404)
        self.api.get.assert_not_called()

    def test_mutations_are_not_allowed(self):
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            for path in ("/", "/measurements/" + MID):
                self.assertEqual(self.client.open(path, method=method).status_code, 405)
        self.api.get.assert_not_called()

    def test_empty_public_allowlist_denies(self):
        os.environ["PUBLIC_DEVICE_IDS"] = ""
        self.assertEqual(self.client.get("/").status_code, 404)
        self.api.get.assert_not_called()

    def test_list_and_security_headers(self):
        response = self.client.get("/", headers=HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertIn("50,83 %", response.text)
        self.assertIn("27.10.2026 13:00 CET", response.text)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertIn("script-src 'none'", response.headers["Content-Security-Policy"])
        self.api.get.assert_called_once_with("/measurements", "pruefstand-01")

    def test_filter_only_shows_matching_rows(self):
        response = self.client.get("/?status=normal", headers=HEADERS)
        self.assertNotIn(MID, response.text)
        self.assertIn("Keine Messungen", response.text)

    def test_invalid_inputs_do_not_query_api(self):
        for path in ("/?status=bad", "/?device_id=../secret", "/measurements/not-a-uuid"):
            self.assertEqual(self.client.get(path, headers=HEADERS).status_code, 400)
        self.api.get.assert_not_called()

    def test_details_escape_values(self):
        self.api.get.return_value = dict(ROW, unit="<script>alert(1)</script>", model_sha256="hidden-model-hash", blob_name="hidden-storage-path", alarm_event={"secret": "hidden-event"})
        response = self.client.get("/measurements/" + MID, headers=HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertIn("305 / 600", response.text)
        self.assertIn("10,00 %", response.text)
        self.assertNotIn("<script>", response.text)
        self.assertIn("&lt;script&gt;", response.text)
        for internal in ("hidden-model-hash", "hidden-storage-path", "hidden-event"):
            self.assertNotIn(internal, response.text)

    def test_missing_measurement(self):
        self.api.get.return_value = None
        self.assertEqual(self.client.get("/measurements/" + MID, headers=HEADERS).status_code, 404)

    def test_unavailable_api_does_not_disclose_error(self):
        self.api.get.side_effect = ApiUnavailable("private-key")
        response = self.client.get("/", headers=HEADERS)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private-key", response.text)

    def test_login_logout_and_cookie_security(self):
        visitor = self.app.test_client()
        page = visitor.get("/login", base_url="https://localhost")
        cookie = page.headers["Set-Cookie"]
        for flag in ("Secure", "HttpOnly", "SameSite=Lax"):
            self.assertIn(flag, cookie)
        with visitor.session_transaction() as state:
            csrf = state["csrf"]
        result = visitor.post("/login", data={"csrf": csrf, "password": "test-only-password"}, base_url="https://localhost")
        self.assertEqual(result.status_code, 302)
        self.assertEqual(visitor.get("/", base_url="https://localhost").status_code, 200)
        with visitor.session_transaction() as state:
            csrf = state["csrf"]
        self.assertEqual(visitor.post("/logout", data={"csrf": csrf}, base_url="https://localhost").status_code, 302)
        self.assertEqual(visitor.get("/", base_url="https://localhost").status_code, 302)

    def test_wrong_password_and_throttle(self):
        visitor = self.app.test_client()
        visitor.get("/login")
        with visitor.session_transaction() as state:
            csrf = state["csrf"]
        for _ in range(5):
            self.assertEqual(visitor.post("/login", data={"csrf": csrf, "password": "wrong"}).status_code, 401)
        result = visitor.post("/login", data={"csrf": csrf, "password": "test-only-password"})
        self.assertEqual(result.status_code, 429)
        self.assertEqual(result.headers["Retry-After"], "60")
        self.api.get.assert_not_called()

    def test_csrf_required_for_login_and_logout(self):
        self.assertEqual(self.client.post("/login", data={"password": "test-only-password"}).status_code, 400)
        self.assertEqual(self.client.post("/logout").status_code, 400)
        self.api.get.assert_not_called()

    def test_missing_secret_fails_closed(self):
        with patch.dict(os.environ, DASHBOARD_SESSION_KEY=""):
            visitor = create_app(self.api).test_client()
        self.assertEqual(visitor.get("/").status_code, 503)
        self.assertEqual(visitor.get("/login").status_code, 503)
        self.api.get.assert_not_called()

    def test_stale_session_requires_login(self):
        with self.client.session_transaction() as state:
            state["authenticated"] = "old-password-version"
        self.assertEqual(self.client.get("/").status_code, 302)
        self.api.get.assert_not_called()

    @patch("app.requests.get")
    def test_key_only_in_server_request_header(self, get):
        with patch.dict(os.environ, RESULTS_API_URL="https://example.azurewebsites.net/api", RESULTS_API_KEY="private-key"):
            response = get.return_value.__enter__.return_value
            response.status_code = 200
            response.json.return_value = {"items": []}
            ResultsApi().get("/measurements", "pruefstand-01")
        args, kwargs = get.call_args
        self.assertNotIn("private-key", args[0])
        self.assertEqual(kwargs["headers"], {"x-functions-key": "private-key"})
        self.assertFalse(kwargs["allow_redirects"])

    @patch("app.requests.get")
    def test_unresolved_key_vault_reference_blocks_request(self, get):
        with patch.dict(os.environ, RESULTS_API_URL="https://example.azurewebsites.net/api", RESULTS_API_KEY="@Microsoft.KeyVault(SecretUri=example)"):
            with self.assertRaises(ApiUnavailable):
                ResultsApi().get("/measurements", "pruefstand-01")
        get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
