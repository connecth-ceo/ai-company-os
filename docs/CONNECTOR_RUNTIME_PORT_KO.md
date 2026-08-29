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
