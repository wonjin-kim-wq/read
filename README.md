# 읽는 힘 — 비문학 독해 연습

비즈코더에서 만든 초등·중학·고등 수준의 비문학 독해 연습 웹 앱입니다.
Flask 백엔드(`app.py`)가 정적 파일과 지문 데이터를 함께 제공하며, 외부 API를 연동할 때
API 키 등 민감한 값을 서버에서만 다루도록 구조화되어 있습니다.

## 주요 기능

- 학교급별 지문 필터와 객관식 문제 풀이
- 지문별 90초 타이머와 시간 종료 시 자동 제출
- 형광펜·밑줄·지우개, 문제 풀이 중 지문 가리기와 다시 보기
- 정답·해설 확인, 정답당 10 XP 지급 및 10단계 레벨·칭호
- 브라우저 `localStorage`에 누적 XP 저장
- 첫 진입 인트로 애니메이션(원고지 네 칸 + 두 문구, 약 7초)과 건너뛰기
- 휴대폰에서도 길게 눌러 선택한 범위에 형광펜·밑줄 적용(읽는 동안 표시 도구를 화면 아래에 고정)

타이머는 지문을 선택할 때 시작하며, 읽기와 문제 풀이 시간을 함께 계산합니다.

## 폴더 구조

```text
.
├── app.py                       # Flask 백엔드: 정적 파일 + /api/passages + /api/generate
├── question_generator.py        # Gemini 문제 생성·검증 모듈
├── requirements.txt             # Python 의존성 (Flask, requests, google-genai)
├── index.html                   # 앱 진입점
├── assets/
│   ├── css/styles.css          # 화면 스타일
│   ├── css/intro.css           # 첫 진입 인트로 스타일
│   ├── js/intro.js             # 첫 진입 인트로(독립 컴포넌트)
│   └── js/app.js               # 화면·타이머·채점·XP 동작 (지문은 /api/passages 호출)
├── data/passages.json          # 지문·문제·정답·해설 (서버가 읽어 API로 내려줌)
├── tests/test_passages.py      # 데이터 무결성 및 Python으로 재현한 로직 검증
├── tests/test_server.py        # Flask 백엔드(app.py) 라우트 검증
├── tests/test_generate.py      # AI 문제 만들기 API 검증 (Gemini 모의 응답)
└── .github/workflows/check.yml # 푸시·PR 자동 검증
```

## 로컬 실행

Python 3가 설치된 환경에서 저장소 루트에서 실행합니다.

```sh
pip install -r requirements.txt
python3 app.py
```

브라우저에서 <http://localhost:8000>을 엽니다. 종료하려면 `Ctrl+C`를 누릅니다.
지문은 프런트엔드(`assets/js/app.js`)가 `/api/passages`를 호출해 받아오며, 이 엔드포인트는
서버(`app.py`)가 `data/passages.json`을 시드로 만든 SQLite DB(`instance/passages.db`,
최초 요청 시 자동 생성)를 읽어 내려준다.
서버 없이 정적 호스팅된 경우 지문 목록은 `data/passages.json`에서 읽지만, 로그인·체험 횟수 검증이 필요한 학습 시작은 Flask 서버가 필요합니다.
서버는 `index.html`, `assets/`, `data/` 아래 파일만 내려주며 `app.py`·`.env`·`tests/` 등은 404로 막습니다.
글꼴(본문 MaruBuri, 손글씨 Nanum Pen Script)은 외부 CDN에서 불러오며, 연결할 수 없으면 시스템 글꼴을 사용합니다.

배포 시 플랫폼이 `PORT` 환경변수를 주입하며, `app.py`는 `0.0.0.0`에 바인딩합니다.

### AI 문제 만들기 (Gemini)

지문 선택 화면의 **문제 만들기** 탭에서 지문을 붙여 넣거나 PDF(5MB 이하)를 올리면,
서버(`app.py` → `question_generator.py`)가 Google Gemini로 4지선다 독해 문제 5개를 만듭니다.
만든 문제는 브라우저에 저장되어 다른 지문처럼 밑줄·형광펜을 그으며 풀 수 있고 XP도 쌓입니다.

- AI 응답은 JSON으로 받아 코드로 검증합니다(보기 4개·중복 없음·정답 1개·근거 문장이 지문에 실제로 있는지). 통과한 문제가 3개 미만이면 실패로 처리합니다.
- 같은 지문·같은 학교급을 다시 넣으면 저장된 문제를 재사용하고 횟수를 차감하지 않습니다.
- 전화번호·이메일·주민번호가 보이는 글은 AI로 보내지 않습니다. 지문 안의 명령문은 지시로 취급하지 않도록 프롬프트에 명시했습니다.
- 실패해도 다시 호출하지 않으며, 기존 학습 기능은 그대로 동작합니다.

배포 환경변수(키는 코드·저장소에 넣지 않습니다):

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `GEMINI_API_KEY` | 없음(필수) | Google AI Studio에서 발급한 키 |
| `GEMINI_MODEL` | `gemini-flash-lite-latest` | 사용할 모델. 더 신중한 문제가 필요하면 `gemini-flash-latest`(느림). 무료 지원 모델은 AI Studio에서 확인 |
| `GEMINI_THINKING_BUDGET` | `0` | 답하기 전 '생각' 분량. 작을수록 빠름. `off`면 모델 기본값(느리지만 신중) |
| `GENERATE_DAILY_LIMIT_PER_USER` | `3` | 한 사용자(접속 주소)당 하루 생성 횟수 |
| `GENERATE_DAILY_LIMIT_TOTAL` | `15` | 사이트 전체 하루 생성 횟수 |
| `USAGE_DB_PATH` | `instance/usage.db` | 사용 횟수·생성 결과를 저장하는 SQLite 파일 |

하루 기준은 Gemini 무료 한도와 같은 미국 태평양 시간 자정입니다.
무료 한도는 Google이 예고 없이 바꿀 수 있으니 AI Studio에서 모델별 하루 요청 수(RPD)를 확인하고 `GENERATE_DAILY_LIMIT_TOTAL`을 그보다 작게 두세요.

## 첫 진입 인트로

- 브라우저 탭마다 처음 한 번만 자동 재생합니다. 같은 탭에서 새로고침하거나 돌아오면 바로 메인 화면을 보여 줍니다(`sessionStorage`의 `readingIntroSeen`).
- 오른쪽 위 **건너뛰기** 버튼이나 `Esc`로 즉시 종료합니다. 건너뛴 탭에서도 다시 자동 재생하지 않습니다.
- 운영체제의 '동작 줄이기'(`prefers-reduced-motion`)가 켜져 있으면 완성 화면만 짧게 보여 줍니다.
- 주소 뒤에 `?intro=1`을 붙이면 이미 본 탭에서도 다시 재생합니다(미리보기용).
- **인트로 다시 보기** 버튼은 개발·시연용입니다. `assets/js/intro.js`의 `INTRO_CONFIG.showReplayButton`으로 관리하며,
  기본값 `"auto"`는 `localhost`·`127.0.0.1`에서만 보이고 배포 주소에서는 숨깁니다. `true`/`false`로 강제할 수 있습니다.

## 검증

```sh
python3 -m unittest discover -s tests -v
node --check assets/js/app.js
node --check assets/js/intro.js
```

첫 명령은 지문 구조·학교급별 분량, Python으로 재현한 채점·레벨 계산, 인트로 파일 연결,
그리고 Flask 백엔드(`app.py`)의 라우트(`/`, `/api/passages`, 정적 파일)를 검증합니다.
나머지 명령은 Node.js로 JavaScript 문법을 확인합니다.
Python 테스트는 실제 브라우저 JavaScript 실행을 대신하지 않습니다.
화면 변경 후에는 지문 선택, 문제 이동, 채점, XP 저장, 표시 도구(휴대폰 포함), 인트로 재생·건너뛰기도 브라우저에서 확인하세요.

## 지문 추가

`data/passages.json` 배열에 기존 항목과 같은 형식으로 지문을 추가합니다.
`id`는 고유해야 하고, `level`은 `초등`, `중학`, `고등` 중 하나입니다.
`timeLimitSec`는 현재 정책에 따라 `90`을 사용합니다.
문제마다 선택지 4개와 0부터 시작하는 `answerIndex`, `explanation`을 포함합니다.

## 학교급 책장과 로그인·체험

- 첫 화면에서 초등학교·중학교·고등학교 입체 노트를 선택하면 붉은 글칸이 있는 세로 원고지가 한 장씩 책에서 펼쳐져 정렬됩니다. 원고지마다 지문 제목이 한 칸에 한 글자씩 표시됩니다. 노트는 표지·책등·종이 단면의 깊이와 공중 부유 모션을 표현하며, 마우스나 키보드로 선택 중에는 부유를 멈춥니다. 동작 줄이기를 설정하면 펼침 애니메이션을 생략합니다.
- 회원가입 때 학교급을 선택합니다. 로그인·새로고침 시 자신의 학교급 책과 지문이 자동으로 열리며 다른 책도 선택할 수 있습니다. 기존 계정은 중학교로 초기화됩니다.
- 비회원은 읽기 시작·다시 풀기를 합쳐 총 2회 체험합니다. 중도에 목록으로 돌아가도 시작한 횟수는 차감됩니다. 로그인한 회원은 이 제한이 없습니다.
- 체험 횟수는 익명 브라우저 쿠키와 서버 SQLite로 관리합니다. 쿠키 삭제·다른 브라우저까지 동일인으로 식별하지는 못합니다. 서버 없는 정적 호스팅에서는 학습 시작을 지원하지 않습니다.
- 운영 시 `SECRET_KEY`를 고정하고 `instance/`를 영구 저장소에 보관하세요. `ACCOUNTS_DB_PATH`, `PASSAGES_DB_PATH`, `USAGE_DB_PATH`로 DB 위치를 지정할 수 있습니다. 저장소가 유지되지 않으면 계정·횟수·저장 지문이 재배포 때 초기화될 수 있습니다.
- 지문 DB는 JSON을 최초 1회 시드합니다. 이미 생성된 DB에는 이후 JSON 변경이 자동 반영되지 않습니다.
