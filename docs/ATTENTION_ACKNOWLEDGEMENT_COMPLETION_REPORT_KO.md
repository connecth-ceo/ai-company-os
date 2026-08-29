# 대표 주의 신호 확인 이력 구현 완료 보고서

작성일: 2026-08-29

## 완료 범위

- 계산형 주의 항목의 안정적 SHA-256 신호 지문
- 초 단위 경과값을 제외해 같은 상태에서 지문이 흔들리지 않는 정규화
- 회사별 append-only `attention_acknowledgements` 원장
- 오래된 화면 지문 거절과 요청 멱등성
- `GET /api/v1/attention?include_acknowledged=false` 미확인 필터
- `GET /api/v1/attention/acknowledgements` 확인 이력 조회
- `POST /api/v1/attention/{attention_id}/acknowledgements` 확인 기록
- CEO Desk 확인 버튼, 확인자 표시, 미확인 대표 지표
- 자동 브리핑에서 동일 확인 신호 반복 제외
- 심각도 또는 안정적 근거가 바뀌면 새 지문으로 자동 재등장

## 구조와 안전 경계

확인은 원본 업무를 완료·취소·승인·거절하지 않습니다. 확인 당시의 주의 ID, 지문, 수준, 종류, 원본 ID와
확인자를 별도 원장에 보존하고 감사 이벤트를 남깁니다. 현재 신호 지문과 요청 지문이 다르면 409를 반환해
대표가 바뀐 상태를 다시 보도록 합니다. 모든 조회와 기록은 `tenant_id`로 격리합니다.

데일리 브리핑은 확인되지 않은 항목만 포함하지만 CEO Desk 기본 조회는 확인된 항목도 표시합니다. 즉 반복
알림은 줄이면서도 미해결 원본이 사라진 것처럼 보이지 않게 했습니다.

## 데이터베이스

- Alembic revision: `a7c9e1f3b5d7`
- 이전 revision: `c5e7f9b1d3a5`
- 신규 테이블: `attention_acknowledgements`
- 신호 중복 방지: `(tenant_id, attention_id, fingerprint)` unique
- 요청 중복 방지: `(tenant_id, idempotency_key)` unique

## 검증 기준

- 동일 신호 지문 유지와 한 번만 기록되는 멱등 재요청
- 확인 후 미확인 필터와 자동 브리핑에서 제외
- 위험 단계 상승 후 새 지문으로 재등장
- 다른 회사에서 확인 이력 비공개
- 잘못된 지문 및 재사용된 멱등 키 충돌 거절
- 전체 회귀 테스트, Ruff format/check, Alembic upgrade, JavaScript 문법 검사
