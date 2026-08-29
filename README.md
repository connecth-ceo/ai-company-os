# AI Company OS

대표(CEO)가 자연어로 업무를 지시하면 AI 비서실장이 조사·전략 담당을 조율하고,
검증 담당의 PASS/REWORK 판정을 거쳐 결과를 보고하는 클라우드 우선 V0입니다.

## 현재 포함된 것

- FastAPI 업무 API와 자동 문서 (`/docs`)
- Chief of Staff, Research, Strategy, Reviewer 실행 흐름
- 명시적 Telegram 명령으로 호출하는 Marketing 초안 및 Legal Risk Review 전문 에이전트
- OpenAI 비용 없이 현재 업무·승인 상태를 요약하는 Telegram 데일리 브리핑
- 매일 07:00 KST 자동 브리핑, 중복 방지, quiet hours, 실패 기록과 안전 재시도
- PostgreSQL 기반 업무·기억·의사결정·지식·승인 영속화
- Celery/Redis 백그라운드 작업
- OpenAI Agents SDK 실행 모드와 API 키 없는 mock 모드
- 중앙 Tool Gateway를 통한 읽기 전용 웹 검색 권한 검증과 감사 메타데이터
- 외부 행동 payload hash·만료·단일사용 범위를 고정하는 제안 전용 ActionIntent
- 승인·hash·만료를 재검사하고 외부 호출 없이 단일사용 claim·결과·timeout 격리를 기록하는 ExecutionAttempt 원장
- 이메일·일반 게시·SmartStore 미래 action을 allowlist하고 실제 실행은 닫아 둔 Connector Registry
- 프롬프트·비밀값을 제외한 읽기 전용 AI Employee Registry
- Goal → Project → Task 전략 계층, 제한된 상태 전이, 읽기 전용 건강도와 AI 직원 권한을 보여주는 Executive UI
- Docker Compose 로컬/배포 기준 구성
- API 키 인증, 회사별 데이터 격리, 중복 요청 방지
- 실행 재시도·시간 제한·토큰 사용량·감사 이벤트
- 버전 있는 WorkflowDefinition과 TaskRun별 불변 실행계획 기록
- Orchestrator 매개 하위업무 위임과 깊이·개수·순환·역할·예산 가드레일
- 위임 전용 단일 역할 실행, 정책 재검사, 토큰·시간 사용 원장
- CEO 웹 대시보드와 Telegram webhook
- 저장된 회사 기억·대표 결정·지식을 다음 AI 업무에 자동 반영
- 기억·유효한 대표 결정·지식을 비용 없이 찾는 테넌트별 통합 검색
- 대표 결정의 제안·활성·철회·만료·대체 이력과 적용 범위 관리
- 결정 상태·재검토일·만료일·근거 검증 상태를 비용 없이 종합하는 결정 신뢰도 큐
- 활성 결정과 담당자·마감일이 있는 약속의 실행 연결률·지연·완료를 계산하는 결정 후속 실행 큐
- 연구·대표 결정의 출처 URL, TaskRun, 내용 해시와 검증 상태를 잇는 읽기 전용 근거 원장
- 내용 해시 재확인, 검증·반려·정정 이력과 감사 이벤트를 갖춘 근거 검토 원장
- 반려·미검증·관찰 근거를 비용 없이 우선순위화하는 근거 품질 큐와 검증률 요약
- 담당자·마감일·출처·관련 결정이 있는 약속/후속조치와 기한 초과 추적
- 지연 약속·장기 실행·업무 실패·승인 적체와 결정 신뢰도·후속 실행 위험을 통합 정렬하고 확인·후속 Task·마감 약속까지 잇는 대표 주의 폐루프
- 저위험 내부 주의신호만 queued Task·기한 약속으로 자동계획하는 기본 비활성·dry-run 우선 정책
- 외부 발송·결제·삭제·배포 요청을 대표 승인함에 자동 등록
- 민감 역할·고비용 AI 위임을 대표 승인 전 실행하지 않는 승인 게이트
- Worker 정체 위임의 dry-run 진단, 안전 복구, 비용 중복 방지 격리
- 실행 전 비용 예약, 실행별 추정 비용 원장, 월 OpenAI 예산 초과 차단
- CEO Desk에서 회사 기억과 대표 결정을 직접 기록
- Alembic 데이터베이스 마이그레이션
- Render용 클라우드 Blueprint
- Caddy 자동 HTTPS가 포함된 단일 VPS 배포 구성
- 운영 설정 fail-fast 검증과 DB/Redis/배포 smoke check

## 가장 빠른 실행

Windows에서 Docker 없이 먼저 사용하려면 `START_AI_COMPANY_MOCK.bat`을 더블클릭합니다. OpenAI
API 키를 `.env`에 설정한 뒤에는 `START_AI_COMPANY_REAL_AI.bat`으로 실제 AI 모드를 실행할 수 있습니다.

Docker 전체 구성은 다음 순서입니다.

1. `.env.example`을 `.env`로 복사합니다.
2. `POSTGRES_PASSWORD`를 긴 영문·숫자 임의값으로 바꿉니다. Compose가 DB URL을 같은 값으로 구성합니다.
3. 첫 확인은 `AI_PROVIDER=mock` 그대로 둡니다.
4. `docker compose up --build`를 실행합니다.
5. 브라우저에서 `http://localhost:8000`을 열면 CEO Desk가 표시됩니다.
6. 개발용 API 문서는 `http://localhost:8000/docs`입니다.

실제 AI 실행은 `.env`의 `AI_PROVIDER=openai`, `OPENAI_API_KEY=...`로 바꾼 뒤
API와 worker를 다시 시작하면 됩니다. 비밀 키는 저장소에 커밋하지 마세요.

Docker 없이 개발할 때는 `DATABASE_URL=sqlite+aiosqlite:///./ai_company.db`,
`TASK_EXECUTION_MODE=inline`을 사용하면 Redis/PostgreSQL 없이도 확인할 수 있습니다.

실제 OpenAI, Telegram, Docker, Render 설정 방법과 검증 체크리스트는
[docs/SETUP_AND_OPERATIONS_KO.md](docs/SETUP_AND_OPERATIONS_KO.md)에 있습니다.
전체 설계는 [docs/MASTER_IMPLEMENTATION_SPEC.md](docs/MASTER_IMPLEMENTATION_SPEC.md)에 있습니다.
V2 리팩터링 전 V0.4 기준선은 [docs/V0_4_BASELINE_KO.md](docs/V0_4_BASELINE_KO.md), 데이터 백업·복구는
[docs/DB_BACKUP_RESTORE_KO.md](docs/DB_BACKUP_RESTORE_KO.md), 주요 구조 결정은
[ADR-0001](docs/adr/0001-preserve-v0-control-plane-and-add-runtime-boundaries.md)에 기록되어 있습니다.
Phase 1의 Runtime·AgentDefinition·Registry 구조는
[docs/PHASE_1_ABSTRACTIONS_KO.md](docs/PHASE_1_ABSTRACTIONS_KO.md)에 설명되어 있습니다.
운영화 구현과 검증 결과는
[docs/OPERATIONALIZATION_COMPLETION_REPORT_KO.md](docs/OPERATIONALIZATION_COMPLETION_REPORT_KO.md)에 있습니다.
전문 기능의 사용법과 안전 경계는
[docs/SPECIALIST_FEATURES_KO.md](docs/SPECIALIST_FEATURES_KO.md)에 있습니다.
JARVIS형 확장 분석은 [JARVIS_AI_COMPANY_OS_GAP_ANALYSIS.md](JARVIS_AI_COMPANY_OS_GAP_ANALYSIS.md),
Goal/Project/Task 전략 계층과 상태 전이는 [docs/GOAL_PROJECT_HIERARCHY_KO.md](docs/GOAL_PROJECT_HIERARCHY_KO.md),
구현·검증 결과는 [docs/PORTFOLIO_LIFECYCLE_COMPLETION_REPORT_KO.md](docs/PORTFOLIO_LIFECYCLE_COMPLETION_REPORT_KO.md),
목표일·실패 업무·보류 상태 기반 포트폴리오 건강도는 [docs/PORTFOLIO_HEALTH_KO.md](docs/PORTFOLIO_HEALTH_KO.md),
구현·검증 결과는 [docs/PORTFOLIO_HEALTH_COMPLETION_REPORT_KO.md](docs/PORTFOLIO_HEALTH_COMPLETION_REPORT_KO.md),
Project/상·하위 Task API는 [docs/PROJECT_TASK_HIERARCHY_KO.md](docs/PROJECT_TASK_HIERARCHY_KO.md)에
설명되어 있습니다. 기존 고정 실행의 버전·계획·결과 기록 구조는
[docs/WORKFLOW_RECORDING_LAYER_KO.md](docs/WORKFLOW_RECORDING_LAYER_KO.md)에 있습니다.
안전한 하위업무 생성 정책은
[docs/DELEGATION_GUARDRAILS_KO.md](docs/DELEGATION_GUARDRAILS_KO.md), 단일 역할 실행 절차는
[docs/DELEGATED_ROLE_EXECUTION_KO.md](docs/DELEGATED_ROLE_EXECUTION_KO.md)에 있습니다.
구현·검증 완료 범위와 아직 운영 자격증명이 필요한 항목은
[docs/DELEGATED_ROLE_EXECUTION_COMPLETION_REPORT_KO.md](docs/DELEGATED_ROLE_EXECUTION_COMPLETION_REPORT_KO.md)에
구분해 기록했습니다.
실행별 비용 추정과 월 예산 통제는
[docs/AI_COST_CONTROL_KO.md](docs/AI_COST_CONTROL_KO.md)에 설명되어 있습니다.
구현·검증 범위와 배포 후 남은 확인은
[docs/AI_COST_CONTROL_COMPLETION_REPORT_KO.md](docs/AI_COST_CONTROL_COMPLETION_REPORT_KO.md)에 있습니다.
구조화된 대표 결정의 상태·효력·범위·대체 규칙은
[docs/DECISION_MEMORY_LIFECYCLE_KO.md](docs/DECISION_MEMORY_LIFECYCLE_KO.md), 실제 검증 결과는
[docs/DECISION_MEMORY_LIFECYCLE_COMPLETION_REPORT_KO.md](docs/DECISION_MEMORY_LIFECYCLE_COMPLETION_REPORT_KO.md)에
기록되어 있습니다.
약속·담당자·마감일·상태·결정 연결과 데일리 브리핑 반영은
[docs/COMMITMENT_TRACKING_KO.md](docs/COMMITMENT_TRACKING_KO.md)에 설명되어 있습니다.
구현·검증 완료 범위와 운영 확인 항목은
[docs/COMMITMENT_TRACKING_COMPLETION_REPORT_KO.md](docs/COMMITMENT_TRACKING_COMPLETION_REPORT_KO.md)에
구분해 기록했습니다.
대표가 지금 확인할 예외를 규칙으로 계산하는 방법은
[docs/ATTENTION_QUEUE_KO.md](docs/ATTENTION_QUEUE_KO.md), 구현·검증 상태는
[docs/ATTENTION_QUEUE_COMPLETION_REPORT_KO.md](docs/ATTENTION_QUEUE_COMPLETION_REPORT_KO.md)에 있습니다.
자동 브리핑의 시간·중복 방지·재시도 정책은
[docs/PROACTIVE_BRIEFING_DELIVERY_KO.md](docs/PROACTIVE_BRIEFING_DELIVERY_KO.md), 구현·검증 상태는
[docs/PROACTIVE_BRIEFING_DELIVERY_COMPLETION_REPORT_KO.md](docs/PROACTIVE_BRIEFING_DELIVERY_COMPLETION_REPORT_KO.md)에
구분해 기록했습니다.
도구 등록·권한·위험 차단과 감사 의미는
[docs/TOOL_GATEWAY_KO.md](docs/TOOL_GATEWAY_KO.md), 구현·검증 결과는
[docs/TOOL_GATEWAY_COMPLETION_REPORT_KO.md](docs/TOOL_GATEWAY_COMPLETION_REPORT_KO.md)에 기록되어 있습니다.
승인 대상을 불변 payload와 연결하는 구조는
[docs/ACTION_INTENT_KO.md](docs/ACTION_INTENT_KO.md), 구현·검증 범위는
[docs/ACTION_INTENT_COMPLETION_REPORT_KO.md](docs/ACTION_INTENT_COMPLETION_REPORT_KO.md)에 기록되어 있습니다.
승인된 외부 행동의 준비·원자적 단일사용 claim 원장은
[docs/EXECUTION_ATTEMPT_LEDGER_KO.md](docs/EXECUTION_ATTEMPT_LEDGER_KO.md)에 기록되어 있습니다.

외부 실행 결과의 원문 없는 불변 증빙 규칙은
[docs/EXECUTION_RECEIPT_KO.md](docs/EXECUTION_RECEIPT_KO.md)에 기록되어 있습니다.
외부 API connector의 action allowlist, 버전별 payload JSON Schema와 실행 가능 상태 계약은
[docs/CONNECTOR_REGISTRY_KO.md](docs/CONNECTOR_REGISTRY_KO.md)에 기록되어 있습니다.
AI 직원 역할·버전·도구·승인 정책 조회 기준은
[docs/AI_EMPLOYEE_REGISTRY_KO.md](docs/AI_EMPLOYEE_REGISTRY_KO.md), 구현 범위는
[docs/AI_EMPLOYEE_REGISTRY_COMPLETION_REPORT_KO.md](docs/AI_EMPLOYEE_REGISTRY_COMPLETION_REPORT_KO.md)에 기록되어 있습니다.
프로젝트 포트폴리오와 읽기 전용 AI 팀을 CEO Desk에 표시하는 기준은
[docs/EXECUTIVE_UI_KO.md](docs/EXECUTIVE_UI_KO.md)에 설명되어 있습니다.
기억·대표 결정·지식을 통합 조회하는 검색 규칙과 안전 경계는
[docs/COMPANY_CONTEXT_SEARCH_KO.md](docs/COMPANY_CONTEXT_SEARCH_KO.md)에 설명되어 있습니다.
연구 산출물과 대표 결정의 출처·실행·해시 연결은
[docs/PROVENANCE_FOUNDATION_KO.md](docs/PROVENANCE_FOUNDATION_KO.md), 구현·검증 범위는
[docs/PROVENANCE_FOUNDATION_COMPLETION_REPORT_KO.md](docs/PROVENANCE_FOUNDATION_COMPLETION_REPORT_KO.md)에 기록되어 있습니다.
대표의 근거 검증·반려·정정 이력과 해시 무결성 규칙은
[docs/PROVENANCE_REVIEW_KO.md](docs/PROVENANCE_REVIEW_KO.md), 구현·검증 범위는
[docs/PROVENANCE_REVIEW_COMPLETION_REPORT_KO.md](docs/PROVENANCE_REVIEW_COMPLETION_REPORT_KO.md)에 기록되어 있습니다.
근거 품질 분류·정렬 규칙과 CEO Desk 검토 큐는
[docs/PROVENANCE_QUALITY_QUEUE_KO.md](docs/PROVENANCE_QUALITY_QUEUE_KO.md), 구현·검증 범위는
[docs/PROVENANCE_QUALITY_QUEUE_COMPLETION_REPORT_KO.md](docs/PROVENANCE_QUALITY_QUEUE_COMPLETION_REPORT_KO.md)에 기록되어 있습니다.
대표 결정의 실행 준비도와 우선 확인 사유를 계산하는 규칙은
[docs/DECISION_READINESS_QUEUE_KO.md](docs/DECISION_READINESS_QUEUE_KO.md), 구현·검증 범위는
[docs/DECISION_READINESS_QUEUE_COMPLETION_REPORT_KO.md](docs/DECISION_READINESS_QUEUE_COMPLETION_REPORT_KO.md)에 기록되어 있습니다.
활성 결정이 후속 약속으로 이어졌는지 계산하는 규칙은
[docs/DECISION_FOLLOW_THROUGH_KO.md](docs/DECISION_FOLLOW_THROUGH_KO.md), 구현·검증 범위는
[docs/DECISION_FOLLOW_THROUGH_COMPLETION_REPORT_KO.md](docs/DECISION_FOLLOW_THROUGH_COMPLETION_REPORT_KO.md)에 기록되어 있습니다.
결정 신뢰도와 후속 실행 위험을 대표 주의 큐·브리핑에 합치는 기준은
[docs/DECISION_ATTENTION_INTEGRATION_COMPLETION_REPORT_KO.md](docs/DECISION_ATTENTION_INTEGRATION_COMPLETION_REPORT_KO.md)에 기록되어 있습니다.
동일 주의 신호의 확인 기록, 변경 시 재등장, 브리핑 중복 억제 기준은
[docs/ATTENTION_ACKNOWLEDGEMENT_COMPLETION_REPORT_KO.md](docs/ATTENTION_ACKNOWLEDGEMENT_COMPLETION_REPORT_KO.md)에 기록되어 있습니다.
주의 신호를 실행 전 Task와 담당자·기한 Commitment로 전환하고 상태를 추적하는 기준은
[docs/ATTENTION_FOLLOW_UP_LOOP_COMPLETION_REPORT_KO.md](docs/ATTENTION_FOLLOW_UP_LOOP_COMPLETION_REPORT_KO.md)에 기록되어 있습니다.
저위험 내부 신호 자동계획의 허용·차단 범위와 기본 비활성 스케줄은
[docs/ATTENTION_AUTOMATION_POLICY_KO.md](docs/ATTENTION_AUTOMATION_POLICY_KO.md)에 기록되어 있습니다.

## V0.4에서 이어지는 실제 사용 흐름

1. CEO Desk에서 회사 원칙과 대표 선호를 `회사 기억`으로 저장합니다.
2. 중요한 선택은 `대표 결정`으로 기록합니다.
3. 새 업무를 지시하면 최근 기억·결정·축적 지식이 AI 팀에 자동 전달됩니다.
4. Research 결과는 회사 지식으로 자동 축적됩니다.
5. 외부 발송·결제·삭제·배포처럼 영향이 있는 행동은 실행하지 않고 승인함에 올립니다.

외부 이메일 발송, 결제, 삭제 또는 배포 승인은 여전히 기록 전용이며 승인만으로 외부 행동을 자동 실행하지
않습니다. AI 역할 위임은 별도의 제한된 실행 경로에서만 승인과 연결됩니다. 기본적으로 법률검토와 설정된
비용 기준을 넘는 위임은 승인 전 실행되지 않으며, 승인 후에도 등록된 단일 역할만 초안·분석 범위로 실행합니다.

## Telegram 전문 기능

- `/briefing`: 최근 24시간의 완료·진행·실패 업무와 승인 대기 건을 즉시 요약합니다. AI 호출 비용이 없습니다.
- `/marketing <요청>`: 조사·전략 결과를 바탕으로 마케팅 초안을 만듭니다. 외부 게시나 광고 집행은 하지 않습니다.
- `/legal <요청>`: 예비 법률·규제 위험을 정리합니다. 법률 자문이나 최종 법적 결론이 아닙니다.

일반 문장은 기존 V0.4 흐름으로 처리되며, 전문 에이전트는 위 명령을 명시했을 때만 추가됩니다.
