# AI Company OS — 마스터 구현 명세 v0.1

## 1. 제품 목표

대표 1명이 자연어로 업무를 지시하면 AI 조직이 계획, 조사, 전략 수립, 검증, 보고를 수행하고
그 과정의 업무·기억·의사결정·지식·승인을 장기 보존하는 개인용 회사 운영체제를 만든다.
최종 운영 환경은 PC가 꺼져 있어도 동작하는 클라우드이며, Telegram과 웹은 이후 동일 API의
입출력 채널로 연결한다.

## 2. V0 조직과 책임

- **CEO(사용자):** 목표, 제약, 승인 기준을 제공하고 고위험 행동을 승인한다.
- **Chief of Staff:** 업무를 해석하고 Research와 Strategy 산출물을 종합해 최종 보고를 소유한다.
- **Research:** 사실, 출처, 불확실성, 추가 확인 항목을 조사한다.
- **Strategy:** 선택지, 장단점, 우선순위, 실행 계획, 측정 지표를 만든다.
- **Reviewer:** 정확성·완결성·실행 가능성·위험을 검사해 PASS 또는 REWORK를 반환한다.

V0는 예측 가능성을 위해 코드가 `Research + Strategy 병렬 → Chief 종합 → Reviewer → 최대 N회 재작업`
순서를 통제한다. 향후 업무 종류별 동적 handoff를 추가할 수 있다.

## 3. 시스템 경계

```text
Telegram / Web (후속 단계)
          |
      FastAPI API
          |
  Task service + approvals
          |
      Redis queue
          |
     Celery worker
          |
 OpenAI Agents SDK / mock
          |
      PostgreSQL
```

OpenAI 호출은 애플리케이션 DB와 분리한다. PostgreSQL이 회사의 정본(system of record)이고,
모델 제공자의 대화 상태는 실행 편의를 위한 보조 상태로만 취급한다.

## 4. 핵심 데이터

- `tasks`: 대표의 요청, 상태, 우선순위, 최종 결과, 오류
- `task_runs`: 매 실행의 시작/종료, 담당 에이전트, 검토 판정, 원시 산출물
- `memories`: 장기적으로 다시 사용할 선호·사실·운영 맥락
- `decisions`: 선택, 근거, 결정자, 관련 업무
- `knowledge_items`: 조사 결과와 재사용 가능한 지식
- `approvals`: 외부 발송·구매·삭제·배포 등 행동의 승인 대기와 판정

모든 레코드는 UUID와 UTC 시각을 사용한다. V1에서는 조직/사용자 테넌트 키, 감사 이벤트,
벡터 검색, 보존 정책을 추가한다.

## 5. 상태와 실행 규칙

업무 상태는 `queued → running → completed | failed`다. Reviewer가 REWORK를 반환하면 설정된
횟수만큼 Chief가 피드백을 반영한다. 한도를 넘겨도 현재 최선 결과와 검토 내용을 보존한다.

외부에 영향을 주는 도구는 기본적으로 `approval_required`로 분류한다. V0에는 승인 데이터/API만
포함하며 실제 이메일 발송, 결제, 삭제, 프로덕션 배포 도구는 연결하지 않는다.

## 6. 보안 원칙

- API 키와 DB 비밀번호는 환경 변수/클라우드 secret manager에서만 관리한다.
- 인터넷 조사 내용과 사용자 파일은 신뢰하지 않는 입력으로 취급한다.
- 외부 행동은 최소 권한, 명시적 승인, 감사 로그를 거친다.
- API 공개 전에 인증, 사용자별 데이터 격리, rate limit, CORS allowlist를 추가한다.
- 민감정보는 모델 입력 전 분류·마스킹하고 저장 기간을 설정한다.

## 7. API V0

- `GET /health`
- `POST/GET /api/v1/tasks`, `GET /api/v1/tasks/{id}`
- `POST /api/v1/tasks/{id}/run`
- `POST/GET /api/v1/memories`
- `POST/GET /api/v1/decisions`
- `POST/GET /api/v1/knowledge`
- `POST/GET /api/v1/approvals`, `POST /api/v1/approvals/{id}/decide`

## 8. 단계별 출시 계획

### V0 — 실행 가능한 코어 (현재)

API, 영속 데이터, 4개 에이전트 흐름, worker, Docker, mock/실 API 전환, 기본 테스트.

### V0.2 — 운영 안전성 (구현 완료)

Alembic 마이그레이션, idempotency key, 재시도/시간 제한, JSON 로그, 토큰 기록,
API 키 인증, 테넌트 격리와 감사 이벤트를 구현했다. OpenTelemetry와 별도 Dead Letter Queue는
트래픽이 생기는 운영 단계에서 추가한다.

### V0.3 — 대표 인터페이스 (구현 완료, 외부 계정 연결 대기)

Telegram bot webhook, 허용 채팅 검증, 완료 결과 회신과 업무 목록·승인함·감사 이력을 제공하는
CEO Desk 웹 UI를 구현했다.

### V0.4 — 회사 맥락과 승인 연결 (구현 완료)

최근 회사 기억·대표 결정·조사 지식을 tenant별로 구성해 Research, Strategy, Chief of Staff에
자동 전달한다. Research 산출물은 중복 없이 지식으로 축적하고, Chief of Staff가 외부 발송·결제·
삭제·게시·배포 등 실제 영향이 있는 행동을 요청하면 구조화된 승인 요청을 생성해 CEO Desk의
승인함에 자동 등록한다. CEO Desk에서 기억과 결정을 직접 추가할 수 있다.

### V1 — 검색 고도화와 자동화

하이브리드 검색, 기억 승격/만료 정책, 정기 업무, 이벤트 트리거, 승인된 외부 도구 실행,
평가 데이터셋과 회귀 테스트를 도입한다.

### V2 — 24시간 클라우드 운영 (배포 구성 완료, 실제 배포 대기)

Render Blueprint로 API, worker, 관리형 PostgreSQL, Key Value, migration, health check를 구성했다.
실제 계정에서 배포한 뒤 백업/복구, 비용 알림과 production 승격을 확인한다.


## 9. 완료 기준

V0 완료는 API로 업무를 생성·실행하고, mock 모드 테스트가 API 키 없이 통과하며, 실제 키를 넣으면
4개 역할의 산출물과 Reviewer 판정이 DB에 남고, Docker Compose로 API/worker/db/redis가 기동되는
상태다.
