# 위임된 단일 역할 실행

## 목적

`source=delegation` 하위 업무를 기존 전체 V0.5 Workflow로 우회 실행하지 않고, 생성 시 지정한 역할 하나만
정책·승인·예산 경계 안에서 실행한다. 일반 업무의 Chief of Staff → Research/Strategy → Reviewer 흐름은
변경하지 않는다.

## API 순서

1. `POST /api/v1/tasks/{parent_task_id}/delegations`로 위임과 하위 업무를 생성한다.
2. 응답의 `id`를 사용해 `POST /api/v1/delegations/{delegation_id}/run`을 호출한다.
3. `GET /api/v1/delegations/{delegation_id}`로 상태와 사용량을 조회한다.
4. `GET /api/v1/tasks/{child_task_id}`로 결과와 TaskRun을 조회한다.

운영 환경에서는 모든 요청에 `X-API-Key`와 `X-Tenant-ID`를 보낸다. 위임 하위 업무를 일반
`POST /api/v1/tasks/{child_task_id}/run`으로 호출하면 HTTP 409로 차단한다.

## 실행 직전 재검사

- 위임·부모·자식의 tenant, Project, 계층 관계가 동일한지 확인한다.
- 부모 또는 자식에 대기 중인 승인이 있으면 중단한다.
- 저장한 역할, Agent 버전, provider/model, 도구, 권한, 승인 정책을 현재 Registry와 정확히 대조한다.
- 현재 allowlist 밖의 도구·권한·승인 정책은 거부한다.
- 토큰·시간·비용 예약 상한을 다시 검사한다.
- 입력 길이 추정치가 토큰 예산보다 크면 AI를 호출하기 전에 거부한다.
- OpenAI 실행에는 남은 토큰 예산을 최대 출력 토큰으로 전달하고, 실행 후 실제 총 토큰도 다시 검사한다.

회사 기억은 신뢰할 수 없는 참고 데이터로 표시하며, 외부 발행·구매·메시지·법률 행위를 했다고 주장하지
말라는 실행 경계를 프롬프트에 포함한다. 한 실행에서 등록 역할 하나만 호출하며 재귀 위임은 하지 않는다.

## 상태와 원장

상태는 `created → dispatched → running → completed|failed`로 진행한다. `delegations`에는 다음을 남긴다.

- 연결된 `task_run_id`, runtime, provider, model.
- 입력·출력·총 토큰, 실행 시간, 시작·종료 시각.
- 실패 시 비밀값과 전체 프롬프트를 제외한 오류 요약.

TaskRun에는 역할명, 시도 횟수, 토큰, 실행 시간과 정책 식별용 artifact를 기록한다. 단일 역할 실행은 기존
WorkflowRun을 만들지 않는다. dispatch/start/completed/failed/rejected 감사 이벤트도 기록한다.

`cost_budget_usd`는 현재 실행 허용 상한(예약값)이다. OpenAI 청구서의 실제 USD 비용과 연결하지 않았으므로
실제 비용으로 표시하거나 차감하지 않는다.

## 실패와 재시도

Celery 전송 실패 시 위임은 `created`, 자식은 `queued`로 되돌아가므로 안전하게 다시 요청할 수 있다. 한 번
실행이 시작된 위임은 중복 비용을 피하기 위해 같은 API로 재실행하지 않는다. 실패 업무의 명시적 재시도
정책은 실제 비용 원장과 worker 중단 복구 설계를 함께 추가한 뒤 도입한다.

## 데이터베이스

Alembic revision `e6f8a0c2d4b6`가 실행 원장 열과 TaskRun 외래키를 추가한다. 기존 위임 데이터는 보존되지만
옛 정책 스냅샷에는 Agent 버전/provider/model이 없으므로 실행 직전 `policy_drift`로 안전하게 거부된다.

## 검증 범위

로컬 mock 검증은 역할별 결과, 일반 `/run` 우회 차단, tenant 격리, 단일 실행, 정책 drift 거부, Celery
전송 실패 복구, 토큰 초과 실패를 확인하며 OpenAI 비용을 발생시키지 않는다. Render migration, Web/Worker
배포 및 실제 OpenAI 1회 실행은 사용자 승인과 운영 비밀값이 필요한 별도 검증 단계다.
