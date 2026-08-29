# Connector Registry 계약

## 목적

다양한 외부 API를 에이전트가 사용하기 전에 connector 이름, 허용 action type, 위험도와 현재 실행 가능
여부를 코드로 고정한다. 임의 문자열 connector나 다른 목적의 connector로 ExecutionAttempt를 준비하지
못하게 하는 fail-closed allowlist다.

## 현재 등록된 계약 슬롯

- `email_gateway`: `email_send`
- `external_publish_gateway`: `external_publish`
- `smartstore_gateway`: 상품 게시, 가격 변경, 캠페인 시작, 리뷰 답변 계약

모든 슬롯은 대표 승인과 ExecutionAttempt 원장을 요구한다. 현재는 계약과 원장 검증만 가능하고
`external_execution_available=false`이므로 네이버·이메일·게시 API를 호출하지 않는다.

각 action type에는 별도의 `v1` payload 계약이 있다. 계약은 Pydantic의 `extra=forbid` 정책으로 알 수
없는 필드를 거부한다. 따라서 승인된 목적과 다른 destination, callback, 공급자 옵션을 실행 직전에
끼워 넣을 수 없다. 검증 오류 응답에는 입력값을 복제하지 않는다.

## 재검사 지점

1. ExecutionAttempt prepare 전에 connector 등록, action type, payload v1 계약을 확인한다.
2. claim 전에 저장된 payload hash와 payload 계약을 다시 확인한다.
3. complete 전에 같은 무결성과 payload 계약을 다시 확인한다.
4. 향후 실제 adapter는 추가로 `require_external_execution`을 통과해야 하며, 현재 모든 connector가 이를
   거부한다.

## 공개 API

`GET /api/v1/connector-catalog`은 버전, provider, 목적, action allowlist, 위험, 승인 필요 여부와 실행
가능 상태만 반환한다. 자격증명 값, client 객체, endpoint secret, 프롬프트는 반환하지 않으며 편집 API도
없다.

`GET /api/v1/connector-catalog/{connector_key}/actions/{action_type}/schema`는 에이전트가 실행 계획을
만들기 전에 읽을 수 있는 JSON Schema를 반환한다. schema ID와 version이 함께 반환되며 connector에
허용되지 않은 action의 schema 조회는 차단된다.

## SmartStore 확장 기준

상품 이미지 입력부터 썸네일·상세페이지·법률검토·가격·게시·마케팅·리뷰·정산으로 확장할 때 각각을
별도 action type으로 유지한다. 조회는 읽기 전용 도구로, 게시·가격·캠페인·리뷰 답변은 ActionIntent와
ExecutionAttempt를 거치는 쓰기 도구로 구분한다. 실제 adapter가 추가되기 전에는 어떤 슬롯도 실행
가능으로 바꾸지 않는다.

상품 게시 v1 계약은 원본 이미지나 HTML을 직접 싣지 않고 승인된 썸네일·상세페이지 asset ID,
법률검토 record ID, 배송정책 ID를 참조한다. 가격·캠페인·리뷰 답변도 각각 독립 계약이므로 한 번의
승인으로 다른 종류의 외부 쓰기를 수행할 수 없다.
