# Provenance Review Foundation

## 목적

`observed`는 URL이 산출물에 있었다는 뜻일 뿐 사실 검증이 아니다. 대표가 원문과 산출물을 확인한 뒤
근거를 `verified` 또는 `rejected`로 판정하고, 나중에 판정을 정정하더라도 이전 판단을 잃지 않도록 별도
검토 원장을 둔다.

## 검토 흐름

```text
ProvenanceRecord 조회
  → 화면에 표시된 SHA-256을 expected_content_hash로 제출
  → 서버의 현재 content_hash와 원자적으로 재확인
  → ProvenanceReview 추가
  → 현재 verification_status 갱신
  → provenance.verified 또는 provenance.rejected 감사 이벤트 기록
```

근거 본문, 출처 URI, TaskRun 연결은 검토 API로 바꿀 수 없다. 검토 행에는 판정 전 상태와 검토한 정확한
내용 해시를 보존한다.

## API

- `GET /api/v1/provenance/{record_id}/reviews`: 최신순 검토 이력
- `POST /api/v1/provenance/{record_id}/reviews`: 검증 또는 반려 판정 추가

POST 요청에는 `decision`, `expected_content_hash`, `reviewed_by`, `note`, `idempotency_key`를 사용한다.
반려에는 사유가 필수이며, 이미 완료된 판정을 바꿀 때도 정정 사유가 필요하다.

## 상태와 무결성

- 허용 판정: `verified`, `rejected`
- `expected_content_hash`가 현재 근거 해시와 다르면 `content_hash_mismatch`로 차단
- 동일 테넌트의 idempotency key 재사용은 같은 요청만 동일 응답으로 처리
- 같은 키를 다른 근거나 판정에 쓰면 `idempotency_conflict`로 차단
- 현재와 같은 완료 판정을 새 키로 반복하면 `status_unchanged`로 차단
- `verified ↔ rejected` 정정은 사유가 있을 때만 허용하고 모든 검토 행을 남김

## 테넌트와 감사

근거와 검토 이력은 모두 tenant 범위에서 조회한다. 다른 tenant의 근거 ID로 목록 또는 판정을 요청하면
404를 반환한다. 성공한 판정은 검토 ID, 이전·현재 상태, 내용 해시, 상속 원본 ID를 AuditEvent에 기록한다.

## CEO Desk

근거 카드에서 `검증` 또는 `반려`를 선택한다. 반려와 기존 판정 정정에는 사유 입력을 요구한다. 화면은
검토 완료 후 원장을 다시 읽어 최신 상태 배지를 표시한다.

## 운영 확인

`SMOKE_PROVENANCE_REVIEW.bat`은 클립보드의 `APP_API_KEY`를 메모리에서만 사용해 readiness, OpenAPI 계약,
기존 검토 이력을 읽는다. 판정을 생성하거나 OpenAI 업무를 실행하지 않는다.
