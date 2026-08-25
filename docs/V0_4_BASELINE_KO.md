# AI Company OS V0.4 기준선 기록

- 기준일: 2026-08-26
- 기준 브랜치: `main`
- 기준 태그: `v0.4-baseline`
- 목적: V2 리팩터링 전 정상 동작하는 V0.4를 재현 가능한 상태로 보존한다.

## 기준선에 포함된 기능

- FastAPI API와 CEO Web Dashboard
- Task/TaskRun, Memory, Decision, Knowledge, Approval, AuditEvent 저장
- Chief of Staff, Research, Strategy, Reviewer 고정 오케스트레이션
- Research와 Strategy 병렬 실행
- Reviewer PASS/REWORK와 제한된 재작업
- OpenAI Agents SDK 실행 모드와 API 키가 필요 없는 mock 모드
- 회사 기억·의사결정·지식의 프롬프트 주입
- Celery/Redis 백그라운드 실행 경계
- Telegram webhook, 허용 chat ID 및 webhook secret 검사
- Docker/Docker Compose, Alembic, Render Blueprint

## 기준 검증 결과

2026-08-26 로컬 Python 가상환경에서 다음 검사를 수행했다.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

결과:

- 테스트: `12 passed`
- Ruff: `All checks passed`
- 커밋 후보에서 API key, private key, 비밀번호·토큰 할당 형태의 민감정보 패턴: 발견되지 않음
- `.env`, 로컬 DB, `.venv`, `outputs`, `work`: Git ignore 확인

## 현재 환경변수 상태

실제 값은 기록하지 않는다. 분석 시점의 설정 유무만 기록한다.

| 변수 | 상태 | 용도 |
|---|---|---|
| `AI_PROVIDER` | `mock` | AI 실행 모드 |
| `OPENAI_API_KEY` | 비어 있음 | 실제 OpenAI 호출 |
| `TELEGRAM_BOT_TOKEN` | 비어 있음 | Telegram Bot API |
| `TELEGRAM_WEBHOOK_SECRET` | 비어 있음 | webhook 요청 검증 |
| `TELEGRAM_ALLOWED_CHAT_ID` | 비어 있음 | CEO Telegram 계정 제한 |
| `APP_API_KEY` | 비어 있음 | 앱 API 인증 |
| `DATABASE_URL` | 설정됨 | 현재 PostgreSQL 형식 설정 |
| `REDIS_URL` | 설정됨 | worker broker/backend |
| `TASK_EXECUTION_MODE` | `worker` | Celery 작업 실행 |
| `AUTO_CREATE_SCHEMA` | `false` | Alembic migration 사용 |
| `AUTH_ENABLED` | `false` | 로컬 인증 비활성화 |

비밀값은 `.env` 또는 배포 서비스의 Secret 설정에만 저장하며 문서, Git, 이슈, 채팅에 복사하지 않는다.

## 실행 방법

### 비용 없는 로컬 mock 실행

Windows 탐색기에서 `START_AI_COMPANY_MOCK.bat`을 실행한다. 이 스크립트는 로컬 SQLite,
inline 작업, mock AI를 사용하며 브라우저에서 `http://127.0.0.1:8000`을 연다.

### 실제 OpenAI 로컬 실행

`.env`의 `OPENAI_API_KEY`를 설정한 뒤 `START_AI_COMPANY_REAL_AI.bat`을 실행한다. API 비용이 발생할 수
있으며 키가 없으면 설정 검증 단계에서 안전하게 중단된다.

### Docker 전체 실행

```powershell
Copy-Item -LiteralPath .env.example -Destination .env
docker compose up --build
```

브라우저에서 `http://localhost:8000`을 열고, API 문서는 `http://localhost:8000/docs`, 준비 상태는
`http://localhost:8000/ready`에서 확인한다.

### 개발 테스트

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

환경변수 전체 설명과 Telegram/Render 설정은 `docs/SETUP_AND_OPERATIONS_KO.md`를 따른다.

## 아직 검증되지 않은 범위

- 실제 OpenAI API 응답과 비용·토큰 기록
- Docker의 API/Worker/PostgreSQL/Redis 종단 간 실행
- 실제 Telegram 송수신
- Render 또는 VPS의 24시간 배포
- 외부 행동 도구 실행

이 항목은 사용자 계정, 비밀값 또는 로컬 Docker 설치가 필요하므로 기준선의 자동 테스트 범위에 포함하지 않는다.

## 기준선으로 복귀하는 방법

기준선 코드를 별도 확인하려면 현재 작업을 먼저 커밋하거나 안전하게 보관한 뒤 다음 태그에서 새 브랜치를 만든다.

```powershell
git switch -c recovery-v0.4 v0.4-baseline
```

기존 작업 폴더에서 추적되지 않은 파일을 삭제하거나 강제 초기화하는 명령은 사용하지 않는다. 데이터 복구는
`docs/DB_BACKUP_RESTORE_KO.md`의 절차를 따른다.
