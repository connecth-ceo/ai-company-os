# 위임 실행 실패·Worker 중단 복구

작성일: 2026-08-28

## 목적

Worker 또는 네트워크 중단 뒤 `dispatched`나 `running`에 남은 위임을 안전하게 판별한다. 제공자 요청이
이미 시작됐을 가능성이 있는 실행은 자동 재시도하지 않아 OpenAI 비용과 외부 효과의 중복을 막는다.

## 복구 정책

### 실행 시작 전 정체

`dispatched` 상태가 `DELEGATION_DISPATCH_STALE_SECONDS`(기본 300초)를 넘었고 TaskRun이 없으면:

- Delegation을 `created`로 되돌린다.
- Child Task를 `queued`로 되돌린다.
- `delegation.recovered_before_start` 감사 이벤트를 기록한다.
- 운영자가 원인을 확인한 뒤 기존 승인 상태를 유지한 채 다시 dispatch할 수 있다.

### 실행 시작 후 정체

`running` 상태가 해당 위임의 `timeout_seconds`와
`DELEGATION_RECOVERY_GRACE_SECONDS`(기본 120초)를 모두 넘으면:

- Delegation, Child Task, 실행 중 TaskRun을 `failed`로 격리한다.
- `delegation.stale_execution_quarantined` 감사 이벤트를 기록한다.
- 자동 재시도는 하지 않는다.
- 새 실행이 필요하면 결과·제공자 로그·비용을 사람이 확인한 뒤 새 위임과 새 승인을 만든다.

## 사용 방법

API는 `POST /api/v1/delegations/recover-stale`이다. 요청 본문의 기본값은 다음과 같다.

```json
{"dry_run": true, "limit": 100}
```

항상 dry-run 결과를 먼저 확인한다. 실제 적용은 같은 요청에 `"dry_run": false`를 명시해야 한다.
Windows에서는 `RECOVER_STALE_DELEGATIONS.bat`를 실행하면 먼저 읽기 전용 검사를 수행하고, 대상이 있을
때만 `RECOVER` 확인 문구를 요구한다. APP_API_KEY는 clipboard에서 메모리로만 읽고 종료 시 제거한다.

## 보안과 경계

- 현재 tenant의 위임만 검색한다.
- 완료·실패·created 상태는 변경하지 않는다.
- dry-run은 DB 상태와 감사 원장을 변경하지 않는다.
- 실행 중이었던 작업은 안전하다고 추측해 재실행하지 않는다.
- API 키, 업무 본문, 결과 본문은 복구 감사 이벤트에 기록하지 않는다.

## 자동 검증

- stale dispatch dry-run 무변경 확인
- 실행 전 정체의 queued/created 복구 및 멱등성 확인
- stale running의 Delegation/Task/TaskRun 실패 격리 확인
- 격리된 위임의 재실행 차단 확인
- tenant 격리 확인
- 실제 OpenAI 호출 없이 전체 회귀검사 수행
