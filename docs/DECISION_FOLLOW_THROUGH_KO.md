# 결정 후속 실행 큐

## 목적

대표 결정이 기록에만 머물지 않고 담당자와 마감일이 있는 Commitment로 이어졌는지 결정론적으로
확인합니다. 기존 Decision과 Commitment를 읽어 계산하며 상태를 자동 변경하거나 외부 행동을 실행하지
않습니다.

## 분류 규칙

규칙 버전은 `decision-follow-through-v1`입니다.

| 수준 | 조건 |
| --- | --- |
| at_risk | 활성 후속 약속이 기한을 넘겼거나 연결 약속이 모두 취소됨 |
| untracked | 활성 결정에 연결된 약속이 없음 |
| in_progress | 연결 약속 중 진행 중 항목이 있음 |
| planned | 실행 대기 약속이 있고 기한을 넘기지 않음 |
| complete | 연결 약속이 완료됐고 미완료 약속이 없음 |
| inactive | 결정이 proposed, superseded, expired, revoked 상태임 |

기본 큐는 `at_risk`, `untracked`, `in_progress`, `planned`만 표시합니다. 전체 요약은 완료·비활성
결정까지 포함하고, 제한 개수를 적용하기 전에 계산합니다.

실행 연결률은 활성 결정 중 하나 이상의 Commitment가 연결된 결정 비율입니다. 연결이 있다는 사실과
실행 완료는 구분합니다.

## API

- 기본 큐: `GET /api/v1/decisions/follow-through`
- 완료 포함: `GET /api/v1/decisions/follow-through?include_complete=true`
- 비활성 포함: `GET /api/v1/decisions/follow-through?include_inactive=true`
- 표시 제한: `limit=1..200`

응답에는 결정별 약속 상태 개수, 기한 초과 개수, 다음 마감일, 분류 사유가 포함됩니다.

## 안전 경계

- tenant별 Decision과 Commitment만 조회합니다.
- 조회 전후 AuditEvent나 원본 상태를 변경하지 않습니다.
- 새 테이블·컬럼·migration이 없습니다.
- OpenAI나 외부 네트워크를 호출하지 않습니다.
- 이메일, 결제, 삭제, 배포 같은 외부 행동을 실행하지 않습니다.

## 운영 확인

Render에서 `APP_API_KEY`를 복사한 뒤 `SMOKE_DECISION_FOLLOW_THROUGH.bat`을 실행합니다. 스크립트는
`/ready`, OpenAPI 계약, 인증된 읽기 큐만 확인하며 데이터를 생성하거나 변경하지 않습니다.
