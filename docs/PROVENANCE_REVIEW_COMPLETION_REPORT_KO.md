# Provenance Review Foundation 완료 보고서

작성일: 2026-08-29

## 구현 완료

- 근거 레코드별 추가형 `provenance_reviews` 검토 원장
- `verified`·`rejected` 판정과 판정 전 상태 보존
- 화면에 표시된 SHA-256과 서버의 현재 내용 해시 재확인
- 회사별 idempotency key와 다른 요청 재사용 차단
- 반려와 완료 판정 정정 시 사유 강제
- 최신 현재 상태와 전체 판정 이력 동시 보존
- 성공 판정의 AuditEvent 기록
- 테넌트별 검토 생성·목록 API와 다른 테넌트 404
- CEO Desk의 검증·반려 버튼과 상태 재조회
- 무변경·무비용 운영 스모크
- Alembic revision `c5e7f9b1d3a5`

## 안전 의미

- 검토 API는 기존 근거의 출처 URI, 본문 해시, TaskRun 연결을 수정하지 않는다.
- `verified`는 대표가 해당 해시의 근거를 검토했다는 뜻이며 외부 기관의 법적 인증을 의미하지 않는다.
- 판정 정정은 이전 검토를 삭제하지 않고 새 행으로 보존한다.
- 상속된 결정 근거를 자동으로 재판정하지 않는다. 각 근거 레코드는 별도로 검토한다.
- 외부 네트워크 조회와 OpenAI 실행을 추가하지 않는다.

## 로컬 검증

- 전체 자동검사 `164 passed`
- Provenance·CEO Desk 집중검사 `9 passed`
- Ruff lint·format 통과
- Python compile과 dependency 검사 통과
- 브라우저 JavaScript와 PowerShell smoke 구문검사 통과
- 해시 일치·불일치, idempotency 재처리·충돌, tenant 격리 검증
- 검증→반려 정정 이력과 사유 없는 정정 차단 검증
- 감사 이벤트의 이전·현재 상태와 해시 기록 검증
- SQLite 전체 upgrade와 신규 downgrade·re-upgrade 통과
- Alembic autogenerate 차이 없음
- PostgreSQL offline DDL의 RESTRICT FK와 신규 테이블 확인

## 배포 후 확인할 것

- GitHub `main`의 CI 전체 통과
- Render Web·Worker 동일 커밋 Live와 schema `c5e7f9b1d3a5`
- 운영 OpenAPI 검토 경로, CEO Desk 자산, 미인증 401 차단 확인
