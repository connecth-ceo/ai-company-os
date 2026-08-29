# ExecutionReceipt 불변 실행 증빙

## 목적

외부 API 실행 결과의 원문이나 공급자 식별값을 저장하지 않고도, 승인된 payload와 실제 결과가
나중에 바뀌지 않았음을 검증하는 공통 영수증이다. 네이버 스마트스토어, 메일, 광고, 결제 등
공급자가 달라도 같은 테넌트 격리·멱등·감사 규칙을 적용한다.

## 기록 규칙

- ExecutionAttempt 하나에는 ExecutionReceipt 하나만 허용한다.
- 성공 결과에는 `provider_reference_hash`와 `response_hash`가 모두 필요하다.
- 실패·불확실 결과는 외부 응답을 받지 못했을 수 있으므로 증빙 해시 없이도 종결할 수 있다.
- 한쪽 해시만 전달하거나 기존 영수증과 다른 해시로 재완료하면 거부한다.
- payload 원문, 공급자 응답 원문, API 키, 토큰은 저장하지 않는다.
- timeout 복구는 재실행하지 않고 `uncertain` 영수증을 남긴다.

## API

`GET /api/v1/execution-attempts/{attempt_id}/receipt`는 현재 테넌트의 영수증만 반환한다. 완료되지
않았거나 다른 테넌트의 실행은 동일하게 404로 숨긴다.

## 공급자 어댑터 계약

향후 어댑터는 공급자 응답을 받은 즉시 표준화된 outcome과 SHA-256 해시 두 개만 완료 API에
전달해야 한다. 원문은 공급자별 제한된 로그 보존 정책에 따르고 AI Company OS 원장에는 복제하지
않는다.
