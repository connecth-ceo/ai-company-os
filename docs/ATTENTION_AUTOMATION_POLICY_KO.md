# 대표 주의신호 저위험 자동계획 정책

## 목적

대표가 모든 운영 예외를 반복 승인하지 않아도 되도록, 비용과 외부 영향이 없는 내부 후속계획을
결정론적으로 생성하는 경계다. 이 기능은 AI를 호출하지 않고 외부 도구를 실행하지 않으며, 생성한
Task도 실행하지 않는다.

## 자동계획 대상

- 신호 종류: `overdue_commitment`, `long_running_task`, `task_failure`
- 신호 수준: `info`, `watch`, `action`
- 결과: `queued` Task 1건과 담당자·기한이 있는 Commitment 1건
- 기본 담당자: `chief_of_staff`
- 동일 신호 fingerprint는 idempotency key로 한 번만 계획

## 반드시 대표에게 남기는 대상

- `pending_approval`, `decision_governance`
- `decision`, `critical` 수준의 모든 신호
- 이미 확인했거나 동일 fingerprint에 후속계획이 있는 신호

자동계획이 활성화되어도 위 대상은 생성·실행하지 않는다.

## API와 스케줄

- `GET /api/v1/attention/automation-policy`: 현재 정책과 활성화 상태 조회
- `POST /api/v1/attention/automation/run`: 기본값은 `dry_run=true`
- Celery Beat가 설정 주기마다 틱을 호출하지만 `ATTENTION_AUTO_PLAN_ENABLED=false`이면 즉시 no-op
- 운영 Blueprint 기본값도 `false`이므로 배포만으로 테스트 데이터가 생기지 않는다.

실제 자동계획을 켜려면 운영 검증 후 Web Service의 `ATTENTION_AUTO_PLAN_ENABLED=true`로 명시하고,
Worker에는 같은 값을 전달해야 한다. 활성화 이후에도 TaskRun, AI 호출, 외부 발송·결제·게시·삭제는
발생하지 않는다.

## 다음 안전 경계

후속 Task를 자동 실행하는 단계는 별도다. 실행 전에는 역할 권한, 비용 한도, 승인 필요 여부,
도구 side effect, 불변 payload hash와 단일사용 ExecutionAttempt 원장을 다시 검사해야 한다.
