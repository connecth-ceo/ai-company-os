# AI Employee Registry 사용·안전 기준

AI Employee Registry는 현재 코드에 등록된 AI 직원의 역할과 운영 정책을 읽기 전용으로 보여줍니다.
별도 데이터베이스 명부를 만들지 않으므로 기존 `AgentDefinition`과 `AgentRegistry`가 계속 단일 기준입니다.

## 조회 API

- `GET /api/v1/agents`: 전체 AI 직원 목록
- `GET /api/v1/agents/{agent_key}`: 직원 한 명의 상세 정책

현재 조회되는 직원은 Chief of Staff, Research, Strategy, Reviewer, Marketing,
Legal Risk Review의 6명입니다.

## 공개하는 정보

- 역할 key, 표시 역할명, 목적
- provider, model, capability
- memory·knowledge 범위
- 허용 도구와 권한
- 대표 승인 정책
- workflow template과 schedule 선언
- 작업환경, 버전, 평가 상태
- structured output 사용 여부

## 공개하지 않는 정보

- system prompt 원문
- output schema class와 Python runtime 객체
- OpenAI·Telegram·APP API key
- 환경 변수와 credential
- 실행 중인 내부 context나 모델 입력

## 안전 경계

1. API는 인증·회사 context를 거친 읽기 요청만 허용합니다.
2. 등록·수정·삭제 endpoint를 제공하지 않습니다.
3. 조회는 AuditEvent나 업무를 생성하지 않습니다.
4. 직원 정의 변경은 검토와 테스트를 거친 코드 배포로만 가능합니다.
5. Registry 조회 자체는 OpenAI 호출과 비용을 발생시키지 않습니다.
