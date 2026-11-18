import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import requests
from fastapi.testclient import TestClient

from api import main
from evalguard import alerts, scheduler
from evalguard.config import settings
from evalguard.storage.database import DatabaseManager

SECRET_URL = "https://hooks.example.com/services/T000/B000/SECRET-TOKEN"

DRIFT = {
    "overall_status": "DRIFT_DETECTED",
    "recommendation": "Review prompt changes.",
    "metrics": {
        "faithfulness_score": {"drift_detected": True, "baseline_mean": 0.94, "current_mean": 0.78},
        "relevance_score": {"drift_detected": False, "baseline_mean": 0.9, "current_mean": 0.89},
        "latency_ms": {"drift_detected": True, "baseline_mean": 2300.0, "current_mean": 3900.0},
    },
}
RUN = {"id": "run-123", "domain": "hr", "run_name": "Scheduled · hr", "model_name": "m:free"}


def tmpdir():
    return tempfile.TemporaryDirectory(ignore_cleanup_errors=True)


def patch_settings(**kw):
    return mock.patch.multiple(settings, **kw)


NO_ALERTS = dict(ALERT_WEBHOOK_URL="", ALERT_SMTP_HOST="", ALERT_EMAIL_TO="", WEB_URL="")


class TestAlerts(unittest.TestCase):
    def test_channels_reflect_what_is_configured(self):
        with patch_settings(**NO_ALERTS):
            self.assertEqual(alerts.channels(), {"webhook": False, "email": False})
            self.assertEqual(alerts.send_alert("s", "b"), {})
        with patch_settings(**{**NO_ALERTS, "ALERT_WEBHOOK_URL": SECRET_URL}):
            self.assertEqual(alerts.channels(), {"webhook": True, "email": False})
        with patch_settings(**{**NO_ALERTS, "ALERT_SMTP_HOST": "smtp.x.com"}):
            self.assertFalse(alerts.channels()["email"])  # needs a recipient too
        with patch_settings(**{**NO_ALERTS, "ALERT_SMTP_HOST": "smtp.x.com", "ALERT_EMAIL_TO": "me@x.com"}):
            self.assertTrue(alerts.channels()["email"])

    def test_webhook_payload_works_for_slack_and_discord(self):
        with patch_settings(**{**NO_ALERTS, "ALERT_WEBHOOK_URL": SECRET_URL}), mock.patch("requests.post") as post:
            self.assertEqual(alerts.send_alert("Subject", "Body"), {"webhook": "sent"})
        self.assertEqual(post.call_args.args[0], SECRET_URL)
        self.assertEqual(post.call_args.kwargs["json"], {"text": "Subject\nBody", "content": "Subject\nBody"})

    def test_a_failing_webhook_is_reported_without_leaking_its_secret_url(self):
        with patch_settings(**{**NO_ALERTS, "ALERT_WEBHOOK_URL": SECRET_URL}):
            with mock.patch("requests.post", side_effect=requests.ConnectionError(f"Max retries exceeded with url: {SECRET_URL}")):
                out = alerts.send_alert("s", "b")
            self.assertEqual(out, {"webhook": "failed: ConnectionError"})
            resp = mock.Mock(status_code=403)
            err = requests.HTTPError(f"403 Client Error: Forbidden for url: {SECRET_URL}", response=resp)
            with mock.patch("requests.post", return_value=mock.Mock(raise_for_status=mock.Mock(side_effect=err))):
                out = alerts.send_alert("s", "b")
            self.assertEqual(out, {"webhook": "failed: HTTPError (HTTP 403)"})
        self.assertNotIn("SECRET", str(out))

    def test_email_uses_starttls_and_login_on_587(self):
        cfg = {**NO_ALERTS, "ALERT_SMTP_HOST": "smtp.x.com", "ALERT_SMTP_PORT": 587, "ALERT_SMTP_USER": "bot@x.com",
               "ALERT_SMTP_PASSWORD": "pw", "ALERT_EMAIL_FROM": "", "ALERT_EMAIL_TO": "me@x.com"}
        with patch_settings(**cfg), mock.patch("smtplib.SMTP") as smtp_cls:
            self.assertEqual(alerts.send_alert("Subject", "Body"), {"email": "sent"})
        smtp = smtp_cls.return_value.__enter__.return_value
        smtp_cls.assert_called_once_with("smtp.x.com", 587, timeout=15)
        smtp.starttls.assert_called_once()
        smtp.login.assert_called_once_with("bot@x.com", "pw")
        msg = smtp.send_message.call_args.args[0]
        self.assertEqual((msg["Subject"], msg["To"], msg["From"]), ("Subject", "me@x.com", "bot@x.com"))

    def test_email_uses_ssl_on_465_and_skips_login_without_a_user(self):
        cfg = {**NO_ALERTS, "ALERT_SMTP_HOST": "smtp.x.com", "ALERT_SMTP_PORT": 465, "ALERT_SMTP_USER": "", "ALERT_EMAIL_TO": "me@x.com"}
        with patch_settings(**cfg), mock.patch("smtplib.SMTP_SSL") as ssl_cls:
            self.assertEqual(alerts.send_alert("s", "b"), {"email": "sent"})
        smtp = ssl_cls.return_value.__enter__.return_value
        smtp.starttls.assert_not_called()
        smtp.login.assert_not_called()

    def test_a_failing_channel_does_not_stop_the_other(self):
        cfg = {**NO_ALERTS, "ALERT_WEBHOOK_URL": SECRET_URL, "ALERT_SMTP_HOST": "smtp.x.com", "ALERT_EMAIL_TO": "me@x.com"}
        with patch_settings(**cfg), mock.patch("requests.post", side_effect=requests.Timeout("slow")), mock.patch("smtplib.SMTP"):
            out = alerts.send_alert("s", "b")
        self.assertEqual(out, {"webhook": "failed: Timeout", "email": "sent"})

    def test_drift_message_lists_only_the_metrics_that_drifted(self):
        with patch_settings(**{**NO_ALERTS, "WEB_URL": "https://app.example.com"}):
            subject, body = alerts.drift_message(RUN, DRIFT)
        self.assertIn("Human Resources", subject)
        self.assertIn("Faithfulness: 94.0% → 78.0%", body)
        self.assertIn("Latency: 2300 ms → 3900 ms", body)
        self.assertNotIn("Relevance", body)
        self.assertIn("Review prompt changes.", body)
        self.assertIn("https://app.example.com/runs/run-123", body)

    def test_drift_message_has_no_link_without_a_web_url(self):
        with patch_settings(**NO_ALERTS):
            self.assertNotIn("Open the run", alerts.drift_message(RUN, DRIFT)[1])

    def test_only_drift_triggers_an_alert(self):
        with mock.patch.object(alerts, "send_alert", return_value={"webhook": "sent"}) as send:
            self.assertEqual(alerts.notify_drift(RUN, {"overall_status": "HEALTHY", "metrics": {}}), {})
            self.assertEqual(alerts.notify_drift(RUN, None), {})
            send.assert_not_called()
            self.assertEqual(alerts.notify_drift(RUN, DRIFT), {"webhook": "sent"})
            send.assert_called_once()


def real_run(domain, ts, scorer="llm:judge", **kw):
    return {"id": f"{domain}-{ts}", "domain": domain, "timestamp": ts, "scorer": scorer, "avg_faithfulness": 0.9, **kw}


class TestScheduler(unittest.TestCase):
    DOMAINS = ["hr", "education", "legal"]

    def setUp(self):
        self.tmp = tmpdir()
        self.addCleanup(self.tmp.cleanup)
        self.db = DatabaseManager(db_path=str(Path(self.tmp.name) / "s.db"))

    def save(self, domain, ts, **kw):
        self.db.save_run(real_run(domain, ts, **kw), [])

    def test_a_domain_with_no_real_score_goes_first_in_the_given_order(self):
        self.assertEqual(scheduler.pick_domain(self.db, self.DOMAINS), "hr")
        self.save("hr", "2026-11-01T00:00:00")
        self.assertEqual(scheduler.pick_domain(self.db, self.DOMAINS), "education")

    def test_mock_heuristic_simulated_and_experiment_runs_do_not_count_as_real(self):
        self.save("hr", "2026-11-01T00:00:00", scorer="mock")
        self.save("education", "2026-11-01T00:00:00", scorer="heuristic")
        self.save("legal", "2026-11-01T00:00:00", is_simulated=True)
        self.save("hr", "2026-11-02T00:00:00", experiment_id="exp1")
        self.assertEqual(scheduler.pick_domain(self.db, self.DOMAINS), "hr")
        self.assertFalse(scheduler.is_real({"scorer": "llm:x", "is_simulated": 1}))
        self.assertFalse(scheduler.is_real({"scorer": None}))

    def test_once_every_domain_has_a_real_score_the_oldest_is_refreshed(self):
        self.save("hr", "2026-11-03T00:00:00")
        self.save("education", "2026-11-01T00:00:00")
        self.save("education", "2026-11-05T00:00:00")  # newest education run is what counts
        self.save("legal", "2026-11-02T00:00:00")
        self.assertEqual(scheduler.pick_domain(self.db, self.DOMAINS), "legal")

    def run_tick(self, now, hours=24, results=None):
        calls = []

        def run_domain(domain, questions):
            calls.append((domain, questions))
            if isinstance(results, Exception):
                raise results
            return results or {"status": "SUCCESS", "run": {"id": "r1"}, "drift_report": {"overall_status": "HEALTHY"}}

        out = scheduler.tick(self.db, hours=hours, questions=6, domains=self.DOMAINS, run_domain=run_domain, now=now)
        return out, calls

    def test_runs_when_due_then_waits_for_the_interval(self):
        out, calls = self.run_tick(now=1_000_000)
        self.assertEqual(calls, [("hr", 6)])
        self.assertEqual((out["domain"], out["status"], out["run_id"], out["drift"]), ("hr", "SUCCESS", "r1", "HEALTHY"))
        self.assertEqual(self.run_tick(now=1_000_000 + 3600)[0], None)       # 1 h later: not due
        self.assertEqual(self.run_tick(now=1_000_000 + 24 * 3600 - 1)[0], None)
        self.assertEqual(len(self.run_tick(now=1_000_000 + 24 * 3600)[1]), 1)  # due again

    def test_a_failed_run_is_recorded_and_waits_for_the_next_interval_instead_of_retrying(self):
        out, _ = self.run_tick(now=1_000_000, results=RuntimeError("daily limit used up"))
        self.assertEqual((out["status"], out["error"]), ("FAILED", "daily limit used up"))
        self.assertEqual(self.run_tick(now=1_000_000 + 60)[0], None)

    def test_a_failed_job_result_is_passed_through(self):
        out, _ = self.run_tick(now=1_000_000, results={"status": "FAILED", "error": "quota"})
        self.assertEqual((out["status"], out["error"], out["run_id"]), ("FAILED", "quota", None))

    def test_off_when_hours_is_zero(self):
        out, calls = self.run_tick(now=1_000_000, hours=0)
        self.assertEqual((out, calls), (None, []))

    def test_state_survives_a_restart(self):
        self.run_tick(now=1_000_000)
        again = DatabaseManager(db_path=self.db.db_path)  # a new process opening the same file
        out = scheduler.tick(again, hours=24, questions=6, domains=self.DOMAINS, run_domain=lambda d, q: {}, now=1_000_000 + 60)
        self.assertIsNone(out)

    def test_status(self):
        st = scheduler.status(self.db, hours=0, questions=6, domains=self.DOMAINS, now=1_000_000)
        self.assertEqual((st["enabled"], st["next_domain"], st["next_due_at"], st["last_run_at"], st["last_result"]),
                         (False, None, None, None, None))
        st = scheduler.status(self.db, hours=24, questions=6, domains=self.DOMAINS, now=1_000_000)
        self.assertEqual((st["enabled"], st["next_domain"], st["last_run_at"]), (True, "hr", None))
        self.run_tick(now=1_000_000)
        st = scheduler.status(self.db, hours=24, questions=6, domains=self.DOMAINS, now=1_000_000 + 3600)
        self.assertEqual(st["last_result"]["domain"], "hr")
        self.assertTrue(st["last_run_at"].endswith("Z") and st["next_due_at"].endswith("Z"))
        self.assertGreater(st["next_due_at"], st["last_run_at"])

    def test_the_loop_keeps_going_after_an_error_and_stops_on_request(self):
        stop, calls = threading.Event(), []

        def tick_once():
            calls.append(1)
            if len(calls) == 3:
                stop.set()
            if len(calls) == 1:
                raise RuntimeError("one bad tick")

        scheduler.run_forever(stop, tick_once, first_delay=0, every=0.01)
        self.assertEqual(len(calls), 3)

    def test_the_loop_exits_without_ticking_if_stopped_during_the_first_delay(self):
        stop = threading.Event()
        stop.set()
        tick_once = mock.Mock()
        scheduler.run_forever(stop, tick_once, first_delay=10, every=10)
        tick_once.assert_not_called()


class FakeRunner:
    """EvaluationRunner stand-in whose result can be set per test."""
    report = None

    def __init__(self, domain, run_name=None, **kw):
        self.domain, self.run_name, self.kw = domain, run_name, kw

    def run_evaluation(self, baseline_run_id=None, progress=None):
        return {"run": {"id": "run-1", "domain": self.domain, "run_name": self.run_name, "model_name": "m"},
                "indexed_chunks": 3, "drift_report": FakeRunner.report, "drift_skipped_reason": None, "skipped": []}


class TestApiWiring(unittest.TestCase):
    def setUp(self):
        self.tmp = tmpdir()
        patches = [
            mock.patch.dict("os.environ", {"EVALGUARD_AUTH_DISABLED": "true"}),
            mock.patch.object(main, "db", DatabaseManager(db_path=str(Path(self.tmp.name) / "api.db"))),
            mock.patch.object(main, "EvaluationRunner", FakeRunner),
            patch_settings(**NO_ALERTS, SCHEDULE_HOURS=0.0, SCHEDULE_QUESTIONS=6),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)
        FakeRunner.report = None
        main._last_test_alert = 0.0
        self.c = TestClient(main.app)

    def job(self, domains=("hr",)):
        job = main._new_job("single", list(domains))
        main._run_job(job, None, None)
        return job

    def test_schedule_endpoint_reports_off_by_default_and_the_alert_channels(self):
        body = self.c.get("/schedule").json()
        self.assertEqual((body["enabled"], body["alerts"]), (False, {"webhook": False, "email": False}))
        with patch_settings(SCHEDULE_HOURS=24.0, ALERT_WEBHOOK_URL=SECRET_URL):
            body = self.c.get("/schedule").json()
        self.assertEqual((body["enabled"], body["hours"], body["questions"], body["alerts"]["webhook"]), (True, 24.0, 6, True))
        self.assertIn(body["next_domain"], main.DOMAINS_REGISTRY)
        self.assertNotIn("SECRET", str(body))

    def test_a_scheduled_tick_runs_one_domain_through_the_job_queue_and_records_it(self):
        with patch_settings(SCHEDULE_HOURS=24.0):
            result = main._scheduled_tick()
            self.assertEqual((result["status"], result["run_id"]), ("SUCCESS", "run-1"))
            self.assertIsNone(main._scheduled_tick())  # not due again yet
        job = list(main._jobs.values())[-1]
        self.assertEqual((job["kind"], job["status"], job["domains"]), ("scheduled", "done", [result["domain"]]))
        self.assertEqual(self.c.get("/schedule").json()["last_result"]["run_id"], "run-1")

    def test_drift_in_a_run_sends_an_alert_and_the_outcome_is_on_the_job(self):
        FakeRunner.report = DRIFT
        with mock.patch.object(alerts, "notify_drift", return_value={"webhook": "sent"}) as notify:
            job = self.job()
        notify.assert_called_once()
        self.assertEqual(notify.call_args.args[1]["overall_status"], "DRIFT_DETECTED")
        self.assertEqual(job["results"][0]["alerts"], {"webhook": "sent"})

    def test_no_drift_no_alert(self):
        FakeRunner.report = {"overall_status": "HEALTHY", "metrics": {}}
        with mock.patch.object(alerts, "send_alert") as send:
            job = self.job()
        send.assert_not_called()
        self.assertEqual((job["status"], job["results"][0]["alerts"]), ("done", {}))

    def test_a_broken_alert_never_fails_the_run(self):
        FakeRunner.report = DRIFT
        with mock.patch.object(alerts, "notify_drift", side_effect=RuntimeError("smtp exploded")):
            job = self.job()
        self.assertEqual((job["status"], job["results"][0]["status"]), ("done", "SUCCESS"))

    def test_test_alert_needs_a_channel_and_has_a_cooldown(self):
        self.assertEqual(self.c.post("/alerts/test").status_code, 400)
        with patch_settings(ALERT_WEBHOOK_URL=SECRET_URL), mock.patch("requests.post"):
            self.assertEqual(self.c.post("/alerts/test").json(), {"results": {"webhook": "sent"}})
            self.assertEqual(self.c.post("/alerts/test").status_code, 429)


if __name__ == "__main__":
    unittest.main()
