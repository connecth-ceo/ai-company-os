# ActionIntent Foundation 완료 보고서

작성일: 2026-08-29

## 구현 완료

- ActionIntent와 기존 Approval의 1:1 연결
- canonical JSON SHA-256 payload hash
- 회사별 idempotency key와 다른 payload 재사용 차단
- `single_use` 범위와 5분~30일 만료 제한
- 승인 직전 payload 무결성 재검사
- 승인·거절·만료 상태 연동과 AuditEvent
- secret-like payload key, 크기, 중첩, list 개수 제한
- 회사별 생성·목록·상세 API
- 실행 엔드포인트를 제공하지 않는 proposal-only 안전 경계
- Alembic revision `f2a4b6c8d0e2`
- 무비용 운영 확인 파일 `SMOKE_ACTION_INTENT.bat`

## 로컬에서 실제 확인한 것

- ActionIntent 생성과 pending Approval 자동 연결
- 동일 payload의 안정적인 SHA-256 hash
- 승인 후 `approved` 전이와 `executed=false` 감사 기록
- 외부 실행 endpoint 부재
- idempotency 재사용·충돌 및 tenant 격리
- secret-like payload 사전 거부
- 만료 후 승인 차단과 자동 reject
- DB payload 변조 후 승인 차단 및 pending 상태 보존
- 기존 일반 승인·위임 승인·Attention Queue 회귀검사 통과
- SQLite 전체 migration upgrade → 신규 downgrade → re-upgrade 통과
- PostgreSQL offline DDL의 테이블, RESTRICT FK, unique index, head revision 확인

- 전체 자동검사 `133 passed`
- ActionIntent·API·위임·Attention Queue 집중검사 `27 passed`
- Ruff format/lint 통과
- PowerShell 운영 smoke 구문검사 통과

## 아직 운영 환경에서 확인할 것

- GitHub main 반영과 Render migration `e1f3a5c7d9b2 → f2a4b6c8d0e2`
- Render Web/Worker 동일 commit Live 및 `/ready` head 확인
- 운영 smoke 제안 1건 생성·거절·감사 이벤트 확인

## 아직 구현하지 않은 것

- 승인된 ActionIntent의 실제 외부 실행
- 1회성 consume와 실행 결과 원장
- 외부 API credential vault
- 자동 만료 sweep worker
- 재시도, rate limit, 외부 비용·응답 저장

## 다음 권장 구현 단위

읽기 전용 AI Employee Registry API를 추가해 코드 기반 AgentDefinition의 역할, 버전, 평가 상태,
도구·권한·승인 정책을 CEO Desk에서 안전하게 조회할 수 있게 합니다. 프롬프트와 비밀값은 노출하지 않고
DB 편집 기능도 추가하지 않습니다.
