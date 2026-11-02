"""Flask 백엔드(app.py) 동작 검증: 정적 파일 서빙과 /api/passages 응답."""

import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app as server_app  # noqa: E402


class TestServer(unittest.TestCase):
    def setUp(self):
        server_app.app.testing = True
        self.client = server_app.app.test_client()

    def test_health_check(self):
        res = self.client.get("/healthz")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json(), {"status": "ok"})

    def test_index_served_at_root(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"<html", res.data.lower())

    def test_api_passages_returns_same_data_as_file(self):
        res = self.client.get("/api/passages")
        self.assertEqual(res.status_code, 200)
        with open(ROOT / "data" / "passages.json", encoding="utf-8") as f:
            expected = json.load(f)
        self.assertEqual(res.get_json(), expected)

    def test_static_asset_is_served(self):
        res = self.client.get("/assets/js/app.js")
        self.assertEqual(res.status_code, 200)

    def test_unknown_path_is_404(self):
        res = self.client.get("/does-not-exist.txt")
        self.assertEqual(res.status_code, 404)

    def test_data_file_is_served_for_static_fallback(self):
        res = self.client.get("/data/passages.json")
        self.assertEqual(res.status_code, 200)

    def test_server_and_secret_files_are_not_served(self):
        for path in ("/app.py", "/requirements.txt", "/README.md", "/.env", "/.gitignore",
                     "/tests/test_server.py", "/.github/workflows/check.yml", "/assets/../app.py"):
            with self.subTest(path=path):
                res = self.client.get(path)
                self.assertEqual(res.status_code, 404)

    def test_path_traversal_is_blocked(self):
        res = self.client.get("/../app.py")
        self.assertIn(res.status_code, (404, 400))


if __name__ == "__main__":
    unittest.main()
