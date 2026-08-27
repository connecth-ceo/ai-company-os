# JARVIS형 AI Company OS — 현행 시스템 격차 분석

> 분석 기준: 배포 커밋 `b549eb8` (`feat: add briefing marketing and legal workflows`)
>
> 작성일: 2026-08-27 (KST)
>
> 원칙: V0.4 제어면과 Phase 1 `AgentRuntime`/`AgentRegistry` 경계를 보존하며 점진적으로 확장한다. 이 문서는 분석 문서이며 기능 코드 변경을 포함하지 않는다.

## Executive Summary

현재 AI Company OS는 단순 데모가 아니다. FastAPI API, PostgreSQL 영속화, Redis/Celery 비동기 실행, Telegram 입출력, 승인 기록, 감사 로그, 회사 맥락 주입, Reviewer 재작업 루프, Docker/Render 배포 및 CI가 연결된 **운영 가능한 V0.5 제어면**이다. Research·Strategy·Chief·Reviewer의 고정 흐름과 선택형 Marketing·Legal 역할도 실제 배포되어 있다.

그러나 현재 구조는 아직 “CEO의 목표를 프로젝트와 하위 업무로 분해하고, 적절한 AI 직원에게 제한적으로 위임하며, 진행 중 약속과 위험을 능동적으로 추적하는 JARVIS형 Company OS”는 아니다. 핵심 격차는 다음 여섯 가지다.

1. `Task`가 독립 요청 단위일 뿐 Goal → Project → Task → Subtask 계층이 없다.
2. 워크플로우가 코드에 고정되어 있고 계획·위임·의존성·예산을 데이터로 관리하지 않는다.
3. Agent 정의는 선언형이지만 인메모리 코드 등록이며 조직/직원 관리 데이터가 아니다.
4. 승인 기록은 있으나 승인 이후 도구 실행을 통제하는 Policy/Tool Gateway가 없다.
5. Memory·Decision·Knowledge는 있으나 관련성 검색, 출처, 상태, 만료, 대체 관계가 부족하다.
6. 데일리 브리핑은 작동하지만 수동·반응형 요약이며 Commitment/Attention/Proactive Intelligence가 없다.

따라서 전면 재작성이나 Hermes 우선 도입은 권장하지 않는다. 먼저 기존 동작을 전혀 바꾸지 않는 **Project/Task Hierarchy Foundation**을 하나의 작은 개발 단위로 추가하는 것이 가장 안전하다.

---

## A. 현재 시스템 기준선

| 영역 | 현재 구현 | 판정 |
|---|---|---|
| 제어면 | FastAPI, PostgreSQL, Task/TaskRun, Approval, AuditEvent | 보존 |
| 비동기 실행 | Redis + Celery, 재시도, late ack, timeout, 복구 | 보존 |
| 채널 | Web CEO Desk, Telegram webhook/결과 회신 | 보존 |
| AI 팀 | Chief, Research, Strategy, Reviewer + Marketing/Legal 선택 실행 | 확장 |
| 추상화 | AgentDefinition, AgentRegistry, AgentRuntime, ModelPolicy, ToolProvider | 확장 |
| 품질 | Reviewer PASS/REWORK 및 제한된 재작업 | 강화 |
| 회사 맥락 | Memory, Decision, KnowledgeItem 최신순 주입 | 재구성 |
| 운영 | Docker, Render Blueprint, CI, readiness | 보존·강화 |

실제 배포 기준선은 `b549eb8`이며, V0.4 기준선과 롤백 절차 문서가 별도로 존재한다. 현재 API 버전 문자열은 여전히 `0.4.0`이므로 제품 버전과 실행 버전 표시를 나중에 일치시켜야 한다.

## B. 현재 요청 처리 흐름

현재 실제 흐름은 다음과 같다.

```text
CEO Web/Telegram 요청
  → Task 생성 및 감사 기록
  → Celery worker가 원자적으로 실행권 획득
  → 최신 Memory/Decision/Knowledge를 텍스트 맥락으로 구성
  → Research + Strategy 병렬 실행
  → 명시적 명령일 때 Marketing 또는 Legal 추가 실행
  → Chief가 최종 보고 작성
  → Reviewer가 PASS 또는 REWORK 판정
  → 필요 시 제한된 재작성
  → TaskRun/결과/토큰/산출물 저장
  → Knowledge 및 Approval 요청 구체화
  → Telegram 결과 회신
```

이 흐름은 예측 가능하고 검증되어 있으므로 첫 JARVIS 확장에서 유지해야 한다.

## C. 목표 아키텍처 대비 총괄 격차

| 목표 구성요소 | 현재 수준 | 핵심 격차 |
|---|---:|---|
| CEO → JARVIS | 부분 | Chief가 일반 AgentDefinition이며 독립된 executive control layer가 아님 |
| Goal/Project/Task | 낮음 | Task만 존재, 계층·목표·프로젝트 없음 |
| Workflow Orchestrator | 부분 | 실행기는 있으나 고정 Python 순서 |
| AI Employees | 부분 | 역할 정의는 있으나 조직/역량/상태를 DB에서 관리하지 않음 |
| Tool Gateway | 낮음 | OpenAI web search만 런타임 내부에 직접 연결 |
| Review/Critic | 중상 | Reviewer와 재작업 존재, 기준/점수/독립 증거 부족 |
| Approval/Risk | 중간 | 승인 기록은 있으나 정책 평가와 승인 후 실행 없음 |
| Company Brain | 낮음~중간 | 세 테이블은 있으나 검색·수명주기·출처 부족 |
| Commitment Tracking | 없음 | 약속/담당/기한/후속 조치 엔티티 없음 |
| Proactive Intelligence | 없음 | 이벤트 감지·제안 생성·스케줄 실행 없음 |
| Executive Dashboard | 부분 | 업무/승인/기억/감사 화면은 있으나 목표·위험·주의 큐 없음 |
| Provenance | 낮음 | URL이 결과 텍스트나 loose JSON에 섞임 |

## D. Task 중심 아키텍처

### 보유한 기반

- `Task`: tenant, idempotency, 우선순위, 상태, 결과, 오류, 채널 출처를 영속화한다.
- `TaskRun`: 시도 횟수, Agent, Reviewer 판정, 토큰, 시간, 산출물을 기록한다.
- worker가 중복 실행을 막고 실패를 복구한다.
- API·Web·Telegram이 동일 Task 모델을 사용한다.

### 부족한 점

- Goal, Project, parent task, dependency가 없다.
- 담당 Agent, 워크플로우 템플릿, 위험도, 주의도, 기한, 비용 상한이 Task의 구조화 필드가 아니다.
- 상태가 `queued/dispatched/running/completed/failed`뿐이라 waiting/review/approval/cancelled를 표현하지 못한다.
- 사용자 요청·JARVIS 계획·직원 산출물·최종 보고가 독립적인 버전 객체가 아니다.

### 판단

기존 `Task`를 폐기하면 안 된다. nullable 관계와 보조 테이블을 추가해 기존 Task를 루트 Task로 간주하는 방식이 안전하다.

## E. Project와 Goal

현재 Project와 Goal 엔티티 및 API가 없다. 따라서 여러 Task가 같은 사업 목표에 속하는지, 프로젝트가 어떤 성공 기준과 기한을 갖는지, 전체 진행률이 무엇인지 알 수 없다.

권장 모델의 최소 형태:

- Goal: 제목, 설명, 성공 지표, 상태, 목표일, owner.
- Project: Goal 연결(선택), 목적, 상태, 위험도, 시작/종료 예정일.
- Task: Project 연결(선택), parent Task 연결(선택).

Goal은 Project 기반이 검증된 뒤 추가해야 한다. 한 번에 세 계층을 모두 넣는 것은 현재 규모에서 과도하다.

## F. Workflow Orchestrator

`app/agents/orchestrator.py`는 안정적인 실행 오케스트레이터이지만 워크플로우 정의 엔진은 아니다. 순서와 분기가 Python 코드로 고정되어 있다.

향후 분리해야 할 개념:

- WorkflowDefinition: 단계, 역할, 입력/출력 계약, 재시도, 승인 지점.
- WorkflowRun: 실제 실행 상태와 단계 이력.
- ExecutionPlan: 특정 CEO 요청을 어떤 단계로 처리할지에 대한 불변 스냅샷.

첫 단계에서는 기존 고정 흐름을 `v04_research_strategy_review` 템플릿으로 감싸되 실행 코드를 바꾸지 않는 어댑터 방식이 적절하다.

## G. JARVIS / Chief 역할

현재 Chief는 Research·Strategy 결과를 받아 보고서를 합성하는 AI 직원이다. 목표 상태의 JARVIS는 그보다 상위에서 다음을 책임져야 한다.

- 요청 의도와 성공 기준 명확화
- 기존 Goal/Project/Decision과 연결
- 실행 계획 선택
- 위험·비용·승인 필요성 판단
- 진행 상황 요약 및 예외만 CEO에게 승격

Chief 프롬프트를 계속 비대하게 만들면 안 된다. 기존 Chief는 “보고서 통합자”로 보존하고, JARVIS는 정책 기반 애플리케이션 서비스로 먼저 구현해야 한다. 장기적으로도 JARVIS 전체를 하나의 자유행동 LLM Agent로 만들지 않는다.

## H. AI Employee Registry

`AgentDefinition`에는 이미 role, purpose, prompt, output schema, model policy, memory scope, allowed tools, permissions, approval policy, knowledge collections, workflow templates, schedules, version, evaluation status가 있다. 이는 매우 좋은 보존 지점이다.

부족한 필드/기능:

- department, responsibilities, capabilities, cost limit, active/suspended status.
- 정의의 DB 영속화와 버전 이력.
- 관리자 승인 후 활성화하는 lifecycle.
- 역할별 평가 결과와 최근 성능.
- UI에서 조회 가능한 AI Team 조직도.

초기에는 코드 정의를 source of truth로 유지하면서 읽기 전용 Registry API부터 추가하는 편이 안전하다. 곧바로 프롬프트를 DB에서 자유 편집하게 하면 재현성과 보안이 약해진다.

## I. Agent / Model / Tool 분리

Phase 1에서 `AgentRuntime`, `ModelPolicy`, `ToolProvider` 경계를 이미 만들었으므로 방향은 맞다.

- Agent와 Model: 분리되어 있음.
- Runtime과 Agent: 분리되어 있음.
- Tool 허용 목록: 정의에 존재함.
- 실제 Tool 실행: OpenAI runtime 안의 `web_search`에 결합됨.
- KnowledgeRetriever: protocol만 존재하고 실제 구현 없음.

다음 확장은 기존 프로토콜을 폐기하지 말고, Tool Gateway가 `ToolProvider`를 구현하게 해야 한다.

## J. Delegation Guardrails

현재 직원 간 위임은 없다. Orchestrator가 정해진 Agent를 호출한다. 이는 안전하지만 JARVIS 목표에는 부족하다.

필수 통제:

- 최대 위임 깊이와 최대 하위 업무 수.
- 동일 Agent/Task 순환 탐지.
- Task별 토큰/시간/금액 상한.
- 허용된 역할과 도구만 선택.
- 동일 tenant와 project 안에서만 관계 생성.
- 승인 대기 시 실행 정지.
- 모든 위임의 parent/initiator/reason 감사 기록.

자유로운 Agent-to-Agent 채팅보다 Orchestrator가 데이터베이스에 Subtask를 생성하는 mediated delegation을 권장한다.

## K. Reviewer / Critic

현재 Reviewer PASS/REWORK와 제한된 재시도는 보존해야 할 강점이다. 다만 판정은 단일 텍스트 피드백 중심이다.

개선 순서:

1. 역할별 검수 기준을 버전 있는 rubric으로 정의.
2. completeness, evidence, consistency, policy를 구조화 점수로 저장.
3. Reviewer가 사용한 근거와 대상 산출물 버전을 연결.
4. 반복 실패 시 자동 재시도 대신 CEO/운영자에게 승격.

다중 Critic 합의나 debate 구조는 현재 단계에서 과도하다.

## L. Company Brain

현재 Company Brain의 씨앗은 `Memory`, `Decision`, `KnowledgeItem` 및 `build_company_context()`다. 그러나 단순 최신순 8개씩, 총 12,000자 제한으로 붙이는 방식이라 업무 관련성이 낮고 오래된 잘못된 정보가 섞일 수 있다.

권장 논리 구분:

- Operational State: Task/Project/Approval/Commitment의 현재 상태.
- Company Knowledge: 검증된 사실, 정책, 고객/제품 정보.
- Decision Memory: 경영 결정과 적용 범위/상태/대체 관계.
- Agent Working Memory: 특정 실행 중의 임시 맥락.

벡터 DB는 이 구분과 provenance가 먼저 갖춰진 뒤 도입한다.

## M. Structured Decision Memory

현재 Decision은 subject, choice, rationale, decided_by, task_id만 갖는다. 다음 필드가 필요하다.

- status: proposed/active/superseded/expired/revoked.
- scope와 applies_to.
- effective_at, expires_at.
- supersedes_decision_id.
- provenance/evidence 연결.
- review_due_at.

기존 행은 `active` 기본값과 전사 범위로 안전하게 마이그레이션할 수 있다. 다만 Project 기반이 먼저 생기면 적용 범위를 더 정확히 연결할 수 있다.

## N. Commitment Tracking

현재 시스템에는 “누가 언제까지 무엇을 하기로 했는가”를 나타내는 구조가 없다. Task의 상태만으로는 회의 약속, 외부 회신, CEO 후속 조치를 구분할 수 없다.

최소 Commitment 모델:

- statement, owner_type/owner_id, due_at, status.
- source_type/source_id와 provenance.
- related project/task.
- reminder policy, completed_at.

Meeting Intelligence보다 Commitment 엔티티를 먼저 만들어야 회의에서 추출한 결과를 저장할 곳이 생긴다.

## O. Proactive Intelligence

현재 `/briefing`은 요청 시 읽기만 하는 기능이다. 능동성은 아직 없다.

권장 안전 단계:

1. 탐지: 기한 초과, 장기 실행, 반복 실패, 승인 적체를 결정론적으로 찾는다.
2. 제안: 행동 후보를 생성하되 실행하지 않는다.
3. 알림: 중복 억제와 quiet hours를 적용한다.
4. 실행: 승인된 낮은 위험 작업만 Tool Gateway로 실행한다.

처음부터 LLM이 임의로 업무를 만들고 실행하도록 해서는 안 된다.

## P. Attention Levels

현재 priority 1–5는 입력 우선순위일 뿐 CEO가 지금 봐야 할 정도를 뜻하지 않는다. 별도 AttentionLevel을 권장한다.

- `info`: 기록만 필요.
- `watch`: 관찰 필요.
- `action`: 담당자 행동 필요.
- `decision`: CEO 결정 필요.
- `critical`: 즉시 승격.

Attention은 위험도, 기한, 실패, 승인, 비용을 근거로 규칙 엔진이 계산하고, 사람이 조정할 수 있어야 한다. Task priority와 혼합하지 않는다.

## Q. Approval / Risk

현재 Approval은 pending/approved/rejected, action, reason, risk, 결정자를 기록한다. Web에서 승인·거절할 수 있으나 승인은 실제 외부 행동을 실행하지 않는다. 이 제한은 UI에도 명시되어 있어 안전하다.

필요한 확장:

- RiskPolicy: 도구·행동·금액·데이터 민감도별 규칙.
- ApprovalRequest가 대상 ToolCall/ExecutionPlan을 불변 참조.
- 승인 만료, 1회성 승인, 범위 제한.
- 승인 이후 동일 payload만 실행하도록 hash/idempotency 적용.
- 승인자 권한 및 separation of duties.

자연어 `risk` 문자열만으로 자동 실행을 허용하면 안 된다.

## R. Daily Briefing

현재 `/briefing`은 KST 기준 최근 24시간 완료/진행/실패, 승인 대기 수, 최근 업무 5개를 비용 없이 반환하며 실제 Telegram에서 검증됐다.

확장 목표:

- 오늘의 Goal/Project 진행과 주요 변동.
- Attention `decision/critical` 우선 표시.
- 오늘 만료되는 Commitment와 지연 건.
- 승인 대기와 비용/품질 이상.
- 추천 행동 1–3개 및 근거.
- 07:00 KST 예약 전송, 중복 방지, 실패 재전송.

Calendar/Email은 커넥터와 명시적 권한이 준비된 뒤 별도 단계로 연결한다.

## S. Meeting Intelligence

현재 회의 자료 수집, 회의록 파싱, 결정/약속 후보 추출 기능은 없다.

권장 흐름:

```text
회의 원문 수신 → 발언/안건 구조화 → Decision/Commitment 후보 생성
→ 사람 검토 → Company Brain 승격 → 관련 Project/Task 연결
```

자동으로 확정 Decision을 저장하지 말고 후보 상태와 provenance를 먼저 보존해야 한다.

## T. Executive Dashboard

현재 CEO Desk는 다음을 잘 제공한다.

- 새 업무 지시.
- 진행/완료/승인/토큰 지표.
- 최근 업무와 결과.
- 승인함.
- Memory/Decision/Knowledge 요약과 추가.
- 감사 활동.

부족한 화면:

- Goals/Projects 포트폴리오.
- JARVIS Attention Queue.
- AI Team 역할/상태/성능.
- Commitments 및 마감.
- 워크플로우/하위 업무 진행도.
- 출처/증거와 산출물 버전.
- 실제 비용과 예산.

기존 단일 페이지를 즉시 SPA로 재작성하지 말고 API와 데이터 모델이 안정된 뒤 섹션을 추가한다.

## U. Provenance

현재 URL이나 근거는 보고서 문자열, `KnowledgeItem.source`, `TaskRun.artifacts` JSON에 흩어진다. 누가 어떤 주장에 어떤 출처를 사용했는지 질의하기 어렵다.

향후 `Artifact`, `Evidence`, `Citation` 또는 통합 `ProvenanceRecord`가 필요하다. 최소 필드는 source URI, captured_at, content hash, claim/section reference, produced_by agent/run, verification status다.

단, 범용 데이터 계보 플랫폼은 만들지 않는다. 우선 Research 산출물과 Decision 근거만 대상으로 시작한다.

## V. Tool Gateway

현재 Tool 사용은 OpenAI runtime의 `WebSearchTool` 한 가지이며 허용 목록은 AgentDefinition에 있다. 중앙 실행 경로, 정책 평가, 자격 증명 격리, 호출별 감사/비용/재시도가 없다.

Tool Gateway의 책임:

- typed input/output schema 검증.
- Agent/tenant/Task별 권한 확인.
- 위험 정책과 승인 확인.
- secret을 Agent 프롬프트와 분리.
- idempotency, timeout, retry, rate limit.
- 요청/응답 메타데이터와 비용 감사.

첫 concrete tool은 기존 web search를 gateway 뒤로 옮기는 것이 가장 낮은 위험의 검증 대상이다.

## W. 보안·운영·관측성

### 이미 있는 것

- API key 인증과 tenant header 격리.
- Telegram secret/allowed chat 검증.
- secrets를 환경변수로 분리.
- readiness에서 DB schema와 Redis 확인.
- worker timeout/retry/recovery.
- Docker/Render/CI 통합 검증.
- 감사 이벤트.

### 보완할 것

- 사용자/역할 기반 인증과 권한.
- secret rotation 및 외부 secret manager.
- per-tenant rate limit와 비용 상한.
- dead-letter/replay 운영 절차.
- OpenTelemetry/구조화 metric/알림.
- 개인정보 분류·보존·삭제 정책.
- migration dry-run 및 운영 백업 검증 자동화.

## X. 기존 V2 마이그레이션 계획과의 충돌

저장소에서 독립된 “V2 Migration Plan” 문서는 발견되지 않았다. 현재 판단 근거는 `MASTER_IMPLEMENTATION_SPEC.md`, `PHASE_1_ABSTRACTIONS_KO.md`, ADR-0001, V0.4 기준선 및 운영화 완료 보고서다.

### 충돌 없음

- V0.4 제어면 보존.
- Runtime/Model/Tool/Knowledge 교체 경계 유지.
- Hermes 등 외부 runtime의 점진적 pilot.
- Workflow V2를 Phase 1에서 성급히 도입하지 않은 결정.

### 정리해야 할 충돌/모호성

1. 기존 문서의 “V2”는 일부에서 24시간 클라우드 운영, 일부에서 Phase 2 Hermes, 새 지시는 JARVIS형 제품 아키텍처를 뜻한다. 향후 명칭을 `Operational V1`, `JARVIS Architecture`, `Runtime Pilot`처럼 분리해야 한다.
2. `MASTER_IMPLEMENTATION_SPEC.md`는 실제 클라우드 배포 대기라고 적혀 있어 현재 운영 상태와 맞지 않는다.
3. 현재 Chief는 일반 Agent인데 새 목표의 JARVIS는 상위 제어 계층이다. 기존 Chief를 삭제하지 않고 책임을 분리해야 한다.
4. 기존 Registry는 코드 기반 인메모리 설계다. 새 목표의 데이터 기반 Registry로 이동하되 초기에는 코드 정의의 재현성을 유지해야 한다.
5. Commerce/Marketplace 확장은 이번 범위에서 명시적으로 제외한다.

## Y. 보존·리팩터링·신규 개발 분류

### 1. 반드시 보존할 코드

- `app/models.py`의 Task/TaskRun/Approval/AuditEvent 기반.
- `app/services/task_service.py`의 원자적 claim, 실행 기록, 실패 복구, 감사.
- `app/worker.py`의 Celery 실행·재시도 설정.
- `app/agents/contracts.py`의 Runtime/Tool/Knowledge 경계.
- `app/agents/definitions.py`, `registry.py`의 선언형 정의와 검증.
- `app/agents/runtimes/openai_agents.py` 어댑터 경계.
- 기존 Research → Strategy → Chief → Reviewer 동작.
- Telegram 인증/멱등성과 결과 회신.
- Docker/Render/CI/readiness/backup 문서.
- 기존 53개 자동검사와 V0.4 rollback 기준선.

### 2. 점진적으로 리팩터링할 코드

- 고정 orchestrator를 기존 동작을 대표하는 workflow template adapter로 감싼다.
- `build_company_context()`를 최신순 문자열 결합에서 typed retrieval service로 바꾼다.
- OpenAI web search를 Tool Gateway 뒤로 이동한다.
- Approval을 단순 기록에서 immutable action payload와 연결한다.
- `TaskRun.artifacts` loose JSON의 핵심 필드를 typed artifact/provenance로 승격한다.
- CEO Desk를 데이터 모델 안정화 후 섹션별로 확장한다.

### 3. 신규 개발할 것

- Project/Goal/Task hierarchy.
- WorkflowDefinition/WorkflowRun/ExecutionPlan.
- mediated delegation과 guardrails.
- JARVIS executive planning/attention service.
- structured Decision Memory와 Commitment.
- provenance/evidence.
- Tool Gateway와 policy engine.
- proactive detector/scheduler/notification dedupe.
- executive portfolio/attention UI.

### 4. 지금 만들지 말아야 할 것

- 기존 제어면을 Hermes나 다른 framework로 전면 교체.
- 자유로운 무제한 Agent-to-Agent 대화.
- 모든 프롬프트/권한을 즉시 DB 편집 가능하게 하는 관리자 화면.
- 범용 BPMN 엔진.
- 범용 graph database 또는 knowledge graph.
- provenance 이전의 무분별한 vector DB 도입.
- 다중 Critic debate/합의 시스템.
- 무승인 외부 발송·결제·삭제·배포.
- Commerce/Marketplace 기능.

### 5. 과잉설계 위험

- 프레임워크 도입 자체가 목적이 되어 현재 안정 경계를 잃는 것.
- Project/Goal/Workflow/Commitment/Provenance를 한 migration에 모두 넣는 것.
- 작은 팀에 복잡한 RBAC·조직도를 먼저 구축하는 것.
- 동적 워크플로우 DSL을 실제 사용 사례보다 먼저 일반화하는 것.
- 모든 기억을 embedding하고 자동 사실로 승격하는 것.

### 6. 기술 위험

- PostgreSQL enum 상태 확장/롤백의 운영 복잡성.
- parent task 및 dependency cycle.
- tenant 간 관계 참조 누출.
- 승인 후 payload 변조 또는 중복 실행.
- Agent 계획 폭주로 비용·시간 초과.
- 오래되거나 거짓인 기억이 보고서에 주입되는 문제.
- 배포 중 API/worker schema 버전 불일치.
- Render worker와 web 환경변수 불일치.

## Z. 권장 마이그레이션·테스트·롤백 전략

### 7. 권장 마이그레이션 순서

1. **기준선 동결:** 배포 커밋/DB 백업/현재 53개 테스트를 기준선으로 기록.
2. **Project/Task hierarchy:** nullable 관계만 추가하고 기존 실행은 변경하지 않음.
3. **Workflow 기록 계층:** 기존 고정 흐름을 하나의 버전 있는 템플릿/실행 기록으로 감쌈.
4. **위임 통제:** Subtask 생성 API와 depth/count/budget/cycle guardrail 추가.
5. **구조화 기억:** Decision lifecycle, Commitment, provenance를 작은 migration으로 순차 추가.
6. **Tool Gateway/정책:** web search부터 중앙 경로로 이동하고 승인 payload 연결.
7. **JARVIS 계층:** intent/plan/attention을 제안 모드로 도입하고 기존 workflow 선택만 수행.
8. **능동 기능:** 결정론적 detector, 07:00 briefing, 중복 억제 후 제안형 intelligence.
9. **Executive UI:** Projects, Attention, Commitments, AI Team, evidence 화면 추가.
10. **Runtime pilot:** 동일 계약·동일 평가셋으로 Hermes 등 후보를 제한적으로 비교.

각 단계는 독립 배포 가능해야 하며 다음 단계가 이전 단계의 성공을 전제로 한다.

### 8. 테스트 전략

- **회귀:** 기존 53개 테스트와 mock E2E를 모든 단계에서 유지.
- **모델/API:** tenant isolation, 관계 무결성, idempotency, 권한, pagination.
- **상태 기계:** 허용/금지 전이와 동시 실행 경쟁 조건.
- **migration:** PostgreSQL upgrade/downgrade SQL, 실제 disposable DB round trip.
- **workflow contract:** 기존 입력에 기존 Agent 순서와 승인/Reviewer 결과가 유지되는지 golden test.
- **guardrail:** cycle, depth, fan-out, budget, timeout, 승인 미충족 차단.
- **보안:** cross-tenant ID, secret leakage, webhook 위조, payload tampering.
- **복구:** worker 중단/재시작, 중복 메시지, API/worker 버전 차이.
- **AI 품질:** 고정 평가셋으로 evidence completeness, hallucination, Reviewer 재작업률 측정.
- **비용:** 실제 OpenAI 검증은 명시적 비용 승인 시에만 1회씩 수행.

### 9. 롤백 전략

- additive nullable migration을 우선하고 destructive rename/drop은 별도 릴리스로 미룬다.
- 새 기능은 feature flag로 끄면 기존 `v04` workflow로 즉시 돌아가야 한다.
- API와 worker가 한 버전 차이에서도 안전하도록 expand → deploy → contract 순서를 사용한다.
- 각 운영 migration 전 PostgreSQL 백업과 복구 명령을 검증한다.
- 새 관계 데이터는 기존 Task 실행에 필수가 아니어야 한다.
- 외부 도구 실행은 idempotency key와 immutable payload를 사용한다.
- 배포 장애 시 마지막 정상 이미지/커밋과 DB revision 조합으로 되돌린다.
- rollback 시 수집한 신규 데이터는 삭제하지 말고 읽지 않는 방식으로 보존한다.

---

## RECOMMENDED NEXT STEP

### 단 하나의 다음 개발 단위: Project / Task Hierarchy Foundation

**목적**

JARVIS가 나중에 목표를 프로젝트와 하위 업무로 나눌 수 있도록 가장 작은 영속 기반을 만든다. 기존 독립 Task는 그대로 작동하고, 실행 순서·Agent·프롬프트·Telegram·승인 로직은 변경하지 않는다.

**수정할 파일**

- `app/models.py`: `Project` 추가, `Task.project_id`와 `Task.parent_task_id` nullable 관계 추가.
- `app/schemas.py`: Project create/read, Task의 선택 관계 필드 추가.
- `app/api/routes.py`: Project 생성/목록/상세와 관계 검증 추가.
- `app/services/task_service.py`: 기존 Task 생성·실행 회귀 보장, 필요 시 관계 감사 메타데이터만 추가.
- `app/db.py`: 기대 Alembic revision 갱신.

**새 파일**

- `migrations/versions/<revision>_project_task_hierarchy.py`
- `tests/test_project_task_hierarchy.py`

**DB migration**

- `projects` 테이블 신규 생성.
- `tasks.project_id` nullable FK 및 tenant 조회용 index 추가.
- `tasks.parent_task_id` nullable self-FK 및 index 추가.
- 기존 Task는 두 필드가 `NULL`인 루트/독립 Task로 유지.
- 삭제는 기본적으로 restrict 또는 soft lifecycle을 사용하고 cascade 삭제하지 않음.

**API 변경**

- `POST /api/v1/projects`
- `GET /api/v1/projects`
- `GET /api/v1/projects/{project_id}`
- 기존 `POST /api/v1/tasks`에 선택적 `project_id`, `parent_task_id` 추가.
- 기존 Task 응답에 동일 선택 필드 추가.
- 연결 대상이 같은 tenant인지 검증하고 자기 자신을 parent로 지정하는 요청을 거절.

**테스트**

- 기존 필드만 사용한 Task 생성/실행이 동일하게 통과.
- Project 생성/조회와 tenant 격리.
- Project에 연결된 Task 생성.
- parent/child Task 생성과 조회.
- 존재하지 않는 ID, 다른 tenant ID, self-parent 거절.
- API/worker/Telegram 기존 회귀 테스트 전체 통과.
- SQLite 단위 테스트와 PostgreSQL migration round trip 통과.

**완료 기준**

1. 기존 53개 테스트를 포함한 전체 자동검사가 통과한다.
2. 현재 고정 V0.5 workflow와 실제 Telegram 명령 동작이 바뀌지 않는다.
3. 기존 운영 데이터가 손실 없이 migration 된다.
4. Project 및 parent Task 관계가 API와 DB에서 tenant-safe하게 저장·조회된다.
5. 새 구조는 아직 자동 위임이나 동적 실행을 시작하지 않는다.
6. 문서에 다음 단계가 Workflow 기록 계층임을 명시한다.

**위험과 대응**

| 위험 | 대응 |
|---|---|
| cross-tenant 관계 누출 | FK 존재 여부만 보지 않고 서비스 계층에서 tenant 일치 검사 |
| task hierarchy cycle | 이번 단위는 직접 self-parent 차단, 향후 임의 depth 위임 전에 전체 cycle 검사 추가 |
| 삭제 시 하위 데이터 손실 | cascade 금지, Project 삭제 API는 이번 단위에서 제외 |
| API 하위 호환성 | 모든 신규 입력/DB 필드를 nullable로 유지 |
| 범위 팽창 | Goal, Workflow, delegation, UI, Attention은 이번 단위에서 구현하지 않음 |

이 단위가 가장 작은 안전한 다음 단계인 이유는 JARVIS의 계획·위임·주의 관리가 모두 업무 관계를 필요로 하는 반면, 현재 검증된 실행 제어면에는 어떤 행동 변경도 요구하지 않기 때문이다.
