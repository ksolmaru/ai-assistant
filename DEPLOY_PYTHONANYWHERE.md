# PythonAnywhere 배포 가이드

이 문서는 이 프로젝트를 PythonAnywhere에 배포하는 가장 간단한 절차를 정리한 가이드입니다.

## 1) PythonAnywhere 계정/웹앱 생성

1. PythonAnywhere 로그인
2. `Web` 탭 → `Add a new web app`
3. `Manual configuration` 선택
4. Python 버전은 로컬과 최대한 비슷하게 선택 (예: 3.10+)

## 2) Bash 콘솔에서 프로젝트 내려받기

```bash
cd ~
git clone <본인_레포_URL> ai-assistant
cd ai-assistant
```

이미 clone한 상태라면:

```bash
cd ~/ai-assistant
git pull
```

## 3) 가상환경 생성 + 패키지 설치

```bash
cd ~/ai-assistant
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 4) 환경변수 설정 (중요)

### 방법 A: Web 탭에서 환경변수 등록 (권장)

1. `Web` 탭 → `Environment variables`
2. 아래 추가
   - Key: `ANTHROPIC_API_KEY`
   - Value: `sk-ant-...`

### 방법 B: `.env` 파일 사용

```bash
cd ~/ai-assistant
cp .env.example .env
nano .env
```

`.env`에 실제 키 입력:

```env
ANTHROPIC_API_KEY=sk-ant-실제키
```

## 5) WSGI 파일 설정

`Web` 탭에서 WSGI configuration 파일을 열고, 기본 내용을 지운 뒤 아래처럼 설정하세요.

```python
import sys
import os

project_home = '/home/<PYTHONANYWHERE_USERNAME>/ai-assistant'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# 선택: .env 파일을 직접 읽고 싶다면 아래 3줄 사용
env_path = os.path.join(project_home, '.env')
if os.path.exists(env_path):
    from dotenv import load_dotenv
    load_dotenv(env_path)

from app import app as application
```

`<PYTHONANYWHERE_USERNAME>`는 본인 계정명으로 바꿔야 합니다.

## 6) Virtualenv 경로 연결

`Web` 탭의 `Virtualenv` 항목에 아래 경로 입력:

```text
/home/<PYTHONANYWHERE_USERNAME>/ai-assistant/.venv
```

## 7) 정적 파일(선택)

이 프로젝트는 Flask 템플릿 기반이라 필수는 아니지만, 추후 `static/` 폴더를 만들면 `Static files` 매핑을 추가하면 됩니다.

## 8) Reload 후 동작 확인

1. `Web` 탭에서 `Reload` 클릭
2. 사이트 접속 후:
   - `/` 페이지 로드
   - 채팅 전송 (`/chat`)
   - 일정 조회 (`/tasks`)

## 9) 오류 확인 포인트

문제가 생기면 `Web` 탭의 에러 로그를 먼저 확인하세요.

- `ModuleNotFoundError`: 가상환경 미연결 또는 `pip install -r requirements.txt` 미실행
- `ANTHROPIC_API_KEY가 설정되지 않았습니다`: 환경변수 또는 `.env` 누락
- SQLite 관련 오류: 파일 권한 또는 경로 문제 (`assistant.db`가 프로젝트 폴더에 생성됨)

## 10) 업데이트 배포 루틴

코드 수정 후 PythonAnywhere에서 아래만 반복하면 됩니다.

```bash
cd ~/ai-assistant
git pull
source .venv/bin/activate
pip install -r requirements.txt
```

그 다음 `Web` 탭에서 `Reload`를 누르세요.
