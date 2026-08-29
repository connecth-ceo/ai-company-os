# 대표 주의 후속조치 폐루프 구현 완료 보고서

작성일: 2026-08-29

## 완료 범위

- 현재 주의 지문과 요청 해시를 검증하는 후속조치 생성 API
- 주의 신호별 queued Task와 담당자·기한 Commitment 원자적 생성
- `attention_follow_ups` append-only 연결 원장
- 프로젝트·결정·원본 주의 ID·지문 연결 보존
- 위험 수준별 기본 Task 우선순위와 마감 정책
- 요청 멱등성, 동일 신호 중복 계획 차단, 테넌트 격리
- 후속조치 생성 시 원본 지문 확인 기록
- Task/Commitment 상태로 `planned`, `in_progress`, `completed`, `cancelled`, `failed` 계산
- 신호 지문 변경 후 재등장과 기존 후속조치 연결 표시
- CEO Desk **후속조치 생성** 버튼 및 상태 표시

## 안전 경계

후속조치 생성은 내부 데이터만 변경합니다. Task는 반드시 `queued`로 생성하고 TaskRun을 만들거나 worker에
전달하지 않습니다. AI 호출, 결제, 게시, 이메일, 삭제, 배포 등 외부 행동도 실행하지 않습니다. 실제 Task
실행은 기존 실행 API와 승인·비용·역할 가드레일을 별도로 통과해야 합니다.

확인한 지문과 현재 지문이 다르면 409를 반환합니다. Task와 Commitment 중 하나라도 만들지 못하면 전체
트랜잭션을 롤백합니다. 결정 후속 약속 생성으로 결정 거버넌스 지문이 바뀌는 경우 새 신호를 숨기지 않고
다시 미확인으로 노출합니다.

## 데이터베이스

- Alembic revision: `d2f4a6b8c0e2`
- 이전 revision: `a7c9e1f3b5d7`
- 신규 테이블: `attention_follow_ups`
- 신호 중복 방지: `(tenant_id, attention_id, fingerprint)` unique
- 요청 중복 방지: `(tenant_id, idempotency_key)` unique
- Task와 Commitment는 각 follow-up에 1:1 연결

## API

- `POST /api/v1/attention/{attention_id}/follow-ups`
- `GET /api/v1/attention/follow-ups`
- `GET /api/v1/attention?include_acknowledged=true` 응답에 후속조치 ID와 계산 상태 포함

## 검증 기준

- Task와 Commitment가 함께 생성되며 TaskRun은 0건
- 수준별 기본 마감과 우선순위
- 멱등 재요청, 다른 요청의 키 충돌, 동일 신호 중복 계획 거절
- 다른 회사에서 신호·후속조치 접근 불가
- Commitment 완료 상태가 follow-up 완료로 반영
- 결정 연결 보존 및 지문 변경 후 재확인
- 전체 마이그레이션, 회귀 테스트, Ruff, JavaScript 문법 검사
