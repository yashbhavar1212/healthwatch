"""Run with:  python -m unittest discover tests -v"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["FLASK_SECRET_KEY"] = "test-key"

from app import create_app  # noqa: E402
from backend import risk  # noqa: E402


class RiskTests(unittest.TestCase):
    def test_original_high_rule_still_high(self):
        self.assertIn(risk.assess(11, 0, "High", "Good")["level"], ("High", "Critical"))

    def test_old_bug_forty_cases_medium_rain_is_not_safe(self):
        # The first version labelled this "Safe".
        self.assertEqual(risk.assess(40, 100, "Medium", "Good")["level"], "Critical")

    def test_quiet_village_is_low(self):
        self.assertEqual(risk.assess(1, 2, "Low", "Good")["level"], "Low")

    def test_boundaries(self):
        self.assertEqual(risk.diarrhea_points(4), 0)
        self.assertEqual(risk.diarrhea_points(5), 2)
        self.assertEqual(risk.diarrhea_points(10), 2)
        self.assertEqual(risk.diarrhea_points(11), 3)
        self.assertEqual(risk.diarrhea_points(26), 4)

    def test_rising_trend_adds_one_point(self):
        base = risk.assess(9, 0, "Low", "Good", previous_diarrhea=9)["score"]
        rising = risk.assess(9, 0, "Low", "Good", previous_diarrhea=5)["score"]
        self.assertEqual(rising, base + 1)

    def test_max_score(self):
        self.assertEqual(risk.assess(100, 100, "High", "Contaminated", 1)["score"], risk.MAX_SCORE)


PG_URL = os.environ.get("TEST_DATABASE_URL")  # set to also run the tests on PostgreSQL


def fresh_config(tmp, demo):
    """SQLite temp file by default; a clean PostgreSQL schema when TEST_DATABASE_URL is set."""
    if PG_URL:
        import psycopg
        with psycopg.connect(PG_URL, autocommit=True) as c:
            c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        return {"DATABASE": PG_URL, "TESTING": True, "DEMO_DATA": demo}
    return {"DATABASE_PATH": os.path.join(tmp, "t.db"), "TESTING": True, "DEMO_DATA": demo}


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app(fresh_config(self.tmp.name, True))
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def login(self, user="admin", pw="Admin@123"):
        r = self.client.post("/api/login", json={"username": user, "password": pw})
        self.assertEqual(r.status_code, 200)
        with self.client.session_transaction() as s:
            return {"X-CSRF-Token": s["csrf"]}

    def test_pages_need_login(self):
        self.assertEqual(self.client.get("/dashboard").status_code, 302)
        self.assertEqual(self.client.get("/api/summary").status_code, 401)

    def test_wrong_password(self):
        r = self.client.post("/api/login", json={"username": "admin", "password": "nope"})
        self.assertEqual(r.status_code, 401)

    def test_csrf_required(self):
        self.login()
        r = self.client.post("/api/records", json={})
        self.assertEqual(r.status_code, 403)

    def test_create_record_and_alert(self):
        h = self.login("worker", "Worker@123")
        village = self.client.get("/api/villages").get_json()[0]["id"]
        r = self.client.post("/api/records", headers=h, json={
            "village_id": village, "diarrhea": 40, "fever": 50, "rainfall": "medium",
            "water_quality": "Contaminated"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.get_json()["assessment"]["level"], "Critical")

    def test_validation(self):
        h = self.login()
        r = self.client.post("/api/records", headers=h, json={
            "village_id": 1, "diarrhea": -3, "fever": 1, "rainfall": "Low"})
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/records", headers=h, json={
            "village_id": 1, "diarrhea": 1, "fever": 1, "rainfall": "Stormy"})
        self.assertEqual(r.status_code, 400)

    def test_worker_cannot_delete(self):
        h = self.login("worker", "Worker@123")
        self.assertEqual(self.client.delete("/api/records/1", headers=h).status_code, 403)

    def test_summary_and_export(self):
        self.login()
        s = self.client.get("/api/summary").get_json()
        self.assertEqual(len(s["villages"]), 10)
        self.assertEqual(len(s["series"]["labels"]), 30)
        csv = self.client.get("/api/export.csv")
        self.assertEqual(csv.mimetype, "text/csv")

    def test_add_and_delete_village_with_reports(self):
        h = self.login()
        r = self.client.post("/api/villages", headers=h, json={"name": "  Test   Gaon ", "district": "Pune", "population": "1200"})
        self.assertEqual(r.status_code, 201)
        vid = r.get_json()["id"]
        dup = self.client.post("/api/villages", headers=h, json={"name": "test gaon"})
        self.assertEqual(dup.status_code, 409)
        self.client.post("/api/records", headers=h, json={
            "village_id": vid, "diarrhea": 30, "fever": 50, "rainfall": "High", "water_quality": "Contaminated"})
        listed = {v["name"]: v for v in self.client.get("/api/villages").get_json()}
        self.assertEqual(listed["Test Gaon"]["reports"], 1)
        d = self.client.delete(f"/api/villages/{vid}", headers=h).get_json()
        self.assertEqual(d["reports_deleted"], 1)
        self.assertNotIn("Test Gaon", [v["name"] for v in self.client.get("/api/villages").get_json()])

    def test_worker_cannot_delete_village(self):
        h = self.login("worker", "Worker@123")
        self.assertEqual(self.client.delete("/api/villages/1", headers=h).status_code, 403)

    def test_public_assess(self):
        r = self.client.post("/api/assess", json={"diarrhea": 12, "fever": 3, "rainfall": "High"})
        self.assertEqual(r.get_json()["level"], "High")


class EmptyStartTests(unittest.TestCase):
    def test_default_start_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(fresh_config(tmp, False))
            c = app.test_client()
            c.post("/api/login", json={"username": "admin", "password": "Admin@123"})
            self.assertEqual(c.get("/api/villages").get_json(), [])
            st = c.get("/api/summary").get_json()["stats"]
            self.assertEqual((st["villages"], st["open_alerts"], st["cases_this_week"]), (0, 0, 0))
            self.assertEqual(c.get("/api/records").get_json()["total"], 0)


if __name__ == "__main__":
    unittest.main()
