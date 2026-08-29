# 결정 후속 실행 큐 구현 완료 보고서

## 완료 범위

- Decision과 연결 Commitment를 합산하는 `decision-follow-through-v1` 규칙
- `at_risk`, `untracked`, `in_progress`, `planned`, `complete`, `inactive` 분류
- 테넌트별 읽기 전용 `GET /api/v1/decisions/follow-through` API
- 활성 결정 실행 연결률과 위험·미연결·진행·완료 요약
- CEO Desk 결정 후속 실행 요약과 우선 확인 큐
- 자동 테스트, UI 자산 검사, 무비용 운영 smoke

## 검증 기준

- 기한 초과와 취소만 남은 결정은 `at_risk`
- 연결 약속이 없는 활성 결정은 `untracked`
- 진행 중 약속은 `in_progress`, 실행 대기는 `planned`
- 완료·비활성 결정은 기본 큐에서 제외하지만 전체 요약에는 포함
- tenant 격리, limit 이전 요약 계산, 감사 이벤트 불변

## 운영 영향

- 데이터베이스 migration: 없음
- 기대 schema revision: `c5e7f9b1d3a5`
- 유료 AI 호출: 없음
- 데이터 생성·상태 변경·외부 행동: 없음
