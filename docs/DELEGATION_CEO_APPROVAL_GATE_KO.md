# 위임 실행 CEO 승인 게이트

작성일: 2026-08-28

## 목적

기존 V0.5 Control Plane과 AgentRuntime/Registry 경계를 유지하면서 민감 역할 또는 고비용 AI 위임을
CEO 승인함에 연결한다. 승인은 위임 생성과 OpenAI 실행 사이의 필수 조건이며 외부 발송·결제·삭제·배포
권한을 부여하지 않는다.

## 기본 정책

- `DELEGATION_APPROVAL_ROLES=legal_review`
- `DELEGATION_APPROVAL_COST_THRESHOLD_USD=1.0`
- 비용 상한이 기준보다 **큰** 경우 승인이 필요하다.
- 역할 또는 비용 조건 중 하나만 충족해도 pending Approval을 자동 생성한다.
- Approval은 위임 Child Task에 연결되고 Delegation의 `approval_id`에 고정된다.
- pending, rejected, missing, tenant/task 불일치, 정책 drift는 모두 실행을 거부한다.
- approved 상태만 기존 단일 역할 dispatch를 허용한다.

`cost_budget_usd`는 제공자 실청구액이 아니라 실행 허용 예약 상한이다. 이 게이트는 비용 승인 의사를
기록하지만 실제 청구액 원장을 대신하지 않는다.

## API 순서

1. `POST /api/v1/tasks/{parent_id}/delegations`
2. 응답의 `approval_id` 확인
3. `GET /api/v1/approvals`에서 action, reason, risk 확인
4. `POST /api/v1/approvals/{approval_id}/decide`
5. 승인된 경우 `POST /api/v1/delegations/{delegation_id}/run`
6. Delegation, Child TaskRun, AuditEvent 원장 대조

거절된 위임을 다시 실행하려면 기존 승인 판정을 덮어쓰지 않는다. 정책에 맞는 새 위임과 새 승인 요청을
만들어 결정 이력을 보존한다.

## 감사 이벤트

- `approval.requested`
- `approval.approved` 또는 `approval.rejected`
- `delegation.approval_approved` 또는 `delegation.approval_rejected`
- 승인 전 실행 시 `delegation.execution_rejected` (`approval_pending`)
- 승인 후 정상 실행 시 기존 dispatch/start/completed 이벤트

감사 이벤트에는 키, 업무 전체 본문, OpenAI 결과 전문을 넣지 않는다.

## 자동 검증 결과

- 전체 pytest: `78 passed`
- Ruff format/lint: 통과
- 민감 역할의 승인 자동 생성과 승인 전 409 차단: 통과
- 승인 후 단일 역할 실행과 TaskRun 저장: 통과
- 거절 후 실행 차단, 고비용 위임 승인 생성: 통과
- tenant/Task/Approval 연결 및 감사 이벤트: 통과
- SQLite head `f7a9b1c3d5e7` upgrade → downgrade → re-upgrade: 통과
- PostgreSQL offline DDL의 RESTRICT FK와 unique index: 통과

## 아직 외부 환경에서 검증하지 않은 것

- Render PostgreSQL에 `f7a9b1c3d5e7` migration 적용
- Render Web/Worker 동일 commit Live 및 `/ready` 200
- 운영 승인함에서 pending → approved → 실제 OpenAI 위임 1회 실행

마지막 항목은 추가 OpenAI 비용이 발생하므로 별도 사용자 승인 전에는 실행하지 않는다.
