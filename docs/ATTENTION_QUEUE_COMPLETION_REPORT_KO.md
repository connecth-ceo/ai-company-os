# 대표 주의 큐 완료 보고서

작성일: 2026-08-28

## 구현 완료

- `info/watch/action/decision/critical`의 독립 AttentionLevel
- 지연 약속, 장기 실행, 업무 실패, 승인 적체의 결정론적 탐지 규칙 v1
- 회사별 격리, 심각도·경과시간 정렬, 종류·최소 수준·개수 필터
- 규칙 버전과 근거를 포함하는 읽기 전용 `GET /api/v1/attention`
- CEO Desk 대표 주의 큐와 대표 확인 필요 지표
- Telegram `/briefing` 상위 주의 항목과 권장 확인 행동
- OpenAI 비용 없이 배포 후 확인하는 `SMOKE_ATTENTION_QUEUE.bat`
- 신규 DB 테이블이나 migration 없이 기존 운영 상태를 읽는 additive 기능

## 로컬 검증

- 전체 자동검사: `115 passed`
- 신규 주의 큐·운영 설정·기존 전문 에이전트 집중 검사: `29 passed`
- Ruff 정적검사: 통과
- Python `compileall`: 통과
- 브라우저 JavaScript 문법검사: 통과
- 운영 smoke PowerShell 구문검사: 통과
- `git diff --check`: 통과
- Pytest 캐시 폴더 쓰기 권한 경고 1건은 검사 결과와 애플리케이션 동작에 영향 없음

## 운영 환경에서 확인할 항목

- GitHub main push와 Render Web/Worker 자동 배포
- 운영 CEO Desk 대표 주의 큐 표시
- 운영 테스트 지연 약속·승인 요청의 탐지와 닫힘 후 큐 제거

## 안전 경계

- 탐지와 제안만 수행하며 재시도·승인·외부 행동을 자동 실행하지 않습니다.
- 모든 규칙은 동일 입력에 같은 결과를 내며 LLM을 호출하지 않습니다.
- Task priority를 AttentionLevel로 재사용하지 않습니다.

## 다음 권장 구현 단위

운영 검증 후 **Proactive Briefing Delivery Foundation**을 추가합니다. 먼저 07:00 KST 예약 실행,
동일 브리핑 중복 억제, quiet hours, 전송 성공·실패 기록과 안전한 재전송만 구현합니다. 새 업무 생성이나
외부 도구 실행은 포함하지 않습니다.
