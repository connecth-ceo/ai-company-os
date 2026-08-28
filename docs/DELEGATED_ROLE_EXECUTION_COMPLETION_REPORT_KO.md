# 위임된 단일 역할 실행 완료 보고서

작성일: 2026-08-28

## 완료한 범위

- 기존 일반 V0.5 Workflow를 변경하지 않고 위임 전용 실행 API를 추가했다.
- `source=delegation` Task의 일반 `/run` 우회를 차단했다.
- 실행 전 tenant/Project/계층, 승인, Registry 역할과 버전, provider/model, 도구, 권한, 승인 정책,
  토큰·시간·비용 상한을 다시 검사한다.
- 현재 허용 목록 밖의 도구·권한·승인 정책과 불완전한 옛 정책 스냅샷은 fail-closed로 거부한다.
- 한 등록 역할만 실행하며 자동 재귀 위임이나 외부 행동은 수행하지 않는다.
- OpenAI Agents runtime에 남은 출력 토큰 상한을 전달한다.
- Delegation과 TaskRun에 runtime/model, 토큰, 시간, 상태, 오류 및 감사 이벤트를 남긴다.
- Celery 전송 실패 시 다시 요청할 수 있는 상태로 복구한다. 실행 시작 뒤 자동 재시도는 비용 중복 방지를
  위해 사용하지 않는다.
- Alembic `e6f8a0c2d4b6` migration과 운영 문서를 추가했다.

## 실제로 검증한 것

| 검사 | 결과 |
|---|---|
| 전체 pytest | `75 passed` |
| Ruff lint/format | 통과 |
| Python compileall | 통과 |
| 역할별 mock 실행과 TaskRun 원장 | 통과 |
| 일반 `/run` 우회 차단 | 통과 |
| tenant 격리와 중복 dispatch 차단 | 통과 |
| 정책 drift 사전 거부 | 통과 |
| Celery queue 전송 실패 복구 | 통과 |
| 실행 후 토큰 초과 fail-closed | 통과 |
| SQLite migration | 빈 DB에서 head, downgrade, 재-upgrade 통과 |
| PostgreSQL offline DDL | 열, FK RESTRICT, unique index, revision SQL 생성 확인 |
| GitHub Actions CI | commit `a759cbc`, 성공 |
| Render migration | `d4e6a8b0c2f4 → e6f8a0c2d4b6`, 완료 |
| Render Web/Worker | 동일 commit `a759cbc` Live, `/ready` 200 및 Celery ready 확인 |
| 운영 위임 E2E | parent → Legal Review 위임 → worker 단일 역할 실행 → completed |
| 실제 OpenAI 런타임 | `openai_agents`, `gpt-5.6-luna`, 1회 실행 성공 |
| 실제 사용량 원장 | input 1,554 / output 306 / total 1,860 tokens, 7,485 ms |
| 단일 역할 경계 | Child TaskRun 1건, `Legal Risk Review Agent`, WorkflowRun 미생성 확인 |

로컬 자동검사는 `AI_PROVIDER=mock`으로 비용 없이 수행했다. 이후 사용자가 명시적으로 승인한 운영 smoke
1건에서 실제 OpenAI 요청과 테스트 데이터 생성을 수행했다. 생성된 식별자는 다음과 같다.

- Parent Task: `dab2a9c5-0698-487e-a39a-bb261e5fe203`
- Delegation: `6caa671c-7ebb-41f2-8bdc-63a1e7731747`
- Child Task: `66d7e407-926c-4ec1-8aae-bd7ad64e543a`

검사 도구는 `APP_API_KEY`를 Windows clipboard에서 메모리로만 읽고 종료 시 clipboard와 변수에서
제거한다. 키와 실제 결과 본문은 로그나 완료 보고서에 기록하지 않는다.

## 아직 운영 환경에서 검증하지 않은 것

- timeout을 실제로 발생시켰을 때 worker 중단과 실패 원장이 일치하는지 확인.
- OpenAI 제공자 청구 데이터와 내부 USD 비용 원장의 연결.
- worker가 실행 도중 강제 종료된 경우의 중복 비용 방지·수동 복구 검증.

실제 USD 청구액 원장은 아직 제공자 청구 데이터와 연결하지 않았으므로 `cost_budget_usd`는 허용 예약
상한이다. 이번 성공은 비용 상한·토큰 원장·단일 실행 경계를 확인했지만 실제 청구액 대조를 의미하지 않는다.

## 배포 후 확인 순서

위 여섯 항목은 모두 완료했다. 다음 운영 단계에서는 자동 재시도 없이 실패 복구 절차, 실제 제공자 비용
대조, CEO 승인함과 연결된 위임 정책을 추가한다.
