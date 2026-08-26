# AI Team V2 Phase 1 추상화 구조

Phase 1은 V0.4의 사용자 동작과 고정 Orchestrator를 유지하면서, 향후 Runtime·모델·도구·지식 계층을
교체할 수 있는 코드 경계를 추가한다. Hermes, Grok, pgvector, LiteLLM, Workflow V2는 아직 도입하지 않는다.

## 디렉터리 구조

```text
app/agents/
├─ contracts.py              # Runtime/Model/Tool/Knowledge protocol
├─ definitions.py            # AgentDefinition, ModelPolicy
├─ registry.py               # AgentRegistry
├─ outputs.py                # 기존 Chief/Reviewer 구조화 출력
├─ prompts.py                # 기존 V0.4 prompt
├─ v04_registry.py           # 기존 4개 역할 정의
├─ orchestrator.py           # 기존 고정 workflow 유지
└─ runtimes/
   ├─ __init__.py
   └─ openai_agents.py       # 기존 OpenAI Agents SDK Adapter
```

## AgentRuntime

`AgentRuntime`은 AgentDefinition 하나와 입력 문자열을 받아 `AgentRunResult`를 반환한다. Runtime은 회사
업무 계획, 승인, DB, 최종 보고를 소유하지 않는다. 따라서 Phase 2의 Hermes도 동일한 계약을 구현하는 별도
Adapter로 추가하거나 제거할 수 있다.

```text
Fixed V0.4 Orchestrator
        |
        v
AgentRuntime protocol
        |
        +-- OpenAIAgentsRuntime (Phase 1)
        +-- HermesRuntime       (Phase 2 candidate)
```

`AgentRunResult`는 구조화 또는 텍스트 출력을 그대로 전달하고 input/output/total token 사용량을 공통 형식으로
반환한다.

## AgentDefinition

현재 구조는 다음 필드를 표현한다.

- `key`, `role`, `purpose`
- `system_prompt`, `output_schema`
- `model_policy`
- `memory_scope`
- `allowed_tools`, `permissions`, `approval_policy`
- `knowledge_collections`
- `workflow_templates`, `schedules`, `working_environment`
- `version`, `evaluation_status`

Phase 1에서 실제 실행에 사용하는 필드는 prompt, output schema, model policy, allowed tools이다. 나머지는
향후 기능을 위한 선언적 경계이며 scheduler, permission engine, workflow engine을 미리 구현하지 않는다.

## AgentRegistry

`build_v04_agent_registry()`는 기존 역할을 다음 key로 등록한다.

| key | 역할 | 현재 도구 | 구조화 출력 |
|---|---|---|---|
| `chief_of_staff` | Chief of Staff | 없음 | `ChiefOutput` |
| `research` | Research Agent | `web_search` | 없음 |
| `strategy` | Strategy Agent | 없음 | 없음 |
| `reviewer` | Reviewer Agent | 없음 | `ReviewerOutput` |

Registry는 중복 key를 거부하고, 존재하지 않는 역할을 요청하면 즉시 오류를 낸다. Phase 1에서는 DB와 관리
화면을 추가하지 않고 프로세스 시작 시 설정에서 Registry를 구성한다.

## ModelProvider와 ModelPolicy

`ModelPolicy`는 provider, model, capability 메타데이터만 가진다. `ModelProvider`는 이 정책을 Runtime이
사용할 모델 식별자로 해석한다. 현재 `OpenAIModelProvider`만 존재하며 V0.4의 `OPENAI_MODEL` 값을 그대로
사용한다. 라우팅, fallback, 예산, 공급자 상태 검사는 Phase 6 범위다.

## ToolProvider

`ToolProvider`는 AgentDefinition의 `allowed_tools` 이름을 Runtime 도구로 변환한다. 현재
`OpenAIToolProvider`는 `web_search`만 OpenAI `WebSearchTool`로 변환하며, 등록되지 않은 도구 이름은
실행하지 않고 오류를 낸다. 실제 permission/approval 정책 엔진은 후속 Phase 범위다.

## KnowledgeRetriever

`KnowledgeRetriever` protocol만 추가했다. 기존 `company_context` 생성과 DB 구조는 변경하지 않았다.
Knowledge V2에서 Operational State, Company Knowledge, Agent Memory를 구분하고 draft/candidate 검토 흐름을
추가할 때 이 경계 뒤에 구현한다.

## 기존 OpenAI 코드의 Adapter화

기존 `orchestrator.py`에 있던 OpenAI `Agent`, `Runner`, `WebSearchTool` 생성·호출 코드를
`runtimes/openai_agents.py`로 옮겼다.

고정 Orchestrator에는 다음 동작이 그대로 남아 있다.

1. Research와 Strategy 병렬 실행
2. Chief of Staff 취합
3. Reviewer PASS/REWORK
4. 설정된 최대 횟수 안에서 Chief 재작업
5. 토큰 합산과 approval request 반환

따라서 V0.4의 Task/DB/API/UI/Telegram 경로는 변경되지 않고, OpenAI 실행 방법만 Runtime 경계를 통과한다.

## DB 호환성

Phase 1은 SQLAlchemy model과 Alembic migration을 변경하지 않는다. 새 AgentDefinition과 Registry는 현재
메모리 기반 코드 정의다. 기존 Task, TaskRun, Approval, AuditEvent, Memory, Decision, KnowledgeItem 데이터와
schema revision `12738dc9272a`를 그대로 사용한다.

## 테스트 범위

- 기존 V0.4 회귀 테스트 전체
- 기존 4개 역할이 Registry에 표현되는지
- 미래 확장 필드와 output schema가 보존되는지
- 중복·누락 AgentDefinition 거부
- OpenAI Agent/Runner/WebSearchTool Adapter 변환
- Runtime 주입 상태에서 Research/Strategy 병렬 실행
- Chief 취합, Reviewer REWORK 후 PASS, approval과 token 합산
- Ruff lint/format, compileall
- 임시 SQLite DB Alembic upgrade/downgrade/upgrade

실제 OpenAI 네트워크 호출, Docker/PostgreSQL/Redis/Celery 통합, 실제 Telegram은 필요한 외부 설정이 없어
이번 자동 검증에 포함하지 않는다.
