# Delegation Guardrails

## 목적

AI 직원끼리 자유롭게 대화하거나 임의로 업무를 실행하게 하지 않고, 기존 Task 계층과 Phase 1
Agent Registry 경계를 사용해 Orchestrator/API가 검증한 하위업무만 생성한다. 기존 V0.5 실행 흐름,
Reviewer, 승인, Telegram 처리는 변경하지 않는다.

## 위임 계약

```http
POST /api/v1/tasks/{parent_task_id}/delegations
Content-Type: application/json

{
  "title": "경쟁사 가격 조사",
  "request": "상위 5개 경쟁사의 가격과 계약 조건을 정리해줘.",
  "delegated_role": "research",
  "reason": "조사 전문 역할에 한정해 위임",
  "priority": 3,
  "token_budget": 10000,
  "timeout_seconds": 600,
  "cost_budget_usd": 1.0
}
```

성공하면 `delegations` 기록과 `source=delegation`인 하위 Task가 같은 트랜잭션에서 생성된다. 하위
Task는 상위 Task의 `tenant_id`와 `project_id`를 강제로 상속하며 `queued` 상태로 남는다. 생성만으로
Celery 또는 OpenAI 실행을 시작하지 않는다.

```http
GET /api/v1/tasks/{parent_task_id}/delegations
```

운영 환경에서는 기존과 같이 `X-API-Key`와 `X-Tenant-ID` 헤더를 사용한다.

## 결정론적 검사

- 최대 위임 깊이: 기본 3단계.
- 한 상위 Task의 직접 하위 Task 수: 기본 5개.
- 기존 계층의 순환 관계 탐지.
- 모든 조상이 같은 회사와 Project 경계에 있는지 확인.
- `delegated_role`이 운영 Agent Registry에 등록됐는지 확인.
- 토큰·시간·비용 예산이 운영 상한을 넘지 않는지 확인.
- 상위 Task가 실행/배포 중이거나 대표 승인 대기 중이면 위임 차단.
- 같은 상위 Task에 대한 동시 위임은 DB row lock으로 직렬화.

거절은 HTTP `409`로 반환하며 하위 Task를 생성하지 않는다. 성공은 `task.delegated`, 거절은
`task.delegation_rejected` 감사 이벤트로 남긴다. 거절 이벤트에는 비밀값이나 전체 업무 본문을 저장하지
않고 정책 코드와 역할만 기록한다.

## 정책 스냅샷

각 위임은 생성 시점의 다음 값을 불변 JSON으로 보존한다.

- 정책 버전, 깊이·개수 상한과 실제 깊이.
- Agent Registry의 역할 키, 허용 도구, 권한, 승인 정책.
- 요청된 토큰·시간·비용 예산.

이 스냅샷은 향후 정책이나 Registry가 바뀌어도 당시 허용 근거를 재현하기 위한 기록이다.

## 환경 설정

| 변수 | 기본값 | 의미 |
|---|---:|---|
| `DELEGATION_MAX_DEPTH` | `3` | 최대 하위 위임 깊이 |
| `DELEGATION_MAX_CHILDREN` | `5` | 상위 Task당 직접 하위 Task 최대 수 |
| `DELEGATION_MAX_TOKEN_BUDGET` | `50000` | 위임 1건 토큰 예산 상한 |
| `DELEGATION_MAX_TIMEOUT_SECONDS` | `900` | 위임 1건 제한 시간 상한 |
| `DELEGATION_MAX_COST_USD` | `5.0` | 위임 1건 비용 예산 상한(USD) |

이 값은 허용 상한일 뿐 실제 결제나 OpenAI 호출을 자동 승인하지 않는다.

## 데이터베이스 이전

- Alembic revision: `d4e6a8b0c2f4`
- `delegations` 테이블을 추가한다.
- 기존 Project, Task, TaskRun, WorkflowRun 데이터는 수정하거나 삭제하지 않는다.
- 부모·자식 Task와 Project 삭제는 위임 기록이 있으면 `RESTRICT`한다.
- downgrade는 `delegations` 테이블만 제거한다.

## 현재 의도적으로 하지 않는 것

- AI 직원 간 자유 채팅과 무제한 재귀 위임.
- 생성 즉시 자동 실행 또는 OpenAI 비용 발생.
- `delegated_role`에 따른 별도 단일 Agent 실행 라우팅.
- 예산의 실시간 토큰/비용 차감 원장.
- 도구 실행과 대표 승인 자동 연결.

위임 하위 Task를 `/run`으로 실행하면 현재 V0.5 표준 Workflow를 사용한다. 저장된 역할 스냅샷을 실제
단일 Agent 실행에 강제 연결하는 기능은 후속 Orchestrator 실행 단위에서 추가해야 한다.

## 로컬 검증 결과

- 전체 자동검사 `69 passed`.
- Ruff lint·format 통과.
- 성공, 깊이, 직접 하위 수, 미등록 역할, 예산, 승인 대기, tenant 격리, 순환 탐지 검증.
- 성공·거절 감사 이벤트와 하위 Task의 queued 상태 검증.
- 임시 SQLite에서 `8c2e4f6a9b10 → d4e6a8b0c2f4 → 8c2e4f6a9b10 → head`
  왕복 및 기존 Task 보존 검증.
- PostgreSQL offline DDL에서 테이블, FK `RESTRICT`, 비용 정밀도, 인덱스, revision 갱신 검증.

배포 후에는 Render PostgreSQL revision, Web `/ready`, Celery worker 연결과 API 1회 smoke test를
확인해야 한다. smoke test는 하위 Task 생성까지만 수행하며 OpenAI 비용을 발생시키지 않아도 된다.
