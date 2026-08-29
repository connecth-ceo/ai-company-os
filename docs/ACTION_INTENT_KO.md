# ActionIntent 승인 대상 불변화

## 목적

기존 `Approval`은 사람이 읽는 action/reason/risk를 기록하지만 승인 대상의 정확한 입력을 고정하지
않았습니다. ActionIntent는 실행 전에 외부 행동 후보를 JSON payload와 SHA-256 hash로 고정합니다.
현재 단계는 제안과 승인 기록만 제공하며 실제 외부 행동은 실행하지 않습니다.

## 데이터 구조

- `action_type`: `external_publish`, `email_send`처럼 등록 예정 행동 종류를 나타내는 snake_case 식별자
- `summary`, `reason`, `risk`: 대표가 승인함에서 판단할 설명
- `payload`: 승인 대상의 구체적이고 JSON-compatible한 입력
- `payload_hash`: 정렬된 canonical JSON의 SHA-256
- `execution_scope`: 현재는 항상 `single_use`
- `expires_at`: 승인 가능 만료시각
- `approval_id`: 자동 생성된 기존 Approval과의 1:1 연결
- `status`: `proposed`, `approved`, `rejected`, `expired`

## API

- `POST /api/v1/action-intents`: ActionIntent와 pending Approval을 함께 생성
- `GET /api/v1/action-intents`: 회사별 목록
- `GET /api/v1/action-intents/{id}`: 회사별 상세
- `POST /api/v1/approvals/{approval_id}/decide`: 기존 승인 API로 함께 승인·거절

ActionIntent 자체의 실행 API는 없습니다. 승인 상태가 `approved`가 되어도 외부 시스템 호출은 발생하지
않습니다. 별도 ExecutionAttempt API는 불변 원장 준비와 단일사용 claim만 기록합니다.

## 생성 예시

```json
{
  "action_type": "external_publish",
  "summary": "검토된 공지 초안 게시 승인",
  "reason": "외부 채널 게시 전 대표 승인 필요",
  "risk": "high",
  "payload": {
    "channel": "company_blog",
    "draft_id": "draft-2026-001",
    "audience": "customers"
  },
  "expires_in_minutes": 60,
  "idempotency_key": "publish-draft-2026-001"
}
```

## 무결성·보안 규칙

1. payload는 최대 20,000 UTF-8 bytes, 8단계 중첩, list 200개로 제한합니다.
2. token, secret, password, API key, credential 등 비밀값 형태의 필드 이름을 거부합니다.
3. 같은 회사의 idempotency key 재요청은 같은 내용이면 기존 기록을 반환하고 다른 내용이면 409로
   차단합니다.
4. 승인 직전에 payload hash를 다시 계산합니다. 불일치하면 승인과 상태 변경을 모두 취소합니다.
5. 만료 후 승인은 fail-closed로 거부하고 ActionIntent를 `expired`, Approval을 `rejected`로 기록합니다.
6. 다른 회사의 Task, Approval, ActionIntent는 조회하거나 연결할 수 없습니다.

## 의도적으로 남긴 경계

- `approved`는 실행 허가 기록일 뿐 실제 실행 성공이 아닙니다.
- ExecutionAttempt claim 시 `consumed` 전이가 추가됐지만 외부 API 호출이나 성공 결과는 아닙니다.
- 외부 도구 자격증명은 payload에 저장하지 않습니다.
- ExecutionAttempt 원장, payload hash 재확인, 1회성 consume 원자성, timeout, idempotency를 구현했습니다.
  실제 connector 호출과 결과 전이가 완성되기 전에는 쓰기 도구를 catalog에 추가하지 않습니다.

## 배포 후 확인

`SMOKE_ACTION_INTENT.bat`은 운영에 하나의 테스트 제안을 만들고 같은 payload hash를 확인한 뒤 해당
승인을 거절하여 닫습니다. OpenAI나 Telegram을 호출하지 않습니다.
