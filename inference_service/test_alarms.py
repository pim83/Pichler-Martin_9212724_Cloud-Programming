"""HTTP-Vertrag prüfen, ohne Ereignisse oder E-Mails zu senden."""
import unittest
from unittest.mock import Mock, patch

from inference_service.alarms import EventGridPublisher


class PublisherTests(unittest.TestCase):
    endpoint = "https://example.germanywestcentral-1.eventgrid.azure.net/api/events"

    def test_authenticated_batch_and_timeout(self):
        credential = Mock()
        credential.get_token.return_value.token = "test-token"
        with patch("inference_service.alarms.requests.post") as post:
            post.return_value.__enter__.return_value.status_code = 200
            EventGridPublisher(self.endpoint, credential).publish(
                {"id": "event-1", "data": {"measurement_id": "measurement-1"}})
            credential.get_token.assert_called_once_with("https://eventgrid.azure.net/.default")
            args, kwargs = post.call_args
            self.assertEqual(args[0], self.endpoint)
            self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-token")
            self.assertEqual(kwargs["json"][0]["id"], "event-1")
            self.assertEqual(kwargs["params"], {"api-version": "2018-01-01"})
            self.assertEqual(kwargs["timeout"], (10, 30))
            self.assertFalse(kwargs["allow_redirects"])

    def test_non_success_not_acknowledged(self):
        for status in (302, 401, 403, 429, 500):
            with self.subTest(status=status), patch("inference_service.alarms.requests.post") as post:
                post.return_value.__enter__.return_value.status_code = status
                with self.assertRaises(RuntimeError):
                    EventGridPublisher(self.endpoint, Mock()).publish({})

    def test_untrusted_endpoint_rejected(self):
        for endpoint in ("http://example.eventgrid.azure.net/api/events",
                         "https://example.invalid/api/events", ""):
            with self.assertRaises(ValueError):
                EventGridPublisher(endpoint, Mock())
