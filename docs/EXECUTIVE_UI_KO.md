# CEO Desk Executive UI

## 목적

이미 구현된 Project/Task 관계와 AI Employee Registry를 대표가 한 화면에서 확인하고 사용할 수 있게
한다. 이 단계는 기존 실행 제어면을 바꾸지 않으며 외부 행동이나 유료 AI 호출을 추가하지 않는다.

## 프로젝트 화면

- 최근 프로젝트와 상태, 연결된 전체·진행·완료 업무 수를 표시한다.
- CEO Desk에서 프로젝트를 만들 수 있다.
- 새 업무 지시 시 프로젝트를 선택하면 기존 `Task.project_id`에 연결한다.
- 완료·보관 프로젝트는 신규 업무 선택 목록에서 제외하지만 이력 화면에는 남긴다.

## AI 팀 화면

- `GET /api/v1/agents`의 읽기 전용 프로필을 카드로 표시한다.
- 역할, 목적, provider/model, 허용 도구, 승인 정책, 평가 상태만 보여준다.
- system prompt, output schema, API key, 내부 비밀값은 API와 화면 모두에서 제외한다.
- AI 직원 추가·수정·삭제 기능은 제공하지 않는다.

## 안전 경계

- 프로젝트 생성은 회사 내부 데이터 기록이며 자동 실행을 시작하지 않는다.
- AI 팀 화면은 읽기 전용이다.
- 기존 승인함, Tool Gateway, ActionIntent 규칙은 그대로 유지한다.
- 모든 API 요청은 기존 `X-API-Key`, `X-Tenant-ID` 인증과 테넌트 격리를 사용한다.

## 검증

- CEO Desk HTML에 프로젝트 선택·목록·생성 폼과 AI 팀 목록이 존재하는지 검사한다.
- JavaScript가 기존 `/api/v1/projects`, `/api/v1/agents`만 사용하는지 검사한다.
- 프로젝트를 선택한 신규 업무가 `project_id`를 전달하는지 회귀 테스트로 고정한다.
