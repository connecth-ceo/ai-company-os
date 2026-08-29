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
- `POST /api/v1/execution-attempts/{id}/dispatch`: 설치된 adapter를 트랜잭션 밖에서 호출하고 결과 종결
- `POST /api/v1/execution-attempts/{id}/complete`: 성공·실패·불확실 결과 종결
- `GET /api/v1/execution-attempts/{id}/receipt`: 원문 없는 불변 실행 증빙 조회
- `POST /api/v1/execution-attempts/recovery/run`: timeout claim dry-run 진단 또는 격리

모든 API는 APP_API_KEY 인증과 테넌트 격리를 적용한다. 요청에는 connector 자격증명이 아니라 connector
식별자, expected payload hash, timeout, idempotency key만 포함한다.

## 현재 안전 경계

- `prepared`와 `claimed` 모두 외부 API 호출을 의미하지 않는다.
- audit event의 `external_call_started`는 현재 항상 `false`다.
- payload와 비밀값을 ExecutionAttempt에 복제하지 않고 ActionIntent payload hash만 보관한다.
- 실제 connector는 아직 catalog에 없고 완료 API도 connector를 호출하지 않는다.
- dispatch endpoint도 운영 adapter registry가 비어 있는 동안에는 원장을 변경하지 않고 fail-closed 한다.
- 성공 완료에는 공급자 참조값과 응답 원문의 SHA-256 해시가 모두 필요하다. 원문, 토큰,
  자격증명은 영수증에 저장하지 않는다.
- 모든 신규 종결은 시도당 하나뿐인 `ExecutionReceipt`와 같은 트랜잭션에 기록된다. 같은
  완료 요청은 동일 영수증으로 멱등 처리하고 다른 증빙 해시로 덮어쓸 수 없다.
- timeout recovery는 기본 비활성이며 활성화해도 자동 재시도하지 않고 `uncertain`으로 격리한다.
- 다음 단계에서 connector gateway가 claim·외부 호출·complete를 하나의 제한된 실행 흐름으로 결합해야 한다.
