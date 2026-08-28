# Workflow Recording Layer

## 목적

기존 V0.5 실행 순서를 변경하지 않고, 각 업무 실행이 어떤 워크플로 정의와 실행계획을 사용했는지
재현 가능한 데이터로 기록한다. 이번 계층은 동적 워크플로 엔진이나 AI 직원 간 자유 위임이 아니다.

## 버전 있는 기본 템플릿

| 키 | 버전 | 기존 동작 |
|---|---|---|
| `v0_5_fixed_orchestration` | `1.0.0` | Research + Strategy → Chief → Reviewer |
| `v0_5_marketing_extension` | `1.0.0` | 기본 흐름에 명시적 Marketing 단계 추가 |
| `v0_5_legal_review_extension` | `1.0.0` | 기본 흐름에 명시적 Legal Risk Review 단계 추가 |

템플릿은 코드 기반 카탈로그가 source of truth다. 운영자가 DB에서 프롬프트나 실행 순서를 자유롭게
편집하는 기능은 제공하지 않는다. 정의의 canonical JSON에는 SHA-256 checksum을 저장한다.

## 데이터 모델

### WorkflowDefinition

- `workflow_key`, `version` 조합은 유일하다.
- 이름, 설명, 단계와 병렬 그룹을 JSON 정의로 보존한다.
- checksum과 활성 상태를 기록한다.
- 기존 버전은 수정하지 않고 새 버전을 추가하는 방식으로 확장한다.

### WorkflowRun

- 회사, Task, TaskRun, WorkflowDefinition을 연결한다.
- 실행 시작 시 정의 전체를 `definition_snapshot`으로 복사한다.
- 선택된 전문 흐름, 단계, Reviewer 재작업 한도, 모델 정책을 `execution_plan`에 고정한다.
- 완료 시 판정, 재작업 횟수, 토큰, 완료 단계를 `result_summary`에 기록한다.
- 실패와 worker 재전달 복구도 상태·오류·종료 시각으로 남긴다.

기존 `TaskRun.artifacts`는 결과 산출물 저장소로 계속 사용한다. WorkflowRun은 그 산출물을 중복 저장하지
않고 실행 정의와 계획의 provenance를 담당한다.

## API

```http
GET /api/v1/workflow-definitions
GET /api/v1/workflow-runs/{workflow_run_id}
GET /api/v1/tasks/{task_id}
```

Task 상세 응답의 각 `runs[]`에는 선택적인 `workflow_run`이 포함된다. 마이그레이션 이전 TaskRun에는
WorkflowRun이 없어도 정상적으로 조회되므로 기존 데이터와 하위 호환된다. 모든 WorkflowRun 상세 조회는
기존 `X-API-Key` 인증과 `X-Tenant-ID` 격리를 적용한다.

## 데이터베이스 이전

- Alembic revision: `8c2e4f6a9b10`
- `workflow_definitions`, `workflow_runs` 테이블을 추가한다.
- 세 가지 V0.5 정의를 migration에서 등록한다.
- 기존 Task와 TaskRun은 수정하거나 삭제하지 않는다.
- downgrade는 새 기록 테이블만 제거한다.

## 보존된 경계

- 기존 Research/Strategy 병렬 실행과 Chief/Reviewer 순서.
- Marketing·Legal의 명시적 명령 선택.
- Reviewer PASS/REWORK와 제한된 재작업.
- Task 원자적 claim, Celery retry/recovery, 승인, Telegram 회신.
- Phase 1 `AgentRuntime`, `AgentDefinition`, `Registry` 경계.

## 의도적으로 하지 않는 것

- 사용자 정의 동적 DAG/DSL 실행.
- DB에서 실행 중인 정의 수정.
- 자동 Task 분해와 Agent 간 자유 위임.
- Tool 실행과 승인 자동 연결.
- 기존 WorkflowRun이 없는 과거 TaskRun의 추정 backfill.

## 검증 결과

실제로 검증한 항목:

- 전체 자동검사 `64 passed`.
- Ruff lint·format, Python compile, dependency 검사 통과.
- 기본·Marketing·Legal 선택이 각각 올바른 버전 템플릿으로 기록됨.
- 성공·실패·감사 이벤트와 tenant 격리 검증.
- WorkflowRun이 없는 기존 TaskRun의 조회 호환성 검증.
- 임시 SQLite에서 `5f42d0b8a1c3 → 8c2e4f6a9b10 → 5f42d0b8a1c3 → head`
  왕복 및 기존 Task 보존 검증.
- PostgreSQL offline DDL에서 두 테이블, 세 정의 seed, FK 생성 검증.

배포 환경에서 추가로 확인할 항목:

- Render PostgreSQL에 revision `8c2e4f6a9b10` 적용.
- 배포 후 mock 또는 승인된 실제 Task 1회의 WorkflowRun 조회.
- Web/worker 새 이미지와 Telegram 기존 명령 회귀.

다음 개발 단위는 이 기록 계층을 기반으로 Subtask 위임의 깊이·개수·순환·tenant/project 경계를
결정론적으로 제한하는 **Delegation Guardrails**다.
