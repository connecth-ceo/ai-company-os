# AI Company OS — Claude Code 인수인계 및 독립 검증 지침

작성일: 2026-08-26 (Asia/Seoul)
인계자: Codex
현재 단계: V0.4 로컬 구현 완료, 외부 서비스 연동 전

## 1. 당신의 첫 임무

이 저장소를 즉시 수정하기 전에 **현재 구현의 유효성을 독립적으로 검증**한다.

- 이 문서의 “통과” 주장을 그대로 신뢰하지 말고 직접 재현한다.
- 검증 결과와 구현 변경을 분리한다.
- 사용자가 수정까지 요청하지 않았다면 코드 변경 없이 검증 보고서만 작성한다.
- 실패를 숨기거나 우회하지 말고, 재현 명령·관찰 결과·원인 후보를 기록한다.
- API 키, 토큰, 비밀번호는 출력·로그·커밋·보고서에 절대 포함하지 않는다.

권장 첫 요청:

> CLAUDE.md를 모두 읽고 Validation Mission V1을 수행해줘. 먼저 코드와 설정을 검토한 뒤 자동 테스트, 정적 검사, 마이그레이션, mock HTTP 흐름을 독립적으로 재현해. Docker/OpenAI/Telegram/Render는 필요한 설정이 있는지 확인하되, 비밀값을 출력하지 말고 외부 호출이나 배포 전에 내 승인을 받아. 코드 수정 없이 PASS/FAIL/BLOCKED 근거와 우선순위별 개선안을 보고해줘.

## 2. 제품 목표와 범위

AI Company OS는 대표(사용자) 한 명이 자연어로 업무를 지시하면 AI 조직이 계획, 조사, 전략 수립, 검수, 최종 보고를 수행하는 개인용 회사 운영체제다.

조직 구조:

```text
CEO 사용자
  └─ Chief of Staff (업무 해석·계획·최종 보고)
       ├─ Research Agent (조사)
       ├─ Strategy Agent (전략)
       └─ Reviewer Agent (PASS / REWORK 검수)
```

V0의 핵심 원칙:

- 클라우드에서 24시간 실행 가능한 구조
- PostgreSQL을 업무 상태의 기준 저장소(source of truth)로 사용
- API 서버와 background worker 분리
- tasks, memories, decisions, knowledge, approvals, audit events 영속화
- mock AI로 전체 흐름을 무료 검증하고, 설정 변경만으로 OpenAI 실행
- 현재는 웹 CEO Desk와 Telegram webhook 제공
- 외부 발송, 결제, 삭제 등 실제 부작용이 있는 행위는 승인 없이 자동 수행하지 않음

## 3. 기술 구성

- Python 3.11+
- FastAPI / Uvicorn
- SQLAlchemy async / Alembic
- PostgreSQL (운영), SQLite (로컬 테스트)
- Celery / Redis
- OpenAI Agents SDK
- Docker / Docker Compose
- Render Blueprint (`render.yaml`)
- 정적 HTML/CSS/JavaScript CEO Desk
- Telegram Bot webhook

## 4. 먼저 읽을 파일

아래 순서로 읽고 실제 코드가 문서와 일치하는지 확인한다.

1. `README.md`
2. `docs/MASTER_IMPLEMENTATION_SPEC.md`
3. `docs/SETUP_AND_OPERATIONS_KO.md`
4. `.env.example` — 실제 `.env` 값은 출력하지 않는다.
5. `app/core/config.py`, `app/core/security.py`
6. `app/models.py`, `app/schemas.py`, `app/db.py`
7. `app/agents/prompts.py`, `app/agents/orchestrator.py`
8. `app/services/task_service.py`, `app/services/audit.py`
9. `app/api/routes.py`, `app/api/telegram.py`, `app/services/telegram.py`
10. `app/main.py`, `app/worker.py`, `app/web/`
11. `migrations/versions/`, `tests/`
12. `Dockerfile`, `docker-compose.yml`, `render.yaml`, `.github/workflows/ci.yml`

## 5. 인계 시점의 상태

Codex가 마지막으로 확인한 결과다. Claude Code는 반드시 다시 실행해 독립 검증한다.

| 영역 | 인계 시점 결과 | 독립 재검증 필요 |
|---|---|---|
| pytest | 12 passed | 예 |
| Ruff lint | 통과 | 예 |
| Alembic | upgrade → downgrade → upgrade 통과(SQLite 임시 DB) | 예 |
| mock HTTP E2E | 작업 생성 → 실행 → 완료, Reviewer PASS 확인 | 예 |
| CEO Desk browser E2E | 기억·결정 저장 → 업무 실행 → 맥락 반영 → 지식·승인 자동 생성 확인 | 예 |
| API key 인증/tenant 분리 | 자동 테스트 통과 | 예 |
| idempotency/audit/retry 경로 | 자동 테스트 통과 | 예 |
| Telegram webhook | mock 네트워크 테스트 통과 | 예 |
| Docker Compose | 로컬에 Docker가 없어 미검증 | 가능할 때만 |
| 실제 OpenAI 호출 | API 키가 없어 미검증 | 설정/승인 필요 |
| 실제 Telegram 송수신 | Bot token/chat ID가 없어 미검증 | 설정/승인 필요 |
| Render 배포 | GitHub/Render 연결 전, 미검증 | 계정/승인 필요 |
| 웹 화면 브라우저 QA | 기능 응답 확인, 실제 브라우저 시각 QA 미완료 | 예 |
| Git | `main`, 아직 최초 커밋 없음 | 현 상태 보존 |

## 6. Validation Mission V1

### A. 저장소 안전 점검

1. `git status --short --branch`로 상태를 기록한다.
2. 현재 파일은 아직 커밋되지 않았을 수 있다. 사용자 작업을 삭제, reset, checkout, clean 하지 않는다.
3. `.gitignore`에 `.env`, 가상환경, DB, 캐시가 포함됐는지 확인한다.
4. tracked/untracked 파일에서 비밀값 패턴을 검색하되 실제 값을 보고서에 복사하지 않는다.
5. `.env`를 열어야 한다면 설정의 존재 여부만 기록하고 값은 마스킹한다.

### B. 자동 테스트와 정적 검사

Windows PowerShell, 저장소 루트 기준:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check app migrations tests scripts
.\.venv\Scripts\python.exe -m compileall -q app migrations tests
```

가상환경이 없거나 깨졌다면 Python 3.11+로 새 환경을 만들고 dev 의존성을 설치한다. 설치가 필요한 경우 네트워크 사용 사실을 먼저 알린다.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

### C. 빈 데이터베이스 마이그레이션 왕복 검증

기존 DB나 운영 DB를 사용하지 않는다. `work` 아래 새 검증 DB를 사용하며 기존 파일을 덮어쓰지 않는다.

```powershell
$validationId = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$env:DATABASE_URL = "sqlite+aiosqlite:///./work/claude_validation_$validationId.db"
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic downgrade base
.\.venv\Scripts\python.exe -m alembic upgrade head
```

확인할 것:

- 모든 테이블과 인덱스 생성 여부
- downgrade 후 재-upgrade 성공 여부
- 현재 model metadata와 migration head 간 불일치 여부
- PostgreSQL 전용 타입/제약이 SQLite 테스트에서 가려지지 않는지

### D. mock 모드 실제 HTTP 흐름

비용 없는 mock 모드에서 서버를 실행한다.

```powershell
$env:DATABASE_URL = "sqlite+aiosqlite:///./work/claude_http_validation.db"
$env:AUTO_CREATE_SCHEMA = "true"
$env:TASK_EXECUTION_MODE = "inline"
$env:AI_PROVIDER = "mock"
$env:AUTH_ENABLED = "false"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

별도 터미널에서 다음을 검증한다.

```powershell
Invoke-RestMethod http://127.0.0.1:8765/health
Invoke-RestMethod http://127.0.0.1:8765/ready

$created = Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8765/api/v1/tasks `
  -ContentType "application/json" `
  -Body '{"request":"신제품 아이디어의 시장성과 실행 전략을 검토해줘","idempotency_key":"claude-validation-v1"}'

Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8765/api/v1/tasks/$($created.id)/run"

Start-Sleep -Seconds 2
Invoke-RestMethod "http://127.0.0.1:8765/api/v1/tasks/$($created.id)" | ConvertTo-Json -Depth 8
```

기대 결과:

- `/health`는 `ok`, `/ready`는 DB 확인 후 `ready`
- task가 `completed`로 이동
- Chief of Staff, Research, Strategy, Reviewer 산출물이 저장됨
- Reviewer verdict가 `PASS`
- task run/attempt 및 audit event가 남음
- 같은 idempotency key 재전송 시 중복 task가 생기지 않음
- 웹 루트 `/`가 CEO Desk HTML을 반환

`inline`은 HTTP 요청 프로세스 안에서 background task로 실행되므로 `/run` 직후 완료를 가정하지 말고 polling한다.

### E. 인증과 tenant 경계

자동 테스트 외에 최소 수동 확인도 권장한다.

- `AUTH_ENABLED=true` + 임시 `APP_API_KEY`에서 키 없는 API 요청이 401인지 확인
- 올바른 `X-API-Key` 요청이 통과하는지 확인
- 서로 다른 `X-Tenant-ID`가 상대 task/memory/decision/knowledge/approval/audit event를 조회하지 못하는지 확인
- API 키와 tenant 값은 보고서에서 마스킹

현재 인증은 개인용 V0를 위한 **단일 API 키 + tenant header** 모델이다. 완전한 사용자 계정/세션/역할 기반 인증으로 간주하지 않는다.

### F. worker와 Docker

Docker가 설치된 경우에만 다음을 실행한다.

```powershell
docker version
docker compose config
docker compose up --build
```

검증 항목:

- migrate 서비스 완료
- Postgres/Redis health check 통과
- API `/ready` 통과
- `TASK_EXECUTION_MODE=worker`에서 Celery가 task를 가져가 완료
- API와 worker 재시작 후에도 task/기억/결정/지식/승인/audit 데이터 유지
- worker 실패 시 retry/attempt/error 기록

주의: `docker compose down -v`는 DB 볼륨을 삭제하므로 사용자의 명시적 허가 없이 실행하지 않는다.

Docker가 없다면 BLOCKED로 기록하고 설치 방법만 안내한다. Docker 설치 자체를 임의로 수행하지 않는다.

### G. 실제 OpenAI 검증

조건:

- 사용자가 `OPENAI_API_KEY`를 안전하게 환경 변수 또는 `.env`에 직접 설정
- `AI_PROVIDER=openai`
- 비용 발생 가능성을 사용자에게 알리고 실제 호출 승인을 받음

승인 후 매우 작은 단일 task로 다음을 확인한다.

- 네 agent 단계가 실제 실행되는지
- structured output parsing 성공 여부
- Reviewer REWORK 루프와 최대 횟수 제한
- timeout/retry/error 저장
- input/output/total token usage 저장의 정확성
- 최종 보고와 하위 산출물이 DB에 영속화되는지

키를 채팅, 명령 출력, 스크린샷, 보고서에 노출하지 않는다. 실제 OpenAI 호출을 못 하면 mock 통과를 실제 AI 통과로 표현하지 않는다.

### H. 실제 Telegram 검증

필요 설정:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ALLOWED_CHAT_ID`
- `TELEGRAM_WEBHOOK_SECRET`
- 인터넷에서 접근 가능한 HTTPS API 주소

확인 순서:

1. webhook secret header가 틀리면 거부되는지 확인
2. 허용되지 않은 chat ID가 거부되는지 확인
3. `/start`, `/help`, `/status` 확인
4. 일반 메시지가 task를 하나만 생성하는지 확인
5. 완료 결과가 Telegram으로 돌아오는지 확인
6. 동일 update 재전송 시 idempotency가 유지되는지 확인

외부 webhook 등록/변경과 실제 메시지 발송 전에는 사용자 승인을 받는다.

### I. Render 배포 준비 검증

`render.yaml`의 문법과 환경 변수 연결을 검토한다. 실제 배포는 외부 상태 변경 및 비용 가능성이 있으므로 사용자 승인 없이 수행하지 않는다.

확인 항목:

- web, worker, Postgres, Redis 리소스 연결
- `preDeployCommand: alembic upgrade head`
- `/ready` health check
- production에서 `AUTH_ENABLED=true` 강제 여부
- secret 값이 blueprint에 평문으로 들어가지 않는지
- 배포 후 Telegram webhook URL 설정 순서
- 로그에 secret/요청 전문이 노출되지 않는지

## 7. 특히 의심하고 확인할 위험 지점

다음은 인계 시점에 남아 있는 검증 공백 또는 설계 한계다.

1. 실제 PostgreSQL + Redis + Celery 조합은 아직 로컬 통합 검증되지 않았다.
2. 실제 OpenAI 응답, structured output, 토큰 집계, timeout/retry는 API 키 없이 검증되지 않았다.
3. Telegram은 HTTP 호출을 mock 처리한 테스트만 통과했다.
4. Render blueprint는 원격 배포로 검증되지 않았다.
5. CEO Desk는 실제 브라우저 크기별 시각/접근성 검증이 필요하다.
6. Chief of Staff의 구조화된 승인 요청은 approval record로 자동 생성된다. 다만 승인 후 실제 발송·결제·삭제·배포를 실행하는 외부 도구는 의도적으로 아직 연결하지 않았다.
7. tenant 분리는 애플리케이션 쿼리 조건에 의존한다. 모든 route에서 누락이 없는지 점검한다.
8. 단일 API 키 방식은 개인용 V0용이다. 인터넷 공개 운영에서 완전한 인증 체계로 과대평가하지 않는다.
9. SQLite 통과가 PostgreSQL 동작을 완전히 보장하지 않는다. FK, enum, transaction, locking 차이를 점검한다.
10. 현재 Git 최초 커밋이 없을 수 있다. 사용자의 승인 없이 임의 commit/push/remote 연결을 하지 않는다.

## 8. 변경 시 지켜야 할 불변 조건

사용자가 검증 후 수정을 요청할 경우:

- 기존 사용자 파일과 변경을 보존한다.
- `.env` 또는 비밀값을 커밋하지 않는다.
- DB schema 변경은 Alembic migration으로 남긴다.
- task 상태 전이는 영속화하고 audit 가능하게 유지한다.
- tenant 경계를 모든 읽기/쓰기 API에 적용한다.
- 외부 부작용은 approval gate를 우회하지 않는다.
- mock 모드와 테스트를 유지한다.
- 수정 전 실패 재현 테스트를 추가하고, 수정 후 전체 회귀 테스트를 실행한다.
- 아키텍처를 크게 바꾸기 전에 근거와 trade-off를 사용자에게 설명한다.

## 9. 최종 검증 보고 형식

보고서는 다음 구조로 작성한다.

```text
# AI Company OS Validation Report

## 결론
- Overall: PASS / PASS WITH RISKS / FAIL / BLOCKED
- 즉시 운영 가능 범위:
- 아직 운영하면 안 되는 범위:

## 환경
- OS / Python / Docker / Git revision 또는 worktree 상태
- secret은 존재 여부만 표시하고 값은 모두 마스킹

## 검증 결과
| ID | 검증 항목 | 결과 | 실행 근거 | 비고 |
|---|---|---|---|---|

## 발견 사항
- P0: 보안/데이터 손실/핵심 흐름 차단
- P1: 운영 전 해결 필요
- P2: 개선 권장

## 외부 설정 때문에 못 한 검증
- 필요한 값 또는 계정
- 사용자가 설정하는 방법
- 설정 후 실행할 정확한 재검증 절차

## 코드 변경
- 없음 (검증 전용) 또는 변경 파일/이유/테스트 결과
```

PASS는 실행 근거가 있을 때만 사용한다. 외부 설정이 없어 못 한 항목은 FAIL이 아니라 BLOCKED로 분리하되, 운영 준비 완료로 계산하지 않는다.

## 10. 완료 기준

Validation Mission V1은 다음이 충족되면 완료다.

- 자동 테스트, lint, format check, compile check 결과 확보
- 신규 빈 DB migration 왕복 결과 확보
- mock HTTP E2E를 실제 서버에서 재현
- 보안/tenant/idempotency/audit 경계 검토
- Docker/OpenAI/Telegram/Render 각각 PASS 또는 구체적 BLOCKED 근거 기록
- 우선순위별 위험과 다음 행동 제시
- secret 미노출, 기존 데이터/작업 미파괴
