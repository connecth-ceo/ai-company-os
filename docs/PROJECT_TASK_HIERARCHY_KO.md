# Project / Task Hierarchy Foundation

## 목적

JARVIS형 AI Company OS가 향후 대표의 목표를 프로젝트와 하위 업무로 나눌 수 있도록 최소 영속 기반을
추가한다. 이번 단계는 데이터 관계만 제공하며 기존 V0.5 실행 순서, Agent 선택, Telegram 명령, 승인 정책은
변경하지 않는다.

## 추가된 구조

### Project

- 회사별(`tenant_id`)로 격리된다.
- 제목, 설명, 상태를 저장한다.
- 상태는 `planned`, `active`, `on_hold`, `completed`, `archived` 중 하나다.
- 이번 단계에서는 삭제와 수정 API를 제공하지 않는다.

### Task 관계

- `project_id`: Task가 속한 Project. 선택 항목이다.
- `parent_task_id`: 상위 Task. 선택 항목이다.
- 기존 Task는 두 값이 모두 비어 있는 독립 업무로 계속 동작한다.
- 상·하위 Task는 같은 회사에 속해야 한다.
- 상위 Task가 Project에 속하면 하위 Task도 같은 Project를 명시해야 한다.
- 데이터베이스가 자기 자신을 상위 Task로 지정하는 관계를 차단한다.

## API

### Project 생성

```http
POST /api/v1/projects
Content-Type: application/json

{
  "title": "2026 한국 시장 진입",
  "description": "초기 고객과 반복 가능한 판매 구조를 검증한다.",
  "status": "active"
}
```

### Project 목록과 상세

```http
GET /api/v1/projects
GET /api/v1/projects/{project_id}
```

### Project Task 생성

```http
POST /api/v1/tasks
Content-Type: application/json

{
  "title": "경쟁사 조사",
  "request": "한국 시장의 주요 경쟁사와 가격을 조사해줘.",
  "project_id": "<project-id>"
}
```

### 하위 Task 생성

```http
POST /api/v1/tasks
Content-Type: application/json

{
  "title": "경쟁사 가격 조사",
  "request": "상위 5개 경쟁사의 가격 정책을 정리해줘.",
  "project_id": "<project-id>",
  "parent_task_id": "<parent-task-id>"
}
```

운영 환경에서는 기존과 같이 `X-API-Key`와 `X-Tenant-ID` 헤더가 적용된다.

## 데이터베이스 이전

- Alembic revision: `5f42d0b8a1c3`
- `projects` 테이블을 추가한다.
- 기존 `tasks`에 nullable `project_id`, `parent_task_id`를 추가한다.
- 기존 Task 데이터는 수정하거나 삭제하지 않는다.
- downgrade 시 새 관계와 Project 테이블만 제거하고 기존 Task는 보존한다.

## 현재 의도적으로 하지 않는 것

- JARVIS의 자동 업무 분해.
- AI 직원 간 자동 위임.
- Goal 모델.
- 동적 Workflow 실행.
- Project 수정·삭제 UI.
- Task 관계 변경 API.

후속 개발 단위인 **Workflow Recording Layer**와 **Delegation Guardrails**가 완료됐다. 위임은 기존
Task 관계를 사용하되 Orchestrator가 역할·예산·깊이·개수·순환·회사/프로젝트 경계를 먼저 검사한 뒤
하위 Task를 생성한다. 자세한 계약은 [DELEGATION_GUARDRAILS_KO.md](DELEGATION_GUARDRAILS_KO.md)에 있다.
