# Tool Gateway 운영 기준

## 목적

에이전트가 요청한 도구를 런타임에 직접 연결하지 않고 중앙 정책 경계를 통과시킵니다. 기존
Research Agent의 공개 웹 검색만 이 경로로 이동하며 V0.4 업무 순서와 결과 형식은 바꾸지 않습니다.

## 현재 등록 도구

| 도구 | 용도 | 위험 | 필요한 권한 | 외부 부작용 |
| --- | --- | --- | --- | --- |
| `web_search` | 공개 웹 자료 조사 | `read_only` | `web.search` | 없음 |

등록 목록은 인증된 `GET /api/v1/tool-catalog`에서 확인할 수 있습니다. 응답에는 비밀값이나 자격증명
위치가 포함되지 않습니다.

## 실행 전 검사

Tool Gateway는 AgentDefinition을 기준으로 다음 순서로 검사합니다.

1. 같은 도구가 중복 선언되지 않았는지 확인합니다.
2. 도구가 중앙 catalog와 해당 런타임 factory에 모두 등록됐는지 확인합니다.
3. AgentDefinition의 `permissions`에 도구가 요구하는 모든 권한이 있는지 확인합니다.
4. 읽기 전용이 아니거나 외부 부작용이 있는 도구는 불변 승인 문맥이 없으면 차단합니다.
5. 통과한 도구만 OpenAI Agents SDK에 전달합니다.

검사 실패는 fail-closed입니다. 알 수 없는 도구, 권한 누락, 쓰기 도구는 모델 호출 전에 실패합니다.

## 감사 기록의 정확한 의미

`tool.access_authorized`는 특정 AgentRun에 도구가 **노출되도록 정책 검사를 통과했다**는 뜻입니다.
현재 OpenAI SDK 경계에서 실제 검색 호출을 확실하게 관찰하지 못한 경우
`invocation_observed=false`로 기록합니다. 이 값을 실제 호출 증거로 해석하면 안 됩니다.

권한 기록은 TaskRun artifact와 AuditEvent에 도구 이름, Agent key, 위험 수준, 필요한 권한만 남깁니다.
검색어, 검색 결과, API 키는 이 메타데이터에 저장하지 않습니다.

## 안전 경계

- 외부 게시, 이메일 발송, 결제, 삭제, 배포 도구는 catalog에 등록되어 있지 않습니다.
- 승인 상태 문자열만으로 쓰기 도구를 실행하지 않습니다.
- 향후 쓰기 도구는 불변 payload hash, 1회성 승인, idempotency, 실행 원장, 자격증명 격리를 먼저
  구현한 뒤 별도 단계에서 추가합니다.
- 도구 정책은 프롬프트 내용이 아니라 코드의 AgentDefinition과 catalog를 기준으로 판정합니다.

## 배포 후 무비용 확인

`SMOKE_TOOL_GATEWAY.bat`을 실행하면 운영 API의 준비 상태와 공개 도구 catalog를 읽기 전용으로
검사합니다. OpenAI 업무나 Telegram 전송을 시작하지 않고 테스트 데이터도 만들지 않습니다.
