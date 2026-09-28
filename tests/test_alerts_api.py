import tempfile
import unittest
from pathlib import Path

from src.alerts_api import alert_status_message, kyiv_air_raid_state
from src.storage import MessageStore


class KyivAlertApiTests(unittest.TestCase):
    def test_city_and_oblast_are_distinct_and_red_wins(self):
        oblast = {"location_uid": "14", "alert_type": "air_raid", "alert_level": "red"}
        city_yellow = {"location_uid": "31", "alert_type": "air_raid", "alert_level": "yellow"}
        city_red = {"location_uid": "31", "alert_type": "air_raid", "alert_level": "red"}
        self.assertEqual(kyiv_air_raid_state({"alerts": [oblast]})[0], "clear")
        self.assertEqual(kyiv_air_raid_state({"alerts": [oblast, city_yellow]})[0], "yellow")
        self.assertEqual(kyiv_air_raid_state({"alerts": [city_yellow, city_red]})[0], "red")

    def test_unknown_active_level_and_invalid_response(self):
        alert = {"location_uid": 31, "alert_type": "air_raid"}
        self.assertEqual(kyiv_air_raid_state({"alerts": [alert]})[0], "active_unknown")
        with self.assertRaises(ValueError):
            kyiv_air_raid_state({"message": "API error"})

    def test_transition_persists_without_repeat_on_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "messages.sqlite3"
            store = MessageStore(path)
            try:
                self.assertTrue(store.observe_kyiv_alert("yellow", "2026-09-27T10:00:00+00:00", "[]"))
                self.assertIsNotNone(store.pending_kyiv_alert())
                store.mark_kyiv_alert_notified("yellow")
                self.assertFalse(store.observe_kyiv_alert("yellow", "2026-09-27T10:01:00+00:00", "[]"))
                self.assertIsNone(store.pending_kyiv_alert())
            finally:
                store.close()
            reopened = MessageStore(path)
            try:
                self.assertIsNone(reopened.pending_kyiv_alert())
                self.assertTrue(reopened.observe_kyiv_alert("red", "2026-09-27T10:02:00+00:00", "[]"))
                self.assertEqual(reopened.pending_kyiv_alert()["state"], "red")
                self.assertEqual(reopened.connection.execute("SELECT COUNT(*) FROM kyiv_alert_events").fetchone()[0], 2)
            finally:
                reopened.close()

    def test_compact_status_message(self):
        message = alert_status_message("red", "2026-09-27T10:00:00+00:00")
        self.assertIn("червоний рівень", message)
        self.assertIn("alerts.in.ua", message)


if __name__ == "__main__":
    unittest.main()
