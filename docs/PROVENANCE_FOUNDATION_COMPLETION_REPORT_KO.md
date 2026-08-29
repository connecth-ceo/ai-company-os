# Provenance Foundation 완료 보고서

작성일: 2026-08-29

## 구현 완료

- 연구 지식과 대표 결정에 연결되는 `provenance_records` 추가형 원장
- Research 결과의 HTTP(S) 출처 정규화·중복 제거·최대 개수 제한
- Task, TaskRun, KnowledgeItem, Decision, 원 ProvenanceRecord 연결
- 연구 내용과 결정 rationale의 SHA-256 변경 탐지값
- 결정 생성 시 연결 업무의 연구 근거 자동 상속
- 테넌트별 읽기 전용 목록·상세 API와 제한된 필터
- CEO Desk의 출처 링크·검증 상태·축약 해시 표시
- 데이터 변경과 AI 호출이 없는 운영 스모크 스크립트

## 안전 의미

- `observed`는 산출물에서 URL을 발견했다는 의미이며 사실 검증 완료가 아니다.
- URL 없는 AI 산출물과 수동 결정은 `unverified`로 명시한다.
- 외부 쓰기 API가 없고 기존 데이터의 자동 backfill도 수행하지 않는다.
- 결정의 상속 레코드는 원 연구 레코드 ID를 보존한다.

## 검증 기준

- 전체 자동검사 `161 passed`
- Ruff lint와 format 검사 통과
- URL 정규화·중복 제거
- Research 완료 시 자동 기록
- Decision의 연구 근거 상속
- URL 없는 수동 결정의 미검증 기록
- 테넌트 간 목록 비노출과 상세 404
- Alembic `a3c5e7f9b1d3 → b4d6f8a0c2e4 → a3c5e7f9b1d3 → b4d6f8a0c2e4` 왕복
- Python compile, dependency, JavaScript, PowerShell 구문검사
- Render Web·Worker 동일 커밋 배포와 운영 읽기 API 확인

GitHub `main` 커밋 `742f6cc`와 Render Web·Worker에 배포했고, 운영 `/ready`의 schema
`b4d6f8a0c2e4`, OpenAPI의 목록·상세 경로, 미인증 401 차단을 확인했다.
