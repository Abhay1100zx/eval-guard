import base64
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from evalguard import auth
from api import main

DOMAIN = "clerk.example.com"
PK = "pk_test_" + base64.b64encode(f"{DOMAIN}$".encode()).decode()
ISS = f"https://{DOMAIN}"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def token(key=KEY, iss=ISS, azp="http://localhost:3000", exp_in=300, sub="user_123"):
    now = int(time.time())
    return jwt.encode({"sub": sub, "iss": iss, "azp": azp, "iat": now, "exp": now + exp_in}, key, algorithm="RS256")


def hdr(**kw):
    return {"Authorization": f"Bearer {token(**kw)}"}


class FakeRunner:
    def __init__(self, domain, run_name=None, **_):
        self.domain = domain

    def run_evaluation(self, baseline_run_id=None, progress=None, **_):
        if self.domain == "legal":
            raise RuntimeError("provider exploded")
        if progress:
            progress(0, 2)
            progress(1, 2)
        return {"run": {"id": f"run-{self.domain}", "scorer": "mock"}, "indexed_chunks": 3,
                "drift_report": None, "drift_skipped_reason": None, "skipped": []}


class TestAuth(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        env = {"CLERK_PUBLISHABLE_KEY": PK, "EVALGUARD_AUTH_DISABLED": "", "CLERK_ISSUER": "", "CLERK_JWKS_URL": ""}
        p1 = mock.patch.dict("os.environ", env)
        p2 = mock.patch.object(auth, "_signing_key", lambda t: KEY.public_key())
        p1.start(); p2.start()
        self.addCleanup(p1.stop); self.addCleanup(p2.stop)

    def test_health_is_public(self):
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_missing_and_malformed_token(self):
        self.assertEqual(self.client.get("/domains").status_code, 401)
        self.assertEqual(self.client.get("/domains", headers={"Authorization": "Basic abc"}).status_code, 401)
        self.assertEqual(self.client.get("/domains", headers={"Authorization": "Bearer garbage"}).status_code, 401)

    def test_valid_token(self):
        r = self.client.get("/me", headers=hdr())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["user_id"], "user_123")
        self.assertEqual(len(self.client.get("/domains", headers=hdr()).json()["domains"]), 8)

    def test_rejected_tokens(self):
        self.assertEqual(self.client.get("/me", headers=hdr(exp_in=-100)).status_code, 401)      # expired
        self.assertEqual(self.client.get("/me", headers=hdr(iss="https://evil.com")).status_code, 401)  # issuer
        self.assertEqual(self.client.get("/me", headers=hdr(azp="https://evil.com")).status_code, 401)  # origin
        with mock.patch.object(auth, "_signing_key", lambda t: OTHER_KEY.public_key()):           # signature
            self.assertEqual(self.client.get("/me", headers=hdr()).status_code, 401)

    def test_unconfigured_fails_closed_and_dev_bypass(self):
        with mock.patch.dict("os.environ", {"CLERK_PUBLISHABLE_KEY": "", "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY": ""}):
            self.assertEqual(self.client.get("/me", headers=hdr()).status_code, 503)
            with mock.patch.dict("os.environ", {"EVALGUARD_AUTH_DISABLED": "true"}):
                r = self.client.get("/me")
                self.assertEqual(r.status_code, 200)
                self.assertTrue(r.json()["dev_mode"])


class TestCors(unittest.TestCase):
    """A browser sends a preflight before PUT/DELETE; if the API doesn't allow the method the call is blocked."""

    def test_preflight_allows_the_methods_the_web_app_uses(self):
        client = TestClient(main.app)
        for method in ("GET", "POST", "PUT", "DELETE"):
            r = client.options("/prompts/x", headers={"Origin": "http://localhost:3000",
                                                      "Access-Control-Request-Method": method,
                                                      "Access-Control-Request-Headers": "authorization,content-type"})
            self.assertEqual(r.status_code, 200, method)
            self.assertEqual(r.headers.get("access-control-allow-origin"), "http://localhost:3000")
            self.assertIn(method, r.headers.get("access-control-allow-methods", ""))

    def test_unknown_origin_is_not_allowed(self):
        r = TestClient(main.app).options("/prompts", headers={"Origin": "https://evil.example",
                                                              "Access-Control-Request-Method": "GET"})
        self.assertNotEqual(r.headers.get("access-control-allow-origin"), "https://evil.example")


class TestEndpoints(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        p = mock.patch.dict("os.environ", {"EVALGUARD_AUTH_DISABLED": "true"})
        p.start(); self.addCleanup(p.stop)

    def test_validation(self):
        self.assertEqual(self.client.post("/rag/query", json={"question": "what is x?", "domain": "hr", "top_k": 0}).status_code, 422)
        self.assertEqual(self.client.post("/rag/query", json={"question": "what is x?", "domain": "hr", "top_k": 99}).status_code, 422)
        self.assertEqual(self.client.post("/rag/query", json={"question": "what is x?", "domain": "nope"}).status_code, 400)
        self.assertEqual(self.client.post("/evaluate/run", json={"domain": "nope"}).status_code, 400)
        self.assertEqual(self.client.get("/runs/does-not-exist").status_code, 404)
        self.assertEqual(self.client.get("/jobs/does-not-exist").status_code, 404)

    def _wait(self, job_id):
        for _ in range(100):
            job = self.client.get(f"/jobs/{job_id}").json()
            if job["status"] in ("done", "failed"):
                return job
            time.sleep(0.05)
        self.fail("job did not finish")

    def test_job_lifecycle(self):
        with mock.patch.object(main, "EvaluationRunner", FakeRunner):
            r = self.client.post("/evaluate/run", json={"domain": "hr"})
            self.assertEqual(r.status_code, 202)
            job = self._wait(r.json()["job_id"])
            self.assertEqual(job["status"], "done")
            self.assertEqual(job["results"][0]["run"]["id"], "run-hr")

            # failing single domain -> failed job with the error surfaced
            job = self._wait(self.client.post("/evaluate/run", json={"domain": "legal"}).json()["job_id"])
            self.assertEqual(job["status"], "failed")
            self.assertIn("provider exploded", job["error"])

            # batch: one failing domain must not abort the others
            job = self._wait(self.client.post("/evaluate/all").json()["job_id"])
            self.assertEqual(job["status"], "done")
            statuses = {r["domain"]: r["status"] for r in job["results"]}
            self.assertEqual(statuses["legal"], "FAILED")
            self.assertEqual(statuses["hr"], "SUCCESS")
            self.assertEqual(len(statuses), 8)

    def test_upload_sanitizes_and_validates(self):
        import tempfile
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d, \
                mock.patch.object(main.settings, "DATA_DIR", Path(d)), \
                mock.patch.object(main.EvaluationRunner, "ingest_domain_data", lambda self: 7):
            bad = self.client.post("/domains/hr/documents", files=[("files", ("x.exe", b"hi"))])
            self.assertEqual(bad.status_code, 400)
            ok = self.client.post("/domains/hr/documents", files=[("files", ("../../evil.txt", b"hello"))])
            self.assertEqual(ok.status_code, 200)
            self.assertEqual(ok.json()["saved"], ["evil.txt"])
            self.assertTrue((Path(d) / "hr" / "documents" / "evil.txt").exists())
            self.assertFalse((Path(d).parent / "evil.txt").exists())


if __name__ == "__main__":
    unittest.main()
