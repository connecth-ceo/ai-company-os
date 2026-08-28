# 약속·후속조치 관리 완료 보고서

작성일: 2026-08-28

## 구현 완료

- Commitment에 약속 내용, 담당 유형·담당자, 마감시각, 상태, 출처·provenance, 관련 Project·Task·Decision,
  reminder policy, 완료시각을 구조화
- open → in_progress/completed/cancelled 및 in_progress → open/completed/cancelled의 제한된 전환
- completed/cancelled 종료 이력 재활성화 차단과 완료시각 일관성 DB 제약
- 상태를 바꾸지 않는 기한 초과 파생 판정과 기한·상태·담당자·연결 대상 필터
- 같은 회사의 실제 Project·Task·Decision만 연결하고 Project/Task 관계 불일치 차단
- manual/decision/task/meeting/external 출처별 source_id 규칙과 bounded metadata 검증
- 모든 생성·상태 변경 AuditEvent
- CEO Desk에서 약속 등록, 관련 대표 결정 연결, 시작·완료·취소, 기한 초과 강조
- Telegram `/briefing`에 지연 건수, 24시간 내 마감, 확인 대상 최대 5건 추가
- OpenAI 비용 없이 배포 후 확인하는 `SMOKE_COMMITMENT_TRACKING.bat`
- Alembic revision `d0e2f4a6b8c1`

## 실제 검증 완료

- Ruff 전체 정적검사 통과
- 전체 자동검사 `108 passed`
- Commitment 전용 자동검사 10개 통과
- Python compileall 통과
- CEO Desk JavaScript 구문 검사 통과
- PowerShell 운영 smoke script 파싱 통과
- SQLite에서 전체 Alembic upgrade, 신규 migration downgrade, re-upgrade 통과
- Alembic 모델/스키마 차이 검사 통과
- PostgreSQL dialect용 전체 migration SQL 생성 통과
- 회사별 데이터 격리, 다른 회사 Decision 연결 차단, Project/Task 불일치 차단 검증
- 기한 초과 목록에서 완료·취소 기록 제외 검증
- 완료시각 기록과 종료 상태 재활성화 차단 검증
- 데일리 브리핑의 지연 약속·후속조치 표시 검증

## 아직 운영 환경에서 확인할 항목

- GitHub main push와 Render Web/Worker 자동 배포
- 운영 PostgreSQL revision `d0e2f4a6b8c1`
- 운영 CEO Desk 약속 영역 표시
- 승인된 운영 테스트 Commitment 두 건의 생성·전환·정리

## 안전 경계

- 이 기능은 약속과 기한을 기록·조회하며 외부 연락, 결제, 삭제, 배포를 자동 실행하지 않습니다.
- 자연어 또는 회의록에서 Commitment를 자동 확정하지 않습니다.
- 모든 구현·자동검사·로컬 migration 검증에서 OpenAI를 호출하지 않았습니다.
- 운영 smoke도 API와 데이터베이스만 사용하도록 구성해 OpenAI 비용이 없습니다.

## 다음 권장 구현 단위

Commitment가 운영 검증되면 결정론적 **Attention Queue**를 추가합니다. 먼저 지연 약속, 장기 실행, 반복 실패,
승인 적체를 규칙으로 탐지하고 `info/watch/action/decision/critical` 수준을 계산합니다. LLM이 임의로 행동을
실행하는 기능은 포함하지 않습니다.
