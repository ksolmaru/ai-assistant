# AI 개인 비서 — 프로젝트 가이드

## 프로젝트 개요

자연어로 대화하면서 업무와 일정을 관리하는 AI 비서 웹앱.
노션 대체를 목표로, 말하면 알아서 저장·정리해주는 비서처럼 동작한다.

**기술 스택:** Python + Flask + SQLite + Claude API (anthropic SDK) + Tailwind CSS

## 파일 구조

```
ai-assistant/
├── app.py          — Flask 라우팅 (/, /chat, /tasks, /greeting, /clear)
├── database.py     — SQLite 추상화 클래스 (DB 교체 시 이 파일만 수정)
├── tools.py        — Claude Tool Use 함수 6개 + 스키마 정의
├── ai_agent.py     — Claude API Tool Use 루프, 대화 기록 관리
├── templates/
│   └── index.html  — 탭 기반 UI (오늘/주간/월별/채팅)
├── .env            — ANTHROPIC_API_KEY (Git 제외)
└── requirements.txt
```

## 일정 카테고리

아래 카테고리를 기본으로 사용한다:

- **교회/찬양부** — 찬양팀 연습, 예배 일정, 찬양 리더 관련
- **공연팀** — 공연 준비, 리허설, 팀 미팅
- **부장님 보고/회의** — 업무 보고, 팀 회의, 사내 미팅
- **개인 약속** — 개인 일정, 약속, 기타

## 기본 일정 저장 형식

일정을 추가하거나 표시할 때 아래 형식을 기본으로 사용한다:

```
날짜(요일) 시간
제목:
장소:
인원: (숫자면 "N명" / 명단이면 이름 나열 / 둘 다면 "N명 (홍길동, 김철수)")
메모:
```

**DB 저장 방식:** title, due_date, due_time, location, attendees, description 각각 별도 컬럼에 저장.

## 코드 작성 규칙

- **초보자 친화적으로 작성** — 복잡한 추상화나 과도한 패턴 사용 금지
- **주석은 한국어로** — 함수·로직 설명은 모두 한국어
- **파일 역할 분리 유지** — DB 접근은 database.py에서만, Tool 함수는 tools.py에서만
- **에러 처리 필수** — API 호출과 DB 작업에는 반드시 try/except 포함
- **대화 기록은 최근 20개만** — 비용 절약을 위해 get_recent_messages(limit=20) 유지

## 실행 방법

```bash
cd ai-assistant
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
# → http://localhost:5000 접속
```
