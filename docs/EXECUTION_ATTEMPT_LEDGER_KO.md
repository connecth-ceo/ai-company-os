# ExecutionAttempt 불변 실행 원장

## 목적

외부 쓰기 도구를 연결하기 전에 승인된 ActionIntent가 정확히 한 번만 실행 경계로 진입하도록 만드는
공통 원장이다. 현재 구현은 원장 준비와 원자적 claim까지만 제공하며 실제 connector나 외부 API를
호출하지 않는다.

## 상태 흐름

1. ActionIntent와 Approval이 모두 승인 상태인지 확인한다.
2. 만료시각과 canonical payload SHA-256을 다시 검사한다.
3. `prepared` ExecutionAttempt를 회사별 idempotency key로 한 번만 만든다.
4. 실행기가 claim할 때 같은 행과 ActionIntent를 잠그고 모든 조건을 다시 검사한다.
5. 성공한 claim은 ExecutionAttempt를 `claimed`, ActionIntent를 `consumed`로 한 트랜잭션에서 바꾼다.

ActionIntent 하나에는 ExecutionAttempt 하나만 허용한다. 실패했거나 불확실한 외부 행동을 같은 승인으로
재시도하지 않고 새 ActionIntent와 승인을 만들게 하는 fail-closed 기준이다.

## API

- `POST /api/v1/action-intents/{id}/execution-attempts`: 준비 원장 생성
- `GET /api/v1/execution-attempts`: 테넌트별 원장 조회
- `POST /api/v1/execution-attempts/{id}/claim`: 실행기의 단일사용 권한 원자적 claim

모든 API는 APP_API_KEY 인증과 테넌트 격리를 적용한다. 요청에는 connector 자격증명이 아니라 connector
식별자, expected payload hash, timeout, idempotency key만 포함한다.

## 현재 안전 경계

- `prepared`와 `claimed` 모두 외부 API 호출을 의미하지 않는다.
- audit event의 `external_call_started`는 현재 항상 `false`다.
- payload와 비밀값을 ExecutionAttempt에 복제하지 않고 ActionIntent payload hash만 보관한다.
- 실제 connector는 아직 catalog에 없고 실행 결과 완료 전이도 열지 않았다.
- 다음 단계에서 connector gateway가 claim과 외부 호출을 결합하고, timeout 뒤 `succeeded`, `failed`,
  `uncertain` 중 하나를 기록해야 한다.
