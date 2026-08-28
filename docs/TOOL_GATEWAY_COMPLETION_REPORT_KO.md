# Tool Gateway Foundation 완료 보고서

작성일: 2026-08-29

## 구현 완료

- 기존 OpenAI runtime의 직접 `web_search` 연결을 중앙 Tool Gateway 경로로 이동
- 도구 catalog, 위험 수준, 필요한 permission, 부작용·승인 필요 여부의 typed 정의
- 중복·미등록·permission 누락·비읽기 도구의 fail-closed 차단
- Research Agent의 기존 `web.search` 권한과 웹 검색 동작 보존
- AgentRun, TaskRun artifact, AuditEvent에 권한 부여 메타데이터 기록
- 권한 부여와 실제 호출을 구분하는 `invocation_observed` 표시
- 비밀값 없이 catalog를 확인하는 `GET /api/v1/tool-catalog`
- OpenAI 호출과 데이터 생성 없이 배포 상태를 확인하는 `SMOKE_TOOL_GATEWAY.bat`

## 로컬에서 실제 확인한 것

- 전체 자동검사 `127 passed`
- Tool Gateway·AgentRuntime·위임 실행 집중검사 `16 passed`
- Ruff 정적검사 통과
- Ruff format 검사 통과 (`108 files already formatted`)
- Python compileall 및 dependency 검사 통과
- 브라우저 JavaScript와 운영 smoke PowerShell 구문검사 통과
- 정상 Research 웹 검색 도구 변환과 권한 메타데이터 생성
- permission 누락 차단
- 외부 쓰기 도구의 불변 승인 문맥 없는 실행 차단
- 인증된 catalog API 응답과 secret 비노출
- 기존 V0.4 Orchestrator·Telegram·위임·승인·비용·브리핑 회귀검사 통과

Pytest 캐시 폴더 쓰기 권한 경고 1건은 테스트 결과와 애플리케이션 동작에 영향이 없습니다.

## 아직 운영 환경에서 확인할 것

- GitHub main 반영 후 Render Web/Worker 자동 배포
- 운영 `GET /api/v1/tool-catalog` 응답
- 실제 OpenAI Research 업무 1건에서 `tool.access_authorized` 감사 이벤트 생성
- OpenAI SDK가 실제 tool invocation event를 안정적으로 제공할 때 호출 단위 원장 연결

## 명시적으로 구현하지 않은 것

- 이메일, 게시, 결제, 삭제, 배포 등 외부 쓰기 도구
- 승인 후 자동 외부 행동
- 자격증명을 Agent prompt에 주입하는 방식
- 웹 검색어와 결과 전문의 별도 ToolCall 원장 저장

## 다음 권장 구현 단위

`Approval`을 단순 자연어 기록에서 불변 `ActionIntent` payload와 연결하는 제안 전용 기반을 추가합니다.
이 단계에서도 실제 외부 도구는 실행하지 않고 payload hash, 만료, 1회성 범위, 상태 전이만 먼저
검증합니다.
