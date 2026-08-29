# Provenance Foundation

## 목적

연구 산출물과 대표 결정이 어디서 왔는지 나중에 다시 확인할 수 있도록 최소 증거 원장을 둔다. 이 원장은 범용 데이터 계보 플랫폼이 아니라 현재 운영 흐름에 필요한 연결만 저장한다.

## 자동 기록 흐름

```text
Research Agent 결과
  → KnowledgeItem 저장
  → HTTP(S) URL 추출·정규화
  → Task / TaskRun / KnowledgeItem / SHA-256 연결

대표 결정 생성
  → 연결 Task의 연구 근거 조회
  → 원 ProvenanceRecord ID를 보존해 결정 근거로 상속
  → 결정 rationale의 SHA-256 기록
```

연구 결과에 URL이 없더라도 실행과 내용 해시는 기록한다. URL이 있다는 사실은 `observed`이며 해당 주장의 사실 여부를 검증했다는 의미가 아니다.

## 읽기 API

- `GET /api/v1/provenance`
- `GET /api/v1/provenance/{record_id}`
- 목록 필터: `subject_type`, `knowledge_item_id`, `decision_id`, `task_id`, `verification_status`, `limit`

외부 생성·수정·삭제 API는 제공하지 않는다. 레코드는 Research/Decision 저장 트랜잭션 안에서만 생성된다.

## 저장 필드

- 대상: `knowledge` 또는 `decision`
- 연결: KnowledgeItem, Decision, Task, TaskRun, 상속 원 ProvenanceRecord
- 출처: 정규화된 HTTP(S) URI와 표시 이름
- 산출: 생성 Agent, claim reference, 정확한 내용의 SHA-256
- 상태: `unverified`, `observed`, `verified`, `rejected`
- 시점과 제한된 메타데이터

테넌트와 결정론적 idempotency key가 같으면 같은 근거를 다시 저장하지 않는다.

## 안전 경계

- 출처 URL을 기록할 때 네트워크 요청을 보내지 않는다.
- URL 조각 식별자를 제거하고 중복을 합치며 실행당 최대 20개만 저장한다.
- 다른 테넌트의 레코드는 목록과 상세 조회 모두에서 보이지 않는다.
- SHA-256은 변경 탐지용이며 출처의 진실성이나 법적 증명을 보장하지 않는다.
- 기존 Task, KnowledgeItem, Decision 행은 변경하지 않는 추가형 마이그레이션이다.

## 운영 확인

`SMOKE_PROVENANCE.bat`은 Render의 `APP_API_KEY`를 클립보드에서 메모리로만 읽고 readiness와 읽기 API 계약을 확인한다. 데이터 생성이나 OpenAI 호출은 하지 않는다.
