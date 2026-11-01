"""
data/passages.json 무결성 검증 + 채점 로직(assets/js/app.js의 submitAnswers 포팅) 검증.

Node/npm이 없는 샌드박스에서 JS를 직접 실행할 수 없으므로, 채점 로직을 파이썬으로
동일하게 재구현해 핵심 동작(정답 처리, 오답 처리, 미응답 처리)을 검증한다.
"""

import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "passages.json"


def load_passages():
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def grade(questions, answers):
    """assets/js/app.js submitAnswers()와 동일한 채점 로직."""
    correct_count = 0
    details = []
    for idx, q in enumerate(questions):
        chosen = answers.get(idx)
        is_correct = chosen == q["answerIndex"]
        if is_correct:
            correct_count += 1
        details.append(
            {
                "chosenText": "선택하지 않음" if chosen is None else q["options"][chosen],
                "correctText": q["options"][q["answerIndex"]],
                "isCorrect": is_correct,
            }
        )
    return correct_count, details


class TestPassagesData(unittest.TestCase):
    def setUp(self):
        self.passages = load_passages()

    def test_has_multiple_passages(self):
        self.assertGreaterEqual(len(self.passages), 3, "비문학 지문이 최소 3개 이상 있어야 함")

    def test_has_elementary_and_middle_level_passages(self):
        levels = {p["level"] for p in self.passages}
        self.assertIn("초등", levels, "초등학생용 지문이 최소 1개 이상 있어야 함")
        self.assertIn("중학", levels, "중학생용 지문이 최소 1개 이상 있어야 함")

    def test_unique_ids(self):
        ids = [p["id"] for p in self.passages]
        self.assertEqual(len(ids), len(set(ids)), "지문 id는 중복되면 안 됨")

    def test_required_fields_and_types(self):
        for p in self.passages:
            with self.subTest(passage=p.get("id")):
                self.assertIn("id", p)
                self.assertIn("title", p)
                self.assertIn("category", p)
                self.assertIn("level", p, "지문마다 난이도(level)가 있어야 함")
                self.assertIn(
                    p["level"], ["초등", "중학", "고등"], "난이도는 초등/중학/고등 중 하나여야 함"
                )
                self.assertIsInstance(p["paragraphs"], list)
                self.assertGreater(len(p["paragraphs"]), 0, "지문 본문 단락이 있어야 함")
                for para in p["paragraphs"]:
                    self.assertIsInstance(para, str)
                    self.assertGreater(len(para.strip()), 0)

                self.assertIsInstance(p["timeLimitSec"], int)
                self.assertGreater(p["timeLimitSec"], 0, "제한 시간은 0보다 커야 함")
                self.assertLessEqual(p["timeLimitSec"], 3600, "제한 시간이 비정상적으로 길면 안 됨")

    def test_reading_time_is_90_seconds(self):
        for p in self.passages:
            with self.subTest(id=p.get("id")):
                self.assertEqual(
                    p["timeLimitSec"], 90, "지문 읽는 시간은 1분30초(90초)로 설정되어야 함"
                )

                self.assertIsInstance(p["questions"], list)
                self.assertGreaterEqual(len(p["questions"]), 2, "지문당 문제가 최소 2개 이상 있어야 함")

    def test_questions_structure(self):
        for p in self.passages:
            for qi, q in enumerate(p["questions"]):
                with self.subTest(passage=p["id"], question=qi):
                    self.assertIn("question", q)
                    self.assertGreater(len(q["question"].strip()), 0)
                    self.assertIsInstance(q["options"], list)
                    self.assertEqual(len(q["options"]), 4, "선택지는 4개여야 함")
                    for opt in q["options"]:
                        self.assertIsInstance(opt, str)
                        self.assertGreater(len(opt.strip()), 0)

                    self.assertIsInstance(q["answerIndex"], int)
                    self.assertGreaterEqual(q["answerIndex"], 0)
                    self.assertLess(q["answerIndex"], len(q["options"]), "정답 인덱스는 선택지 범위 안에 있어야 함")

                    self.assertIn("explanation", q)
                    self.assertGreater(len(q["explanation"].strip()), 0)

    def test_no_duplicate_options_within_question(self):
        for p in self.passages:
            for qi, q in enumerate(p["questions"]):
                with self.subTest(passage=p["id"], question=qi):
                    self.assertEqual(
                        len(q["options"]), len(set(q["options"])), "같은 문제 안에 동일한 선택지가 있으면 안 됨"
                    )


class TestGradingLogic(unittest.TestCase):
    def setUp(self):
        self.passages = load_passages()
        self.sample_questions = self.passages[0]["questions"]

    def test_all_correct(self):
        answers = {i: q["answerIndex"] for i, q in enumerate(self.sample_questions)}
        correct_count, details = grade(self.sample_questions, answers)
        self.assertEqual(correct_count, len(self.sample_questions))
        self.assertTrue(all(d["isCorrect"] for d in details))

    def test_all_wrong(self):
        answers = {}
        for i, q in enumerate(self.sample_questions):
            wrong_idx = (q["answerIndex"] + 1) % len(q["options"])
            answers[i] = wrong_idx
        correct_count, details = grade(self.sample_questions, answers)
        self.assertEqual(correct_count, 0)
        self.assertTrue(all(not d["isCorrect"] for d in details))

    def test_unanswered_counts_as_wrong(self):
        correct_count, details = grade(self.sample_questions, {})
        self.assertEqual(correct_count, 0)
        for d in details:
            self.assertEqual(d["chosenText"], "선택하지 않음")
            self.assertFalse(d["isCorrect"])

    def test_partial_answers(self):
        answers = {0: self.sample_questions[0]["answerIndex"]}
        correct_count, _ = grade(self.sample_questions, answers)
        self.assertEqual(correct_count, 1)


class TestPassageLengthByLevel(unittest.TestCase):
    """학교급(초/중/고)별로 지문 길이가 차등 적용되는지 검증."""

    def setUp(self):
        self.passages = load_passages()

    def _avg_length(self, level):
        lengths = [
            sum(len(para) for para in p["paragraphs"])
            for p in self.passages
            if p["level"] == level
        ]
        self.assertTrue(lengths, f"{level} 지문이 없음")
        return sum(lengths) / len(lengths)

    def test_length_increases_with_school_level(self):
        elem = self._avg_length("초등")
        middle = self._avg_length("중학")
        high = self._avg_length("고등")
        self.assertLess(elem, middle, "중학 지문은 초등 지문보다 길어야 함")
        self.assertLess(middle, high, "고등 지문은 중학 지문보다 길어야 함")

    def test_high_school_passages_are_clearly_longer(self):
        elem = self._avg_length("초등")
        high = self._avg_length("고등")
        self.assertGreater(high, elem * 1.8, "고등 지문은 초등 지문보다 눈에 띄게 길어야 함")


# ---------------- 경험치(XP) / 레벨 / 칭호 로직 ----------------
# assets/js/app.js의 computeLevelInfo()와 동일한 규칙을 파이썬으로 재구현해 검증한다.

XP_PER_CORRECT = 10
XP_PER_LEVEL = 50
LEVEL_TITLES = [
    "글자 탐험가",
    "문장 수집가",
    "의미 추적자",
    "맥락 분석가",
    "논리 해결사",
    "지식 전략가",
    "통찰의 현자",
    "사고의 지배자",
    "진리의 개척자",
    "독해의 초월자",
]


def compute_level_info(total_xp):
    max_level = len(LEVEL_TITLES)
    safe_xp = max(0, total_xp or 0)
    level = min(max_level, safe_xp // XP_PER_LEVEL + 1)
    title = LEVEL_TITLES[level - 1]
    is_max = level >= max_level
    base = (level - 1) * XP_PER_LEVEL
    xp_into_level = XP_PER_LEVEL if is_max else safe_xp - base
    progress_percent = 100 if is_max else min(100, (xp_into_level / XP_PER_LEVEL) * 100)
    return {
        "level": level,
        "title": title,
        "isMax": is_max,
        "xpIntoLevel": xp_into_level,
        "progressPercent": progress_percent,
    }


class TestLevelingSystem(unittest.TestCase):
    def test_has_ten_titles_in_order(self):
        self.assertEqual(len(LEVEL_TITLES), 10)
        self.assertEqual(LEVEL_TITLES[0], "글자 탐험가")
        self.assertEqual(LEVEL_TITLES[-1], "독해의 초월자")

    def test_level_one_title_at_zero_xp(self):
        info = compute_level_info(0)
        self.assertEqual(info["level"], 1)
        self.assertEqual(info["title"], "글자 탐험가")

    def test_xp_awarded_per_correct_answer(self):
        correct_count = 3
        xp_gained = correct_count * XP_PER_CORRECT
        self.assertEqual(xp_gained, 30)

    def test_level_up_at_threshold(self):
        just_below = compute_level_info(XP_PER_LEVEL - 1)
        at_threshold = compute_level_info(XP_PER_LEVEL)
        self.assertEqual(just_below["level"], 1)
        self.assertEqual(at_threshold["level"], 2)
        self.assertEqual(at_threshold["title"], "문장 수집가")

    def test_caps_at_max_level(self):
        info = compute_level_info(XP_PER_LEVEL * 50)
        self.assertEqual(info["level"], 10)
        self.assertEqual(info["title"], "독해의 초월자")
        self.assertTrue(info["isMax"])
        self.assertEqual(info["progressPercent"], 100)

    def test_progress_percent_within_level(self):
        info = compute_level_info(25)  # 레벨1 구간 중간
        self.assertEqual(info["level"], 1)
        self.assertAlmostEqual(info["progressPercent"], 50.0)


if __name__ == "__main__":
    unittest.main()
