import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import requests

import app as service


FIXTURES = Path(__file__).parent / "fixtures"
SUCCESS = json.loads((FIXTURES / "source_success.json").read_text(encoding="utf-8"))
FAILURES = json.loads((FIXTURES / "source_failures.json").read_text(encoding="utf-8"))


def response(status, payload=None, headers=None):
    result = Mock()
    result.status_code = status
    result.ok = 200 <= status < 400
    result.headers = headers or {}
    result.json.return_value = payload
    return result


class AppConditionsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data_path = Path(self.temp.name) / "loa_data.json"
        self.seed_path = Path(self.temp.name) / "history_seed.json"
        self.old_data, self.old_seed, self.old_database = (
            service.DATA_FILE, service.HISTORY_SEED_FILE, service.DATABASE_URL
        )
        service.DATA_FILE = self.data_path
        service.HISTORY_SEED_FILE = self.seed_path
        service.DATABASE_URL = ""
        service.app.config.update(TESTING=True)
        self.api_headers_patcher = patch.object(service, "api_headers", return_value={})
        self.api_headers_patcher.start()
        self.client = service.app.test_client()

    def tearDown(self):
        service.DATA_FILE, service.HISTORY_SEED_FILE, service.DATABASE_URL = (
            self.old_data, self.old_seed, self.old_database
        )
        self.api_headers_patcher.stop()
        self.temp.cleanup()

    def mock_success(self, power="1,234.56"):
        profile = dict(SUCCESS["profile"], CombatPower=power)
        return [
            response(200, profile, {"Last-Modified": "Mon, 16 Nov 2026 03:00:00 GMT"}),
            response(200, SUCCESS["equipment"]),
        ]

    def test_public_routes_need_no_login(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/health").json["status"], "ok")

    @patch.object(service, "kst_now")
    @patch.object(service.requests, "get")
    def test_same_kst_day_updates_one_row_and_next_day_appends(self, get, clock):
        kst = timezone(timedelta(hours=9))
        day_one = datetime(2026, 11, 16, 23, 59, tzinfo=kst)
        day_two = datetime(2026, 11, 17, 0, 1, tzinfo=kst)
        clock.return_value = day_one
        first = self.mock_success("1,234.56")
        second = self.mock_success("1,250.00")
        third = self.mock_success("1,260.00")
        get.side_effect = first + second + third

        first_result = self.client.get("/api/search?name=%EC%8B%9C%ED%97%98%EC%9A%A9%EC%BA%90%EB%A6%AD%ED%84%B0")
        second_result = self.client.get("/api/search?name=%EC%8B%9C%ED%97%98%EC%9A%A9%EC%BA%90%EB%A6%AD%ED%84%B0")
        clock.return_value = day_two
        third_result = self.client.get("/api/search?name=%EC%8B%9C%ED%97%98%EC%9A%A9%EC%BA%90%EB%A6%AD%ED%84%B0")

        self.assertEqual(first_result.status_code, 200)
        self.assertEqual(second_result.status_code, 200)
        self.assertEqual(third_result.status_code, 200)
        rows = third_result.json["history"]
        self.assertEqual([row["date"] for row in rows], ["2026-11-16", "2026-11-17"])
        self.assertEqual(rows[0]["combatPower"], 1250.0)
        self.assertEqual(rows[1]["combatPower"], 1260.0)
        self.assertEqual(third_result.json["yesterdayPower"], 1250.0)
        provenance = third_result.json["provenance"]
        self.assertEqual(provenance["timezone"], "Asia/Seoul")
        self.assertEqual(provenance["sourceUrl"], service.API_DOCS_URL)
        self.assertIsNotNone(provenance["sourceTimestamp"])
        self.assertIn("+09:00", provenance["queryCompletedAt"])

    @patch.object(service.requests, "get")
    def test_missing_source_timestamp_is_reported_as_unavailable(self, get):
        get.return_value = response(200, SUCCESS["profile"])

        _, timing = service.request_loa("시험용캐릭터", "profiles")

        self.assertIsNone(timing["sourceTimestamp"])

    @patch.object(service.requests, "get")
    def test_external_http_failures_are_distinguished(self, get):
        for status, code in FAILURES["http"].items():
            with self.subTest(status=status):
                get.return_value = response(int(status), {})
                with self.assertRaises(service.ApiError) as caught:
                    service.request_loa("시험용캐릭터", "profiles")
                self.assertEqual(caught.exception.code, code)
                if status in ("401", "403", "404", "429", "500"):
                    self.assertEqual(caught.exception.source_status, int(status))

    @patch.object(service.requests, "get")
    def test_network_and_invalid_json_failures_are_distinguished(self, get):
        for failure, code in FAILURES["network"].items():
            with self.subTest(failure=failure):
                if failure == "timeout":
                    get.side_effect = requests.Timeout()
                elif failure == "offline":
                    get.side_effect = requests.ConnectionError()
                else:
                    get.side_effect = None
                    get.return_value = response(200)
                    get.return_value.json.side_effect = ValueError("synthetic malformed json")
                with self.assertRaises(service.ApiError) as caught:
                    service.request_loa("시험용캐릭터", "profiles")
                self.assertEqual(caught.exception.code, code)

    @patch.object(service.requests, "get")
    def test_stale_value_is_returned_without_overwriting_last_success(self, get):
        original = [{
            "name": "시험용캐릭터", "server": "시험서버", "className": "시험직업",
            "itemLevel": 1700.0, "combatPower": 1234.56, "date": "2026-11-16"
        }]
        self.data_path.write_text(json.dumps({"시험용캐릭터": original}), encoding="utf-8")
        get.return_value = response(503, {})

        result = self.client.get("/api/search?name=%EC%8B%9C%ED%97%98%EC%9A%A9%EC%BA%90%EB%A6%AD%ED%84%B0")

        self.assertEqual(result.status_code, 502)
        self.assertEqual(result.json["code"], "source_server_error")
        self.assertEqual(result.json["lastSuccessful"]["character"]["combatPower"], 1234.56)
        self.assertEqual(json.loads(self.data_path.read_text(encoding="utf-8"))["시험용캐릭터"], original)

    @patch.object(service, "kst_now")
    @patch.object(service.requests, "get")
    def test_success_after_failure_appends_the_new_kst_day(self, get, clock):
        old_row = {
            "name": "시험용캐릭터", "server": "시험서버", "className": "시험직업",
            "itemLevel": 1700.0, "combatPower": 1234.56, "date": "2026-11-16"
        }
        self.data_path.write_text(json.dumps({"시험용캐릭터": [old_row]}), encoding="utf-8")
        clock.return_value = datetime(2026, 11, 17, 0, 1, tzinfo=timezone(timedelta(hours=9)))
        get.side_effect = [response(503, {})] + self.mock_success("1,250.00")

        failed = self.client.get("/api/search?name=%EC%8B%9C%ED%97%98%EC%9A%A9%EC%BA%90%EB%A6%AD%ED%84%B0")
        recovered = self.client.get("/api/search?name=%EC%8B%9C%ED%97%98%EC%9A%A9%EC%BA%90%EB%A6%AD%ED%84%B0")

        self.assertIn("lastSuccessful", failed.json)
        self.assertEqual(recovered.status_code, 200)
        self.assertEqual([row["date"] for row in recovered.json["history"]],
                         ["2026-11-16", "2026-11-17"])
        self.assertEqual(recovered.json["yesterdayPower"], 1234.56)

    @patch.object(service.requests, "get")
    def test_schema_change_does_not_save_zero_values(self, get):
        invalid_profile = dict(SUCCESS["profile"])
        invalid_profile.pop("CombatPower")
        get.return_value = response(200, invalid_profile)

        result = self.client.get("/api/search?name=%EC%8B%9C%ED%97%98%EC%9A%A9%EC%BA%90%EB%A6%AD%ED%84%B0")

        self.assertEqual(result.status_code, 502)
        self.assertEqual(result.json["code"], FAILURES["schema"]["missing_combat_power"])
        self.assertFalse(self.data_path.exists())


if __name__ == "__main__":
    unittest.main()
