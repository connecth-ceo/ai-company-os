# 공급자 중립 Connector Runtime Port

## 목적

네이버 스마트스토어, 이메일, 광고 등 공급자별 SDK를 핵심 업무·승인 코드에서 분리하는 실행 경계다.
공급자를 바꾸더라도 ActionIntent, Approval, ExecutionAttempt, ExecutionReceipt는 그대로 유지한다.

## 입력 계약

`ConnectorInvocation`은 실행 시도 ID, 테넌트, connector/action 식별자, 승인 payload hash와 canonical
JSON bytes만 전달한다. 생성 시 다음을 다시 검사한다.

- payload SHA-256이 승인 원장과 같은지
- action별 versioned payload contract를 만족하는지
- canonical JSON인지
- 계약 밖 필드(예: API 키)가 섞이지 않았는지

payload bytes는 객체 repr에서 숨겨 우발적인 로그 복제를 줄인다. 자격증명은 이 포트를 통과하지 않고,
향후 공급자 어댑터 내부의 제한된 secret resolver가 담당한다.

## 출력 계약

`ConnectorResult`는 `succeeded`, `failed`, `uncertain` 중 하나와 outcome code만 반환한다. 성공은
공급자 참조값과 응답 원문의 SHA-256 해시 두 개가 의무다. 공급자 응답 원문이나 토큰은 반환하지 않는다.
결과의 execution attempt ID가 요청과 다르면 거부한다.

## Registry

`ConnectorAdapterRegistry`는 connector key 중복과 action 범위를 검사하고, 미등록 adapter는 항상
fail-closed 한다. 현재 운영 registry는 비어 있으므로 외부 API를 호출하지 않는다. 공급자를 선정하면
해당 adapter만 이 포트를 구현하고 catalog 가용성을 켜는 방식으로 추가한다.

## Dispatch 조정기

`POST /api/v1/execution-attempts/{attempt_id}/dispatch`는 이미 claim된 실행만 받으며 아래 세 구간을
분리한다.

1. 읽기 세션에서 consumed intent, deadline, payload hash와 versioned contract를 재검사한다.
2. DB 트랜잭션을 닫은 뒤 adapter를 호출한다.
3. 검증된 결과만 새 쓰기 세션에서 ExecutionAttempt와 ExecutionReceipt로 함께 종결한다.

adapter timeout이나 예외는 공급자 성공·실패를 추측하지 않는다. claim 상태를 유지해 기존 timeout
recovery가 `uncertain`으로 격리하도록 하며 자동 재시도하지 않는다. 완료된 dispatch를 다시 요청하면
adapter를 재호출하지 않고 기존 영수증을 반환한다.
