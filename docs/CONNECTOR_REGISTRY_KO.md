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

## 재검사 지점

1. ExecutionAttempt prepare 전에 connector 등록과 action type을 확인한다.
2. claim 전에 같은 정책을 다시 확인한다.
3. complete 전에 같은 정책을 다시 확인한다.
4. 향후 실제 adapter는 추가로 `require_external_execution`을 통과해야 하며, 현재 모든 connector가 이를
   거부한다.

## 공개 API

`GET /api/v1/connector-catalog`은 버전, provider, 목적, action allowlist, 위험, 승인 필요 여부와 실행
가능 상태만 반환한다. 자격증명 값, client 객체, endpoint secret, 프롬프트는 반환하지 않으며 편집 API도
없다.

## SmartStore 확장 기준

상품 이미지 입력부터 썸네일·상세페이지·법률검토·가격·게시·마케팅·리뷰·정산으로 확장할 때 각각을
별도 action type으로 유지한다. 조회는 읽기 전용 도구로, 게시·가격·캠페인·리뷰 답변은 ActionIntent와
ExecutionAttempt를 거치는 쓰기 도구로 구분한다. 실제 adapter가 추가되기 전에는 어떤 슬롯도 실행
가능으로 바꾸지 않는다.
