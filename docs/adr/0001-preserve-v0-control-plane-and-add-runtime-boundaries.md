# ADR-0001: V0 제어 계층을 유지하고 교체 가능한 실행 경계를 추가한다

- 상태: Accepted
- 결정일: 2026-08-26
- 적용 범위: V2 Phase 0–1

## 배경

V0.4는 FastAPI, PostgreSQL, Celery, Redis, 업무·승인·감사 데이터, CEO Dashboard, Telegram과 고정된
4개 AI 역할을 제공한다. V2는 장기적으로 여러 Agent Runtime과 LLM 공급자, 지식 검색, MCP 도구,
7개 전문 역할을 지원해야 한다.

전체 시스템을 새로운 Agent framework로 교체하면 현재 정상 동작과 회사 데이터의 소유권을 위험에 빠뜨린다.
반대로 현재 고정 Orchestrator 안에 공급자별 코드를 계속 추가하면 역할·모델·도구·권한이 강하게 결합된다.

## 결정

1. V0.4의 FastAPI/DB/Task/Approval/Audit/UI/Telegram을 회사 소유 Control Plane으로 유지한다.
2. 현재 고정 Orchestrator의 사용자 동작과 결과를 Phase 1에서 변경하지 않는다.
3. 다음 확장 경계를 작은 Python protocol/추상 타입과 데이터 정의로 추가한다.
   - `AgentRuntime`
   - `AgentDefinition`, `AgentRegistry`
   - `ModelProvider`, `ModelPolicy`
   - `ToolProvider`
   - `KnowledgeRetriever`
4. 기존 OpenAI Agents SDK 실행은 제거하지 않고 첫 번째 `AgentRuntime` Adapter로 이동한다.
5. Hermes, Grok, pgvector, Wiki.js, LiteLLM, 새 VPS 구성은 Phase 1에 도입하지 않는다.
6. 아직 실행하지 않는 AgentDefinition 필드는 표현만 가능하게 하고 별도 기능을 구현하지 않는다.
7. 회사 지식, 운영 상태, Agent Memory를 개념적으로 분리한다. AI 생성 정보는 향후 draft/candidate 검토 후
   Company Knowledge로 승격한다.

## 결과

### 긍정적 결과

- V0.4 기준선으로 즉시 돌아갈 수 있다.
- Hermes 또는 다른 Runtime을 현재 시스템을 교체하지 않고 시험할 수 있다.
- 역할과 실행 기술이 분리되고 AgentDefinition을 버전 관리할 수 있다.
- 향후 Model Router, MCP, Knowledge V2의 위치가 명확해진다.

### 비용과 제약

- Phase 1에는 기존 고정 Orchestrator와 새 Registry가 동시에 존재한다.
- 일부 필드는 미래 확장용 메타데이터로만 존재한다.
- DB 영속화와 관리 UI는 후속 Phase에서 별도로 구현해야 한다.

## 검토한 대안

### Hermes로 전체 Orchestrator 즉시 교체

현재 동작과 데이터 소유권을 위험에 빠뜨리고 특정 Runtime에 종속되므로 채택하지 않았다.

### 현재 Orchestrator에 공급자별 분기 계속 추가

단기 구현은 빠르지만 역할·모델·도구·권한이 한 파일에 결합되어 V2 확장이 어려워지므로 채택하지 않았다.

### Workflow V2를 Phase 1에서 함께 구현

변경 범위가 커지고 V0.4 호환성을 검증하기 어려우므로 Phase 4까지 미룬다.

## 수용 기준

- 기존 테스트 전체 통과
- mock 모드와 기존 4개 역할의 결과 호환
- Research/Strategy 병렬 실행 유지
- Chief 취합, Reviewer PASS/REWORK, Approval, Telegram 동작 유지
- OpenAI 코드는 Runtime Adapter를 통해 호출
- 새 경계의 단위 테스트 추가
