# 결정 신뢰도 큐 구현 완료 보고서

## 완료 범위

- 결정 생명주기와 결정 근거 검증 상태를 합산하는 `decision-readiness-v1` 규칙 구현
- 테넌트별 읽기 전용 `GET /api/v1/decisions/readiness` API 추가
- `ready`, `watch`, `review`, `blocked`, `closed` 5단계 분류와 우선순위 정렬
- 전체 요약과 기본 예외 큐 분리, 준비·종료 항목의 명시적 포함 옵션 제공
- CEO Desk에 결정 신뢰도 요약과 우선 확인 목록 연결
- 로컬 자동 테스트, JavaScript 구문 검사, 운영 smoke 스크립트 추가

## 검증 기준

- 활성 만료 경과와 반려 근거는 `blocked`
- 제안 상태, 재검토 기한 경과, 미검증 근거는 `review`
- 관찰 근거와 14일 이내 만료·재검토는 `watch`
- 모든 연결 근거가 검증되면 `ready`
- 대체·만료·철회된 결정은 `closed`
- 기본 응답에서 `ready`와 `closed` 제외, 요약에는 포함
- `limit` 적용 전 전체 요약 계산
- 테넌트 격리와 조회 전후 감사 이벤트 불변 확인

## 운영 상태

- 데이터베이스 마이그레이션: 없음
- 기대 스키마 revision: `c5e7f9b1d3a5`
- 유료 AI 호출: 없음
- 자동 결정 변경·외부 행동: 없음

배포 후에는 `SMOKE_DECISION_READINESS.bat`으로 실제 서비스의 `/ready`, OpenAPI, 인증된 큐 응답을 확인한다.
