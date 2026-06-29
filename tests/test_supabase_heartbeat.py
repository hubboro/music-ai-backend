import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import supabase_utils


class SupabaseHeartbeatTests(unittest.TestCase):
    def test_build_heartbeat_payload(self):
        checked_at = datetime(2026, 6, 29, 10, 0, tzinfo=timezone.utc)

        payload = supabase_utils.build_heartbeat_payload(
            source="test",
            status="ok",
            metrics={"soundtracks_total": 7},
            checked_at=checked_at,
        )

        self.assertEqual(payload["run_date"], "2026-06-29")
        self.assertEqual(payload["source"], "test")
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["metrics"], {"soundtracks_total": 7})
        self.assertEqual(payload["checked_at"], "2026-06-29T10:00:00+00:00")

    @patch.object(supabase_utils, "SUPABASE_SERVICE_ROLE_KEY", "service-role")
    @patch.object(supabase_utils, "SUPABASE_URL", "https://example.supabase.co")
    @patch.object(supabase_utils, "_count_soundtracks", side_effect=RuntimeError("metrics down"))
    @patch.object(supabase_utils.requests, "post")
    def test_save_app_heartbeat_records_degraded_status_when_metrics_fail(self, post, _count_soundtracks):
        response = Mock()
        response.json.return_value = [{"run_date": "2026-06-29", "source": "test", "status": "degraded"}]
        response.raise_for_status.return_value = None
        post.return_value = response

        result = supabase_utils.save_app_heartbeat(source="test")

        self.assertEqual(result["status"], "degraded")
        post.assert_called_once()
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["source"], "test")
        self.assertEqual(payload["status"], "degraded")
        self.assertIn("metrics down", payload["error"])


if __name__ == "__main__":
    unittest.main()
