"""회원가입/로그인 API(app.py) 동작 검증."""

import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app as server_app  # noqa: E402


class TestAuth(unittest.TestCase):
    def setUp(self):
        server_app.app.testing = True
        self._tmpdir = tempfile.TemporaryDirectory()
        server_app.ACCOUNTS_DB_PATH = pathlib.Path(self._tmpdir.name) / "accounts.db"
        self.client = server_app.app.test_client()

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_signup_then_me_returns_user(self):
        res = self.client.post(
            "/api/auth/signup", json={"role": "student", "name": "홍길동", "password": "123456"}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["user"]["name"], "홍길동")

        me = self.client.get("/api/auth/me")
        self.assertEqual(me.get_json()["user"]["role"], "student")

    def test_signup_rejects_short_password(self):
        res = self.client.post(
            "/api/auth/signup", json={"role": "student", "name": "김철수", "password": "123"}
        )
        self.assertEqual(res.status_code, 400)

    def test_duplicate_name_in_same_role_is_rejected(self):
        self.client.post("/api/auth/signup", json={"role": "student", "name": "이영희", "password": "abcdef"})
        res = self.client.post("/api/auth/signup", json={"role": "student", "name": "이영희", "password": "abcdef"})
        self.assertEqual(res.status_code, 409)

    def test_same_name_allowed_across_different_roles(self):
        res1 = self.client.post("/api/auth/signup", json={"role": "student", "name": "박민수", "password": "abcdef"})
        res2 = self.client.post("/api/auth/signup", json={"role": "teacher", "name": "박민수", "password": "ghijkl"})
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res2.status_code, 200)

    def test_login_with_wrong_password_fails(self):
        self.client.post("/api/auth/signup", json={"role": "student", "name": "최수진", "password": "abcdef"})
        other_client = server_app.app.test_client()
        res = other_client.post(
            "/api/auth/login", json={"role": "student", "name": "최수진", "password": "wrongpw"}
        )
        self.assertEqual(res.status_code, 401)

    def test_login_with_correct_password_succeeds(self):
        self.client.post("/api/auth/signup", json={"role": "teacher", "name": "정선생", "password": "abcdef"})
        other_client = server_app.app.test_client()
        res = other_client.post(
            "/api/auth/login", json={"role": "teacher", "name": "정선생", "password": "abcdef"}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["user"]["role"], "teacher")

    def test_logout_clears_session(self):
        self.client.post("/api/auth/signup", json={"role": "student", "name": "강태오", "password": "abcdef"})
        self.client.post("/api/auth/logout")
        res = self.client.get("/api/auth/me")
        self.assertIsNone(res.get_json()["user"])

    def test_me_without_login_returns_null_user(self):
        res = self.client.get("/api/auth/me")
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(res.get_json()["user"])


if __name__ == "__main__":
    unittest.main()

class TestLibraryAccess(TestAuth):
    def test_level_survives_signup_login_and_refresh(self):
        data = {"role": "student", "name": "책읽기", "password": "abcdef", "level": "고등"}
        self.assertEqual(self.client.post('/api/auth/signup', json=data).get_json()['user']['level'], '고등')
        self.client.post('/api/auth/logout')
        self.assertEqual(self.client.post('/api/auth/login', json=data).get_json()['user']['level'], '고등')
        self.assertEqual(self.client.get('/api/auth/me').get_json()['user']['level'], '고등')

    def test_login_can_update_school_level(self):
        data = {"role": "student", "name": "학교급변경", "password": "abcdef", "level": "초등"}
        self.client.post('/api/auth/signup', json=data)
        self.client.post('/api/auth/logout')
        data['level'] = '고등'
        res = self.client.post('/api/auth/login', json=data)
        self.assertEqual(res.get_json()['user']['level'], '고등')
        self.assertEqual(self.client.get('/api/auth/me').get_json()['user']['level'], '고등')
        self.client.post('/api/auth/logout')
        data.pop('level')
        self.assertEqual(self.client.post('/api/auth/login', json=data).get_json()['user']['level'], '고등')

    def test_invalid_login_level_rejected(self):
        res = self.client.post('/api/auth/login', json={"role": "student", "name": "test", "password": "abcdef", "level": "invalid"})
        self.assertEqual(res.status_code, 400)

    def test_invalid_level_rejected(self):
        res = self.client.post('/api/auth/signup', json={"role": "student", "name": "test", "password": "abcdef", "level": "invalid"})
        self.assertEqual(res.status_code, 400)

    def test_trial_limit_persists_after_login_logout(self):
        self.assertEqual(self.client.get('/api/practice').get_json()['remaining'], 2)
        for expected in (1, 0):
            res = self.client.post('/api/practice')
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.get_json()['remaining'], expected)
        self.assertEqual(self.client.post('/api/practice').status_code, 403)
        self.client.post('/api/auth/signup', json={"role": "student", "name": "회원", "password": "abcdef"})
        for _ in range(3):
            self.assertTrue(self.client.post('/api/practice').get_json()['allowed'])
        self.client.post('/api/auth/logout')
        self.assertEqual(self.client.post('/api/practice').status_code, 403)

    def test_existing_accounts_gain_level_column(self):
        import sqlite3
        with sqlite3.connect(server_app.ACCOUNTS_DB_PATH) as conn:
            conn.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, role TEXT, name TEXT, password_hash TEXT, created_at TEXT)')
        with server_app._accounts_db() as conn:
            self.assertIn('level', [r[1] for r in conn.execute('PRAGMA table_info(users)')])
