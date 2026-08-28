# AI 비용 통제 단계 완료 보고서

작성일: 2026-08-28

## 구현 완료

- `gpt-5.6-luna` 공식 단가를 버전 있는 가격표로 고정
- 알 수 없는 Provider/모델 또는 가격표 버전 불일치 시 실행 전 차단
- 토큰 예산을 기준으로 위임별 보수적 최대 비용 계산
- 대표가 지정한 `cost_budget_usd`보다 최대 예상 비용이 크면 생성 단계에서 차단
- 월 예산 장부에 실행 전 비용 예약 후 동시 실행의 총 예약액까지 반영
- 정상 완료와 사용량이 확인된 실패를 실행별 비용 원장에 기록
- Provider 호출 후 사용량을 확인할 수 없는 장애는 예약 상한을 불확실 비용으로 격리
- 큐 전송 실패, 실행 전 검증 실패, 실행 전 정체 복구 시 예약 반환
- 회사별 월 비용 요약 및 실행 원장 조회 API
- Render Web/Worker에 동일한 `OPENAI_MONTHLY_BUDGET_USD` 전달
- 비용 없이 조회하는 Windows용 `CHECK_AI_COST_BUDGET.bat`

## 실제 검증 완료

- Ruff 정적검사 통과
- Python compile 검사 통과
- 전체 자동검사 `87 passed`
- 가격 계산 검증: 입력 1,554·출력 306 토큰은 USD 0.00067800
- 월 예산 부족 시 Provider 호출 전 차단 검증
- 정상 실행의 예약 반환·원장 기록·월 누계 반영 검증
- 실행 전 정체 복구의 예약 반환 검증
- 실행 중 정체 복구의 불확실 비용 격리 검증
- 회사별 비용 원장 격리 검증
- Alembic 전체 업그레이드 → 신규 마이그레이션 다운그레이드 → 재업그레이드 통과
- Alembic 모델/스키마 차이 검사 통과 (`No new upgrade operations detected`)
- 비용 조회 PowerShell 파일 구문 검사 통과

## 아직 외부 환경에서 확인할 항목

- 현재 Codex 실행 환경에서는 Docker/WSL 서비스 접근이 거부되어 신규 마이그레이션을 실제 PostgreSQL
  컨테이너에서 다시 확인하지 못함
- GitHub push 및 Render 자동 배포 후 Web과 Worker가 새 커밋으로 모두 `Live`인지 확인 필요
- Render PostgreSQL의 마이그레이션 버전이 `b8c0d2e4f6a8`인지 `/ready`로 확인 필요
- 실제 OpenAI 호출을 추가로 실행하지 않았으므로 새 비용 원장에 실제 운영 실행 1건을 기록하는 최종 smoke
  check가 남아 있음
- `provider_billed_cost_usd`는 OpenAI 청구서 연동 전까지 비어 있으며 현재 값은 토큰 기반 추정치임

## 배포 후 확인 순서

1. GitHub에 새 커밋을 push합니다.
2. Render의 `ai-company-os`와 `ai-company-worker`가 같은 새 커밋으로 `Live`인지 확인합니다.
3. `https://ai-company-os-uydy.onrender.com/ready`가 200이고 schema가 `b8c0d2e4f6a8`인지 확인합니다.
4. Render Web Service에서 `APP_API_KEY`의 값을 복사합니다.
5. 저장소 루트의 `CHECK_AI_COST_BUDGET.bat`을 더블클릭합니다. 이 단계는 읽기 전용이고 OpenAI 비용이
   없습니다.
6. 월 예산·잔여액·최근 원장이 정상 출력되면 짧은 실제 위임 1건을 별도 승인 후 실행합니다.
7. 다시 `CHECK_AI_COST_BUDGET.bat`을 실행해 실행별 추정액이 기록됐는지 확인합니다.
