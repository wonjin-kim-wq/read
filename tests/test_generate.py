"""AI 문제 만들기(/api/generate) 검증. 실제 Gemini는 호출하지 않고 응답을 흉내 낸다."""

import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app as server_app  # noqa: E402
import question_generator as qg  # noqa: E402

PASSAGE = (
    "꿀벌은 꽃에서 꿀과 꽃가루를 모아 벌집으로 가져간다. 이 과정에서 꽃가루가 다른 꽃으로 옮겨져 식물이 열매를 맺는다.\n\n"
    "과학자들은 꿀벌의 수가 줄어들면 사과와 딸기 같은 과일 생산이 크게 줄어들 수 있다고 경고한다. "
    "그래서 여러 나라에서 꿀벌이 살 수 있는 꽃밭을 늘리는 활동을 하고 있다.\n\n"
    "꿀벌을 지키는 일은 우리 식탁을 지키는 일과 같다. 작은 곤충 하나가 생태계 전체에 큰 영향을 주기 때문이다."
)


def fake_response(count=5, evidence="꿀벌은 꽃에서 꿀과 꽃가루를 모아 벌집으로 가져간다."):
    questions = []
    for i in range(count):
        questions.append(
            {
                "type": "fact",
                "question": f"꿀벌에 대한 설명으로 알맞은 것은? ({i + 1})",
                "options": [f"보기 가{i}", f"보기 나{i}", f"보기 다{i}", f"보기 라{i}"],
                "answer": 2,
                "explanation": "지문 첫 문단에 나와 있다.",
                "evidence": evidence,
            }
        )
    return json.dumps(
        {"title": "꿀벌과 생태계", "category": "과학", "paragraphs": ["무시됨"], "questions": questions},
        ensure_ascii=False,
    )


class GenerateTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_patch = mock.patch.object(server_app, "USAGE_DB_PATH", pathlib.Path(self.tmp.name) / "usage.db")
        self.db_patch.start()
        self.env = mock.patch.dict(
            os.environ,
            {"GEMINI_API_KEY": "test-key", "GENERATE_DAILY_LIMIT_PER_USER": "2", "GENERATE_DAILY_LIMIT_TOTAL": "3"},
        )
        self.env.start()
        server_app.app.testing = True
        self.client = server_app.app.test_client()

    def tearDown(self):
        self.env.stop()
        self.db_patch.stop()
        self.tmp.cleanup()

    def post(self, text=PASSAGE, level="중학", ip="1.1.1.1", **extra):
        data = {"level": level, "text": text, **extra}
        return self.client.post("/api/generate", data=data, headers={"X-Forwarded-For": ip})


class TestGenerateEndpoint(GenerateTestBase):
    def test_generates_passage_in_app_format(self):
        with mock.patch.object(qg, "call_gemini", return_value=fake_response()) as call:
            res = self.post()
        self.assertEqual(res.status_code, 200, res.get_json())
        body = res.get_json()
        passage = body["passage"]
        call.assert_called_once()
        self.assertEqual(passage["level"], "중학")
        self.assertEqual(passage["source"], "ai")
        self.assertEqual(passage["timeLimitSec"], 90)
        self.assertEqual(len(passage["paragraphs"]), 3, "직접 넣은 글은 원문 문단을 그대로 쓴다")
        self.assertEqual(len(passage["questions"]), 5)
        q = passage["questions"][0]
        self.assertEqual(q["answerIndex"], 1, "AI의 1~4 정답 번호를 앱의 0~3으로 바꾼다")
        self.assertIn("근거:", q["explanation"])
        self.assertEqual(body["remainingToday"], 1)

    def test_same_input_reuses_saved_questions_without_calling_ai(self):
        with mock.patch.object(qg, "call_gemini", return_value=fake_response()) as call:
            first = self.post()
            second = self.post()
        self.assertEqual(call.call_count, 1)
        self.assertTrue(second.get_json()["cached"])
        self.assertEqual(first.get_json()["passage"]["id"], second.get_json()["passage"]["id"])
        self.assertEqual(second.get_json()["remainingToday"], 1, "재사용은 횟수를 차감하지 않는다")

    def test_daily_limit_per_user(self):
        with mock.patch.object(qg, "call_gemini", return_value=fake_response()) as call:
            self.assertEqual(self.post(text=PASSAGE + " 하나").status_code, 200)
            self.assertEqual(self.post(text=PASSAGE + " 둘").status_code, 200)
            res = self.post(text=PASSAGE + " 셋")
        self.assertEqual(res.status_code, 429)
        self.assertEqual(call.call_count, 2, "한도를 넘으면 AI를 호출하지 않는다")

    def test_daily_limit_total_across_users(self):
        with mock.patch.object(qg, "call_gemini", return_value=fake_response()):
            self.post(text=PASSAGE + " 1", ip="1.1.1.1")
            self.post(text=PASSAGE + " 2", ip="2.2.2.2")
            self.post(text=PASSAGE + " 3", ip="3.3.3.3")
            res = self.post(text=PASSAGE + " 4", ip="4.4.4.4")
        self.assertEqual(res.status_code, 429)

    def test_status_reports_remaining(self):
        res = self.client.get("/api/generate/status", headers={"X-Forwarded-For": "9.9.9.9"})
        body = res.get_json()
        self.assertTrue(body["enabled"])
        self.assertEqual(body["remainingToday"], 2)
        self.assertNotIn("test-key", res.get_data(as_text=True), "API 키는 응답에 절대 포함되지 않는다")

    def test_missing_api_key(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            status = self.client.get("/api/generate/status").get_json()
            res = self.post()
        self.assertFalse(status["enabled"])
        self.assertEqual(res.status_code, 503)

    def test_rejects_short_text_and_personal_info(self):
        with mock.patch.object(qg, "call_gemini") as call:
            self.assertEqual(self.post(text="너무 짧은 글").status_code, 400)
            self.assertEqual(self.post(text=PASSAGE + " 연락처 010-1234-5678").status_code, 400)
            self.assertEqual(self.post(text="가" * 8001).status_code, 400)
            self.assertEqual(self.post(level="대학").status_code, 400)
        call.assert_not_called()

    def test_rejects_non_pdf_upload(self):
        import io

        res = self.client.post(
            "/api/generate",
            data={"level": "중학", "file": (io.BytesIO(b"not a pdf"), "a.pdf")},
            content_type="multipart/form-data",
        )
        self.assertEqual(res.status_code, 400)

    def test_pdf_upload_uses_ai_extracted_paragraphs(self):
        import io

        response = json.loads(fake_response())
        response["paragraphs"] = PASSAGE.split("\n\n")
        with mock.patch.object(qg, "call_gemini", return_value=json.dumps(response, ensure_ascii=False)) as call:
            res = self.client.post(
                "/api/generate",
                data={"level": "고등", "file": (io.BytesIO(b"%PDF-1.4 fake"), "a.pdf")},
                content_type="multipart/form-data",
            )
        self.assertEqual(res.status_code, 200, res.get_json())
        self.assertEqual(call.call_args.kwargs["pdf_bytes"], b"%PDF-1.4 fake")
        self.assertEqual(len(res.get_json()["passage"]["paragraphs"]), 3)

    def test_quota_error_from_gemini_is_not_counted(self):
        err = qg.GenerationError("오늘 AI 사용 한도를 다 썼어요.", 429)
        with mock.patch.object(qg, "call_gemini", side_effect=err):
            res = self.post()
        self.assertEqual(res.status_code, 429)
        self.assertEqual(res.get_json()["remainingToday"], 2)


class TestQuestionValidation(unittest.TestCase):
    def test_drops_questions_whose_evidence_is_not_in_passage(self):
        data = json.loads(fake_response(evidence="지문에 없는 문장이다."))
        self.assertEqual(qg.validate_questions(data["questions"], PASSAGE), [])

    def test_drops_bad_options_and_answers(self):
        good = json.loads(fake_response(count=1))["questions"][0]
        bad = [
            {**good, "question": "a", "options": ["1", "2", "3"]},
            {**good, "question": "b", "options": ["같음", "같음", "다름", "또"]},
            {**good, "question": "c", "answer": 5},
            {**good, "question": "d", "answer": True},
            {**good, "question": "e", "explanation": ""},
        ]
        self.assertEqual(len(qg.validate_questions(bad + [good], PASSAGE)), 1)

    def test_too_few_valid_questions_is_an_error(self):
        with self.assertRaises(qg.GenerationError):
            qg.build_passage(fake_response(count=2), "중학", "ai-x", text=PASSAGE)

    def test_invalid_json_is_an_error(self):
        with self.assertRaises(qg.GenerationError):
            qg.build_passage("not json", "중학", "ai-x", text=PASSAGE)

    def test_prompt_treats_passage_as_data(self):
        self.assertIn("절대 따르지", qg.SYSTEM_INSTRUCTION)


if __name__ == "__main__":
    unittest.main()
