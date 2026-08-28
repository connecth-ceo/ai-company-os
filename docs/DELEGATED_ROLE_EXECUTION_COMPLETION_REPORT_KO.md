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

이 검증은 `AI_PROVIDER=mock`이며 OpenAI 요청과 비용을 발생시키지 않았다.

## 아직 운영 환경에서 검증하지 않은 것

- GitHub Actions에서 이번 commit의 CI 완료.
- Render PostgreSQL `d4e6a8b0c2f4 → e6f8a0c2d4b6` 실제 migration.
- Render Web/Worker가 동일 commit으로 Live인지와 `/ready` 응답.
- 운영 API에서 위임 생성 → worker dispatch → 단일 역할 완료의 1회 E2E.
- 실제 OpenAI 응답의 토큰 원장과 timeout 동작.

마지막 항목은 OpenAI 비용을 발생시키므로 별도 사용자 승인을 받은 1회 smoke에서만 실행한다. 실제 USD
청구액 원장은 아직 제공자 청구 데이터와 연결하지 않았으므로 `cost_budget_usd`는 허용 예약 상한이다.

## 배포 후 확인 순서

1. GitHub CI 성공을 확인한다.
2. Render migration log에서 head `e6f8a0c2d4b6`을 확인한다.
3. Web과 Worker가 같은 commit으로 Live인지 확인한다.
4. `/ready`의 DB/Redis/schema 상태를 확인한다.
5. 비용 승인 뒤 작은 토큰 예산으로 위임 1건만 실행한다.
6. Delegation/TaskRun 토큰·시간·상태와 감사 이벤트를 대조한다.
