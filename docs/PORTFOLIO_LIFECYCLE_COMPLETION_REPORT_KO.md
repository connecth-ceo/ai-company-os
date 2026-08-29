# 목표·프로젝트 수명주기 완료 보고서

작성일: 2026-08-29

## 구현 완료

- Goal과 Project의 명시적 상태 enum 및 허용 전이표
- 종료 상태에서 실행 상태로 되돌리는 요청의 fail-closed 차단
- 열린 프로젝트가 있는 목표의 달성·취소 차단
- 미완료 업무가 있는 프로젝트의 완료·보관 차단
- 종료 목표의 새 Project 연결과 종료 Project의 새 Task·위임 생성 차단
- 상태 전이와 하위 항목 생성을 행 잠금으로 직렬화
- 이전 상태와 대표 메모를 포함하는 AuditEvent
- CEO Desk 카드의 현재 상태별 허용 버튼과 종료 전이 확인
- OpenAI 호출 없이 운영 확인하는 `SMOKE_PORTFOLIO_LIFECYCLE.bat`

## 로컬 검증

- 전체 자동검사 `155 passed`
- Goal/Project·위임·Executive UI 집중검사 `18 passed`
- Ruff lint 및 format 검사 통과
- Python compileall과 dependency 검사 통과
- CEO Desk JavaScript와 운영 smoke PowerShell 구문검사 통과
- SQLite 전체 Alembic upgrade → downgrade base → re-upgrade 통과
- PostgreSQL dialect 전체 offline migration SQL 생성 통과
- 로컬 CEO Desk에서 계획 목표 시작, 목표 연결 프로젝트 생성, 프로젝트 보류·재개 버튼 표시 확인

이번 단위는 기존 DB 열을 사용하므로 Alembic revision을 추가하지 않는다. 기대 revision은 계속
`a3c5e7f9b1d3`이다.

## 안전 경계

- 상태 변경은 AI 업무를 실행하거나 외부 행동을 시작하지 않는다.
- 기존 Goal 없는 Project와 Project 없는 독립 Task는 계속 허용한다.
- 프로젝트 완료 판정은 현재 업무 상태만 검사하며 LLM 판단을 사용하지 않는다.
- 종료 기록을 삭제하지 않고 이력으로 보존한다.

## 배포 후 확인

- GitHub Actions 전체 통과
- Render Web·Worker 동일 커밋 Live
- 운영 CEO Desk 상태 버튼 표시
- 무비용 smoke로 Goal `planned → active → achieved`, Project `active → completed`와 감사 이벤트 확인
