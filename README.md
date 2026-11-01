# 읽는 힘 — 비문학 독해 연습

비즈코더에서 만든 초등·중학·고등 수준의 비문학 독해 연습 웹 앱입니다.
별도 패키지 설치나 빌드 없이 정적 HTTP 서버에서 실행합니다.

## 주요 기능

- 학교급별 지문 필터와 객관식 문제 풀이
- 지문별 90초 타이머와 시간 종료 시 자동 제출
- 형광펜·밑줄·지우개, 문제 풀이 중 지문 가리기와 다시 보기
- 정답·해설 확인, 정답당 10 XP 지급 및 10단계 레벨·칭호
- 브라우저 `localStorage`에 누적 XP 저장

타이머는 지문을 선택할 때 시작하며, 읽기와 문제 풀이 시간을 함께 계산합니다.

## 폴더 구조

```text
.
├── index.html                  # 앱 진입점
├── assets/
│   ├── css/styles.css          # 화면 스타일
│   └── js/app.js               # 화면·타이머·채점·XP 동작
├── data/passages.json          # 지문·문제·정답·해설
├── tests/test_passages.py      # 데이터 무결성 및 Python으로 재현한 로직 검증
└── .github/workflows/check.yml # 푸시·PR 자동 검증
```

## 로컬 실행

Python 3가 설치된 환경에서 저장소 루트에서 실행합니다.

```sh
python3 -m http.server 8000 --bind 127.0.0.1
```

브라우저에서 <http://localhost:8000>을 엽니다. 종료하려면 `Ctrl+C`를 누릅니다.
지문은 `fetch()`로 불러오므로 HTML 파일을 직접 열기보다 HTTP 서버를 사용하세요.
글꼴은 외부 CDN에서 불러오며, 연결할 수 없으면 시스템 글꼴을 사용합니다.

정적 호스팅 시 `index.html`, `assets/`, `data/`를 같은 루트에 배치합니다.
상대 경로를 사용하므로 하위 경로에서도 실행할 수 있습니다.

## 검증

```sh
python3 -m unittest discover -s tests -v
node --check assets/js/app.js
```

첫 명령은 지문 구조·학교급별 분량과 Python으로 재현한 채점·레벨 계산을 검증합니다.
두 번째 명령은 Node.js로 JavaScript 문법을 확인합니다.
Python 테스트는 실제 브라우저 JavaScript 실행을 대신하지 않습니다.
화면 변경 후에는 지문 선택, 문제 이동, 채점, XP 저장, 표시 도구도 브라우저에서 확인하세요.

## 지문 추가

`data/passages.json` 배열에 기존 항목과 같은 형식으로 지문을 추가합니다.
`id`는 고유해야 하고, `level`은 `초등`, `중학`, `고등` 중 하나입니다.
`timeLimitSec`는 현재 정책에 따라 `90`을 사용합니다.
문제마다 선택지 4개와 0부터 시작하는 `answerIndex`, `explanation`을 포함합니다.
