# AI 비용 원장과 월 예산 통제

## 목적

AI Company OS는 위임 업무를 실행하기 전에 최대 예상 비용을 예약하고, 실행이 끝나면 실제 토큰 사용량을
기준으로 추정 비용을 원장에 기록합니다. 기존 `cost_budget_usd`는 대표가 해당 위임에 허용한 상한으로 계속
유지되며, `OPENAI_MONTHLY_BUDGET_USD`는 회사 전체 월간 안전 한도입니다.

## 현재 가격 기준

- 모델: `gpt-5.6-luna`
- 가격표 버전: `openai-2026-08-28`
- 입력: 100만 토큰당 USD 0.20
- 캐시 입력: 100만 토큰당 USD 0.02
- 출력: 100만 토큰당 USD 1.20
- 공식 출처: <https://developers.openai.com/api/docs/models/gpt-5.6-luna>

현재 런타임 원장은 캐시 입력 토큰을 별도로 받지 못하므로 모든 입력을 일반 입력 단가로 계산합니다. 따라서
캐시가 적용된 실행의 추정액은 실제 청구액보다 높을 수 있습니다. 입력 토큰이 272,000개를 넘는 요청은 공식
장문 컨텍스트 배율을 반영합니다. 가격을 알 수 없는 모델은 비용 통제를 우회하지 않고 실행을 차단합니다.

## 실행 상태별 처리

1. 위임 생성 시 토큰 상한으로 보수적 최대 비용을 계산합니다.
2. 대표가 정한 위임별 비용 상한보다 크면 생성 단계에서 차단합니다.
3. 실행 직전 월 예산에 최대 비용을 예약합니다. 월 누계와 활성 예약의 합이 한도를 넘으면 OpenAI 호출 전에
   차단합니다.
4. 정상 종료 또는 사용량이 확인된 실패는 토큰 기반 추정액으로 정산합니다.
5. Provider 호출 후 Worker가 중단되어 사용량을 알 수 없으면 예약 상한을 `uncertain_upper_bound`로 격리합니다.
6. Provider 호출 전 큐 전송 실패나 정체 복구는 예약을 전액 반환합니다.

## 금액의 의미

- `estimated_spend_usd`: 토큰 사용량과 저장된 단가로 계산한 추정 누계
- `reserved_usd`: 아직 끝나지 않은 실행을 위해 잡아 둔 최대 금액
- `uncertain_spend_usd`: 호출 가능성은 있으나 토큰 사용량을 확인할 수 없는 보수적 상한
- `provider_billed_cost_usd`: 현재는 항상 비어 있음. OpenAI 청구서와 대조해 확정액을 적재하는 기능을 붙일 때
  사용하기 위한 필드

이 시스템의 금액은 청구서 확정액이 아닙니다. OpenAI 사용량/청구 화면을 회계 기준으로 사용해야 합니다.

## 운영 설정

```text
OPENAI_MONTHLY_BUDGET_USD=10.0
```

Render Blueprint는 Web Service에 위 값을 설정하고 Worker가 동일한 값을 참조합니다. 값을 바꾸려면 Web
Service 환경설정에서 수정한 뒤 Web과 Worker가 모두 새 설정으로 재배포됐는지 확인합니다.

## 조회 방법

- 월 요약: `GET /api/v1/ai-costs/current-month`
- 실행별 원장: `GET /api/v1/ai-costs/ledger?limit=100`
- Windows 초보자용 확인: Render에서 `APP_API_KEY` 값을 복사하고 저장소 루트의
  `CHECK_AI_COST_BUDGET.bat`을 더블클릭합니다. 이 검사는 읽기 전용이며 OpenAI 비용이 발생하지 않습니다.

두 API 모두 기존과 동일하게 `X-API-Key`와 `X-Tenant-ID` 인증을 사용하며 다른 회사의 원장을 반환하지
않습니다.
