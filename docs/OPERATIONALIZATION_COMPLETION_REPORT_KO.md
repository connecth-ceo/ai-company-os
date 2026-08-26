# AI Company OS 운영화 단계 완료 보고서

- 기준일: 2026-08-26 (Asia/Seoul)
- 기준선: V0.4 제어 흐름 + Phase 1 AgentRuntime/AgentDefinition/Registry
- Phase 2 Hermes: 시작하지 않음
- 목적: 실제 OpenAI, PostgreSQL/Redis/Celery, Telegram, Docker/VPS 운영을 위한 코드와 검증 경로 완성

## 결론

기존 `Research + Strategy → Chief of Staff → Reviewer → 승인/기억 저장` 흐름과 Phase 1 Runtime/Registry
경계를 변경하지 않고 운영화 계층을 추가했다. 코드 수준의 운영 준비, mock E2E, 설정 보안, worker 복구,
Telegram webhook/회신 경계, Docker/Render/VPS 배포 정의와 smoke 도구는 완료했다.

현재 컴퓨터에서 Docker Desktop/WSL 2를 구성하고 PostgreSQL, Redis, migration, API, Celery worker와
mock 업무 E2E를 실제 Compose 스택으로 검증했다. 실제 OpenAI 프로젝트 키로 유료 오케스트레이션도
검증했다. Telegram 자격증명과 공개 HTTPS 배포 환경이 필요한 검증은 완료로 표시하지 않는다. 이 보고서는
"구현됨"과 "실환경에서 검증됨"을 구분한다.

## 1. 보존한 기존 경계

- V0.4 Orchestrator의 업무 순서와 PASS/REWORK 제어권 유지
- `OpenAIAgentsRuntime` Adapter와 `AgentRegistry` 사용 방식 유지
- API route와 Task/TaskRun/Approval/AuditEvent/Memory/Decision/KnowledgeItem schema 유지
- Alembic head `12738dc9272a` 유지, 신규 migration 없음
- Research/Strategy 병렬 실행, Chief 취합, Reviewer 재작업 흐름 유지
- Hermes 및 Workflow V2 미도입

## 2. 구현한 운영화 항목

### 환경·비밀값 보안

- `TELEGRAM_ENABLED` 명시적 활성화 플래그 추가
- Telegram이 활성화될 때 token, webhook secret, numeric chat ID를 모두 강제
- production에서 다음 조건을 fail-fast로 강제:
  - API 인증 활성화
  - 32자 이상 `APP_API_KEY`
  - PostgreSQL 사용
  - Celery worker 실행 모드
  - migration 기반 schema 관리
  - wildcard CORS 금지
  - Telegram 사용 시 HTTPS 공개 URL
- 비밀값은 `.env`/클라우드 secret에만 두고 예제에는 placeholder만 유지
- PostgreSQL 기본 고정 비밀번호 제거
- 회사 맥락의 추가 trace 전송을 피하도록 OpenAI Agents SDK tracing을 기본 비활성화하고 명시적 opt-in 제공
- OpenAI Responses 별도 저장을 기본 비활성화하고 명시적 opt-in 제공
- 검증한 OpenAI Agents SDK 0.22 계열로 dependency 범위를 고정해 배포 시 무검증 major/minor drift 방지
- 업무 요청을 50,000자로 제한하고 기본 브라우저 보안 응답 헤더 적용
- production에서 예제의 `replace-with` API/DB placeholder를 실제 비밀값으로 오인하지 못하도록 거부
- Settings 표현에서 DB/Redis 자격증명과 API/Telegram secret을 숨김
- `.env`에서 읽은 OpenAI key를 OS 환경에 재출력하지 않고 Agents SDK에 직접 설정해 로컬 실제 호출 경로 보장

### PostgreSQL·Redis·Celery·Docker

- API readiness가 DB, Alembic revision, worker 모드의 Redis 연결을 실제 확인
- Celery에 startup broker retry, late acknowledgement, worker-loss reject, prefetch 1, soft/hard time limit 적용
- Redis visibility timeout을 task hard limit보다 길게 고정하고 Celery result 만료를 명시
- Celery 기본 동시 실행 수를 2로 제한해 소형 서버 메모리·API rate·비용 급증 방지
- worker-loss 후 재전달된 업무가 기존 RUNNING TaskRun을 실패 처리하고 새 attempt로 복구하도록 구현
- DB 상태·갱신시각 기반 원자적 task claim으로 동시 전달과 완료 후 재전달의 중복 실행 방지
- Redis queue 전송 실패 시 업무를 QUEUED로 되돌리고 API/동일 Telegram update 재시도를 허용
- Docker 이미지를 non-root 사용자로 실행하고 API Compose healthcheck 추가
- API/worker 종료 유예시간을 분리해 배포·재시작 중 Celery 작업의 정상 종료 기회 확보
- 로컬 Compose의 API/DB/Redis 포트를 loopback에만 바인딩
- PostgreSQL/Redis 영속 volume 및 Redis AOF 적용
- PostgreSQL native ENUM을 migration에서 한 번만 생성·공유하고 모든 테이블 제거 뒤 drop하도록 수정
- CI에 lint, format, test, compile, dependency, Compose config, image build 단계 추가

### Telegram

- webhook secret과 허용 chat ID 검사 유지
- `update_id`가 없는 업무 메시지를 거부해 idempotency key 충돌 방지
- 접수 응답, `/start`, `/help`, `/status`, 완료 결과 분할 회신 경로 유지
- 완료 회신 성공/실패를 AuditEvent에 기록
- 완료 회신의 실패한 4,000자 조각만 지수 지연으로 최대 3회 재시도해 AI 업무 중복 실행 방지
- Telegram HTTP 오류에서 bot token이 예외·로그에 노출되지 않도록 정규화
- httpx/httpcore INFO 로그를 억제해 URL path에 포함되는 Telegram bot token의 성공 요청 로그 노출 방지
- webhook 설정 도구가 bot identity, webhook URL, 최근 Telegram 오류를 확인

### 클라우드/VPS 배포

- Render Blueprint의 API, worker, PostgreSQL, Redis, migration 경로 유지
- Telegram은 기본 비활성화하고 자격증명이 모두 준비된 뒤에만 켜도록 변경
- 단일 VPS용 `deploy/compose.vps.yml` 추가
- Caddy 자동 HTTPS, 외부 비공개 PostgreSQL/Redis, 재시작 정책, health dependency 추가
- 설정/인프라 점검, 유료 OpenAI smoke, 배포 업무 E2E smoke 스크립트 추가
- 배포 smoke의 APP_API_KEY를 명령 인자 대신 임시 환경변수로 받을 수 있어 shell history 노출 방지
- Research prompt와 유료 OpenAI smoke가 직접 출처 URL을 요구하도록 강화
- Research가 웹페이지 내부 지시를 따르지 않고 untrusted reference로만 취급하도록 prompt-injection 경계 명시
- Research/Strategy/Chief/Reviewer 사이 산출물도 untrusted data로 표시해 간접 prompt injection 전파 차단

## 3. 실제로 검증한 항목

| 검증 | 결과 |
|---|---|
| pytest 전체 | 42 passed |
| Ruff lint | 통과 |
| Ruff format check | 통과 |
| Python compileall | 통과 |
| pip dependency check | No broken requirements found |
| Git diff whitespace check | 통과 |
| 민감정보 패턴 검사 | 발견 0건 |
| YAML 구문 파싱 | Compose, VPS Compose, Render, CI 모두 통과 |
| production 안전 설정 테스트 | 약한 키, SQLite, inline, auto schema, wildcard CORS, 불완전 Telegram 거부 확인 |
| migration-managed readiness | Alembic revision 불일치 거부와 head revision 승인 확인 |
| OpenAI SDK Adapter 로컬 호환 | 설치된 `openai-agents 0.22.0`의 Agent/Runner/WebSearchTool signature 확인 |
| 기본 모델 기능 확인 | 공식 OpenAI 문서에서 `gpt-5.6-luna`의 Responses, structured output, web search 지원 확인 |
| mock HTTP E2E | 실제 로컬 서버에서 readiness → task 생성 → 실행 → completed 확인 |
| DB migration 왕복 | 임시 SQLite에서 upgrade → downgrade → upgrade, head 확인 |
| PostgreSQL migration SQL | offline DDL에서 공유 ENUM 1회 생성, 두 테이블 참조, 테이블 제거 후 ENUM drop 순서 확인 |
| Telegram mock E2E | secret/chat 허용, 업무 생성, 완료 회신 호출, audit 기록 확인 |
| Telegram outbound service | Bot API 요청, 4,000자 분할, transient retry, 네트워크 실패 격리, 오류 token 비노출 확인 |
| Celery worker 재전달 복구 | 중단된 RUNNING attempt 실패 처리 후 새 attempt 완료 확인 |
| 동시·완료 후 중복 전달 | 동시 worker 호출은 TaskRun 1개, 완료 후 redelivery는 no-op 확인 |
| Redis dispatch 실패 복구 | API 503, QUEUED 복귀, audit 기록, 동일 Telegram update 재전송과 중복 방지 확인 |
| Docker Desktop/WSL 2 | Docker Desktop 4.88.1, WSL 2.7.3, Engine running 확인 |
| Compose schema와 이미지 build | `docker compose config --quiet`, API/worker/migrate 이미지 build 통과 |
| PostgreSQL/Redis/Celery 통합 | PostgreSQL·Redis healthy, Alembic `12738dc9272a`, Celery `pong` 확인 |
| 실제 Compose mock 업무 E2E | `/ready` → task 생성 → worker 실행 → completed, token total 0 확인 |
| CEO Desk 브라우저 QA | 연결 상태, 업무 결과, 승인함, 회사 맥락, 감사 기록 렌더링 및 콘솔 오류 0건 확인 |
| 실제 OpenAI 네트워크 오케스트레이션 | `gpt-5.6-luna`, Research/Strategy/Chief/Reviewer 실행, 출처 URL·최종 보고서·32,774 tokens 확인 |
| 실제 Reviewer 통제 경계 | 유료 smoke에서 `REWORK` 판정 반환 확인; 추가 비용 재실행은 하지 않음 |
| OpenAI 설정 Compose 재구성 | `Configuration: valid (development, openai)`, API/DB/Redis healthy, Celery `pong`, integration `SUCCESS` 확인 |

기존 로컬 HTTP smoke task ID는 임시 DB의 `8475a314-61ae-4323-9609-4bcce36f7927`였고 정상 완료했다.
실제 Compose/PostgreSQL/Celery smoke task ID는 `38d996f6-8a73-4697-96fd-9c1c7808349a`였고 정상
완료했다. 둘 다 mock 모드이므로 token total은 0이 맞다.

## 4. 외부 환경 때문에 아직 검증하지 못한 항목

| 항목 | 상태 | 완료 조건 |
|---|---|---|
| Telegram 실제 송수신 | 미실행 | bot token/chat ID/HTTPS URL 설정 후 휴대폰 메시지 접수 및 완료 회신 확인 |
| Render 실제 배포 | 미실행 | GitHub/Render 연결 및 비용 승인 후 공개 `/ready`와 worker 로그 확인 |
| VPS 실제 배포 | 미실행 | VPS·도메인 준비 후 HTTPS 인증서, 재시작, 백업/복구 확인 |
| 격리 Python wheel build | sandbox network 차단으로 hatchling build env 다운로드 불가 | 온라인 CI의 wheel build 단계 통과 확인 |
| Phase 1+운영화 Git commit | 미생성 | Codex 환경의 `.git` 쓰기 제한 해제 후 검토·commit; 모든 작업 파일은 보존됨 |

## 5. 다음 실가동 순서

1. Docker 서비스를 새 OpenAI 설정으로 재구성한다.
2. Render 또는 VPS 중 하나를 선택해 HTTPS로 배포한다.
3. Telegram 자격증명을 입력하고 `TELEGRAM_ENABLED=true`로 전환한다.
4. 휴대폰에서 실제 업무를 보내 최종 E2E를 확인한다.
5. 외부 검증이 통과한 뒤에만 Phase 2 Hermes 파일럿을 시작한다.

## 종료 상태

- Phase 0: 완료
- Phase 1: 구현 및 자동 검증 완료
- 운영화 코드·테스트·문서·배포 경로: 완료
- 자격증명 없는 로컬 및 Docker 통합 검증: 완료
- 실제 OpenAI 네트워크 검증: 완료
- 실제 Telegram/클라우드 실검증: 외부 환경 대기
- Phase 1+운영화 별도 Git commit: 미생성, working tree에 보존
- Phase 2 Hermes: 시작하지 않음
