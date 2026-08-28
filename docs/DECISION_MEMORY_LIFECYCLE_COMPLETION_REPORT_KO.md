# 대표 결정 메모리 수명주기 완료 보고서

작성일: 2026-08-28

## 구현 완료

- 기존 Decision에 상태, 적용 범위, 적용 대상, 효력·만료·검토 시각, 대체 결정 연결 추가
- proposed → active/revoked, active → expired/revoked의 제한된 상태 전환
- 활성 결정을 새 활성 결정으로 원자적으로 대체하고 이전 기록을 superseded로 보존
- 회사·Project·Task·부서 범위 검증과 회사별 데이터 격리
- 현재 효력이 있으면서 실행 중인 회사·Project·Task 범위와 일치하는 active 결정만 후속 AI 업무의 회사
  맥락에 포함
- 상태·범위·현재 효력 필터, 상세 조회, 상태 전환 API
- 생성·활성화·철회·만료·대체 AuditEvent
- 기존 V0.4 결정 생성 형식의 하위 호환
- CEO Desk에서 제안/확정 선택, 제안 확정, 활성 결정 철회, 기존 결정 대체
- 배포 후 OpenAI 비용 없이 확인하는 SMOKE_DECISION_MEMORY.bat
- 기존 기록을 보존하며 기본값을 채우는 Alembic revision c9d1e3f5a7b9

## 실제 검증 완료

- Ruff 전체 정적검사 통과
- 전체 자동검사 98 passed
- 새 결정 수명주기 전용 자동검사 11 passed
- JavaScript 구문 검사 통과
- 제안·철회·미래 효력 결정이 AI 맥락에서 제외되는 동작 검증
- 활성화한 결정이 AI 맥락에 포함되는 동작 검증
- 대체 후 이전 결정은 superseded, 새 결정만 effective 목록에 남는 동작 검증
- Project 결정의 일치 업무 포함·무관 업무 제외와 Task 결정의 대상 업무 포함 검증
- 종료 상태 재활성화, 잘못된 초기 상태, 잘못된 만료시각, 범위 불일치 차단 검증
- 다른 회사의 결정·Project 범위 격리 검증
- Alembic 전체 업그레이드, 신규 마이그레이션 다운그레이드, 재업그레이드 통과
- Alembic 모델/스키마 차이 검사 통과
- PostgreSQL dialect용 마이그레이션 SQL 생성 통과
- 이전 스키마에 저장한 기존 결정이 active/company 기본값과 원래 내용·시각을 유지한 채 업그레이드되는
  실제 데이터 보존 검사 통과

## 이번 단계에서 실행하지 않은 것

- OpenAI 호출과 유료 AI 업무
- GitHub main push
- Render 자동 배포
- 운영 PostgreSQL 마이그레이션
- 운영 데이터에 [SMOKE] 결정 생성

## 배포 후 확인할 항목

1. 로컬 커밋을 GitHub main에 push하는 별도 승인을 받습니다.
2. Render의 ai-company-os와 ai-company-worker가 같은 새 커밋으로 Live인지 확인합니다.
3. /ready 응답의 database_schema가 c9d1e3f5a7b9인지 확인합니다.
4. CEO Desk에서 결정 상태가 표시되는지 확인합니다.
5. 운영 테스트 데이터 생성 승인을 받은 뒤 SMOKE_DECISION_MEMORY.bat을 실행합니다.

## 아직 남은 설계 범위

- 만료 결정 상태를 주기적으로 정리하는 스케줄러
- 자연어 보고서에서 대표 결정을 자동 추출하는 기능
- Decision과 다음 단계 Commitment의 명시적 연결
- 부서 식별자의 별도 마스터 데이터 관리

다음 권장 구현 단위는 대표 약속·후속조치·마감일을 추적하는 Commitment 기반입니다.
